import requests
import logging
import threading
import time
import os
from .db import get_stats, get_db

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.last_update_id = 0
        self.polling_active = False
        self.daemon_callbacks = {}

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def register_callbacks(self, callbacks: dict):
        """Registra le funzioni del daemon da chiamare via comando Telegram."""
        self.daemon_callbacks = callbacks

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.is_configured():
            logger.warning("Telegram Bot non configurato: salta invio notifica.")
            return False

        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False
            }
            res = requests.post(url, json=payload, timeout=10)
            return res.status_code == 200
        except Exception as e:
            logger.error(f"Errore invio messaggio Telegram: {e}")
            return False

    def notify_email_sent(self, broker_name: str, broker_email: str):
        text = (
            f"📤 <b>GDPR Erasure Request Sent</b>\n\n"
            f"🏢 <b>Broker:</b> {broker_name}\n"
            f"✉️ <b>Recipient:</b> <code>{broker_email}</code>\n"
            f"⚖️ <b>Legal Basis:</b> Art. 17 GDPR (Right to Erasure)\n"
            f"⏳ <i>Awaiting formal compliance within 30 days.</i>"
        )
        return self.send_message(text)

    def notify_leak_detected(self, email: str, breach_title: str, breach_date: str, leaked_fields: list[str]):
        fields_str = ", ".join(leaked_fields) if leaked_fields else "Various records"
        text = (
            f"🚨 <b>NEW DATA BREACH DETECTED ONLINE</b>\n\n"
            f"👤 <b>Compromised Email:</b> <code>{email}</code>\n"
            f"🌐 <b>Source:</b> <b>{breach_title}</b> ({breach_date})\n"
            f"⚠️ <b>Exposed Data:</b> {fields_str}\n\n"
            f"🛡️ <i>Targeted erasure requests are being queued.</i>"
        )
        return self.send_message(text)

    def notify_broker_response(self, broker_name: str, classification: str, summary: str, detected_link: str = None):
        icon = "✅" if classification == "SUCCESS" else "⚠️" if classification == "OPT_OUT_LINK" else "❓"
        text = (
            f"{icon} <b>Response Received: {broker_name}</b>\n\n"
            f"🤖 <b>AI Classification:</b> <code>{classification}</code>\n"
            f"📝 <b>Summary:</b>\n{summary}\n"
        )
        if detected_link:
            text += f"\n🔗 <b>Confirmation Link:</b>\n{detected_link}\n<i>(Automated verification attempt in progress)</i>"

        return self.send_message(text)

    def send_detailed_status(self):
        """Sends a detailed progress report of all operations."""
        stats = get_stats()
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT name, status, last_contacted_at, notes
            FROM brokers
            WHERE status != 'PENDING'
            ORDER BY last_contacted_at DESC LIMIT 5
        """)
        contacted = [dict(r) for r in cursor.fetchall()]
        conn.close()

        contacted_str = ""
        if contacted:
            for c in contacted:
                status_icon = "✅" if c['status'] == 'CONFIRMED' else "📤" if c['status'] == 'SENT' else "❌"
                notes = f" - <i>{c['notes']}</i>" if c['notes'] else ""
                contacted_str += f"• {status_icon} <b>{c['name']}</b> ({c['status']}){notes}\n"
        else:
            contacted_str = "<i>No requests sent yet.</i>\n"

        text = (
            f"📊 <b>OBLIVION STATUS REPORT</b>\n\n"
            f"📈 <b>Database Summary:</b>\n"
            f"• ⏳ Pending: <b>{stats.get('pending', 0)}</b> brokers\n"
            f"• 📤 Requests Sent: <b>{stats.get('sent', 0)}</b>\n"
            f"• ✅ Confirmed Removals: <b>{stats.get('confirmed', 0)}</b>\n"
            f"• ❌ Refusals: <b>{stats.get('refused', 0)}</b>\n"
            f"• 🚨 Active Leaks: <b>{stats.get('active_leaks', 0)}</b>\n\n"
            f"🕒 <b>Recent Activity:</b>\n{contacted_str}\n"
            f"💡 <i>Type /help to view available commands.</i>"
        )
        return self.send_message(text)

    def send_brokers_summary(self):
        """Displays brokers grouped by status."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name, domain, status FROM brokers ORDER BY status, name")
        brokers = [dict(r) for r in cursor.fetchall()]
        conn.close()

        if not brokers:
            return self.send_message("No brokers registered in database.")

        sent_list = [f"• {b['name']}" for b in brokers if b['status'] == 'SENT']
        confirmed_list = [f"• {b['name']}" for b in brokers if b['status'] == 'CONFIRMED']
        pending_count = len([b for b in brokers if b['status'] == 'PENDING'])

        text = f"🏢 <b>DATA BROKER DIRECTORY ({len(brokers)} total)</b>\n\n"
        if confirmed_list:
            text += f"✅ <b>Confirmed Removals ({len(confirmed_list)}):</b>\n" + "\n".join(confirmed_list[:8]) + "\n\n"
        if sent_list:
            text += f"📤 <b>Awaiting Response ({len(sent_list)}):</b>\n" + "\n".join(sent_list[:8]) + "\n\n"
        text += f"⏳ <b>Queued for Dispatch:</b> <b>{pending_count}</b> brokers remaining.\n\n"
        text += "💡 <i>Use /send_next to dispatch the next 3 requests immediately.</i>"

        return self.send_message(text)

    def _poll_updates(self):
        """Listening loop for incoming Telegram commands."""
        logger.info("Started Telegram command polling...")
        while self.polling_active:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self.last_update_id + 1, "timeout": 20}
                res = requests.get(url, params=params, timeout=25)

                if res.status_code == 200:
                    data = res.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        msg = update.get("message", {})
                        from_chat = str(msg.get("chat", {}).get("id", ""))
                        text = msg.get("text", "").strip()

                        # Security check: only authorized chat ID
                        if from_chat == str(self.chat_id):
                            parts = text.split()
                            cmd = parts[0].lower() if parts else ""

                            if cmd == "/status":
                                self.send_detailed_status()
                            elif cmd in ["/start", "/help"]:
                                self.send_message(
                                    "🛡️ <b>OBLIVION COMMANDS</b>\n\n"
                                    "• <code>/status</code> - Complete removal status report\n"
                                    "• <code>/brokers</code> - List of brokers and current status\n"
                                    "• <code>/send_next</code> - Immediately dispatch next batch of 3 requests\n"
                                    "• <code>/scan</code> - Launch AI OSINT search for exposed records\n"
                                    "• <code>/add &lt;domain&gt;</code> - Add site to removal queue (e.g. <code>/add spokeo.com</code>)\n"
                                    "• <code>/pause</code> - Pause scheduled email dispatching\n"
                                    "• <code>/resume</code> - Resume automated dispatching"
                                )
                            elif cmd == "/brokers":
                                self.send_brokers_summary()
                            elif cmd == "/send_next":
                                fn = self.daemon_callbacks.get("send_next")
                                if fn:
                                    self.send_message("🚀 <i>Dispatching next batch of requests...</i>")
                                    fn()
                            elif cmd == "/scan":
                                fn = self.daemon_callbacks.get("scan")
                                if fn:
                                    self.send_message("🔍 <i>AI Web Discovery launched in background... You will be alerted if new sites are found.</i>")
                                    threading.Thread(target=fn, daemon=True).start()
                            elif cmd == "/pause":
                                fn = self.daemon_callbacks.get("pause")
                                if fn:
                                    fn()
                                    self.send_message("⏸️ <b>Automated GDPR requests PAUSED.</b>")
                            elif cmd == "/resume":
                                fn = self.daemon_callbacks.get("resume")
                                if fn:
                                    fn()
                                    self.send_message("▶️ <b>Automated GDPR requests RESUMED.</b>")
                            elif cmd == "/add":
                                if len(parts) > 1:
                                    domain = parts[1].replace("https://", "").replace("http://", "").split("/")[0].strip()
                                    fn = self.daemon_callbacks.get("add_broker")
                                    if fn:
                                        self.send_message(f"🔎 <i>Searching privacy and DPO contacts for <code>{domain}</code>...</i>")
                                        threading.Thread(target=fn, args=(domain,), daemon=True).start()
                                else:
                                    self.send_message("⚠️ <i>Please specify a domain! Example:</i>\n<code>/add example.com</code>")
                time.sleep(1)
            except Exception as e:
                time.sleep(5)

    def start_polling(self):
        if not self.is_configured():
            return
        self.polling_active = True
        thread = threading.Thread(target=self._poll_updates, daemon=True)
        thread.start()

    def stop_polling(self):
        self.polling_active = False
