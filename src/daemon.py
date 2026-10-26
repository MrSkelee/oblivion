import time
import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler
from .db import (
    init_db, seed_brokers, get_pending_brokers, update_broker_status,
    record_interaction, get_stats, get_db
)
from .legal_generator import generate_gdpr_request
from .mail_service import MailService
from .ai_agent import OpenRouterPrivacyAgent
from .telegram_notifier import TelegramNotifier
from .leak_checker import LeakChecker
from .broker_finder import AIBrokerFinder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("PrivacyDaemon")

class PrivacyDaemon:
    def __init__(self):
        init_db()
        seed_brokers()

        self.user_name = os.getenv("USER_FULL_NAME", "User")
        self.user_emails = [e.strip() for e in os.getenv("USER_EMAILS", "").split(",") if e.strip()]
        self.user_phone = os.getenv("USER_PHONE", "")

        self.mail_service = MailService()
        self.ai_agent = OpenRouterPrivacyAgent()
        self.notifier = TelegramNotifier()
        self.leak_checker = LeakChecker()
        self.finder = AIBrokerFinder(ai_agent=self.ai_agent, notifier=self.notifier)
        self.scheduler = BackgroundScheduler()
        self.is_paused = False

        # Registra i comandi interattivi per Telegram
        self.notifier.register_callbacks({
            "send_next": lambda: self.job_process_pending_requests(batch_size=3),
            "scan": self.job_discover_new_brokers,
            "pause": self.pause,
            "resume": self.resume,
            "add_broker": self.manual_add_broker
        })

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    def manual_add_broker(self, domain: str):
        """Aggiunge manualmente un broker inserito via comando Telegram."""
        domain_clean = domain.lower().replace("https://", "").replace("http://", "").split("/")[0].strip()
        email = self.finder.extract_privacy_email_from_site(domain_clean)
        if not email:
            email = f"privacy@{domain_clean}"

        conn = get_db()
        cursor = conn.cursor()
        broker_id = domain_clean.replace(".", "_")
        name = domain_clean.split(".")[0].capitalize()

        cursor.execute("""
            INSERT OR REPLACE INTO brokers (id, name, domain, email, country, category, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (broker_id, name, domain_clean, email, "Custom", "Aggiunto manualmente via Telegram", "Inserito da utente"))
        conn.commit()
        conn.close()

        self.notifier.send_message(
            f"✅ <b>Site added to removal queue!</b>\n\n"
            f"🏢 <b>Company:</b> {name} (<code>{domain_clean}</code>)\n"
            f"✉️ <b>Contact Email:</b> <code>{email}</code>\n"
            f"⏳ <i>Queued for next dispatch.</i>"
        )

    def job_process_pending_requests(self, batch_size=3):
        """Invia un lotto controllato di richieste GDPR per evitare blocchi antispam."""
        if self.is_paused:
            logger.info("Invio richieste GDPR attualmente in pausa.")
            return

        pending = get_pending_brokers(limit=batch_size)
        if not pending:
            logger.info("Nessuna richiesta GDPR in attesa di invio.")
            return

        logger.info(f"Avvio invio per {len(pending)} broker in attesa...")
        for broker in pending:
            lang = "it" if broker.get("country") == "IT" else "en"
            req = generate_gdpr_request(
                broker_name=broker["name"],
                user_name=self.user_name,
                user_emails=self.user_emails,
                user_phone=self.user_phone,
                language=lang
            )

            success = self.mail_service.send_email(
                to_email=broker["email"],
                subject=req["subject"],
                body=req["body"]
            )

            if success:
                update_broker_status(broker["id"], "SENT")
                record_interaction(broker["id"], "OUTGOING", req["subject"], req["body"])
                self.notifier.notify_email_sent(broker["name"], broker["email"])
                time.sleep(5) # Pausa di cortesia tra un invio e l'altro

    def job_check_inbox_and_analyze(self):
        """Controlla la posta in arrivo e fa analizzare le risposte a Gemini."""
        logger.info("Controllo nuovi messaggi nella casella email...")
        unread = self.mail_service.fetch_unread_replies()
        if not unread:
            return

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, domain, email FROM brokers")
        all_brokers = [dict(r) for r in cursor.fetchall()]
        conn.close()

        for mail in unread:
            sender_raw = mail["from"].lower()
            subject_raw = mail["subject"].lower()
            body_preview = mail["body"][:500].lower()
            matching_broker = None

            for b in all_brokers:
                if b["domain"].lower() in sender_raw or b["email"].lower() in sender_raw:
                    matching_broker = b
                    break

            # FILTRO DI SICUREZZA RIGOROSO:
            # Se il mittente NON è un data broker della nostra lista e l'oggetto/corpo non riguarda il GDPR/rimozione dati,
            # IGNORA completamente l'email (è un'email personale, di Twitch, Discord, ordini, ecc.)
            is_gdpr_related = any(k in subject_raw or k in body_preview for k in [
                "gdpr", "art. 17", "art 17", "oblio", "erasure", "data deletion", 
                "privacy request", "cancellazione dati", "suppression"
            ])

            if not matching_broker and not is_gdpr_related:
                continue

            broker_name = matching_broker["name"] if matching_broker else "Mittente Privacy Esterno"
            broker_id = matching_broker["id"] if matching_broker else None

            # Analisi con OpenRouter AI
            analysis = self.ai_agent.analyze_broker_email(
                broker_name=broker_name,
                subject=mail["subject"],
                body=mail["body"]
            )

            classification = analysis.get("classification", "UNKNOWN")
            summary = analysis.get("summary", "")
            detected_link = analysis.get("detected_link")

            # Se l'AI riconosce che è un'email generica/promozionale senza pertinenza privacy, salta
            if classification == "UNKNOWN" and not matching_broker:
                continue

            # Visita il link SOLO se confermato dall'AI come link di opt-out/cancellazione
            if detected_link and classification == "OPT_OUT_LINK":
                self.mail_service.visit_confirmation_link(detected_link)

            # Aggiorna lo stato nel database
            if broker_id:
                if classification == "SUCCESS":
                    update_broker_status(broker_id, "CONFIRMED", notes=summary)
                elif classification == "REJECTED":
                    update_broker_status(broker_id, "REFUSED", notes=summary)
                else:
                    update_broker_status(broker_id, "IN_REVIEW", notes=summary)

                record_interaction(
                    broker_id=broker_id,
                    direction="INCOMING",
                    subject=mail["subject"],
                    body=mail["body"],
                    classification=classification,
                    detected_link=detected_link
                )

            # Notifica su Telegram
            self.notifier.notify_broker_response(
                broker_name=broker_name,
                classification=classification,
                summary=summary,
                detected_link=detected_link
            )

    def job_check_leaks(self):
        """Verifica se ci sono nuovi leak sulle email monitorate."""
        if self.user_emails:
            logger.info("Esecuzione scansione leak per le email configurate...")
            self.leak_checker.sync_new_breaches(self.user_emails, notifier=self.notifier)

    def job_daily_report(self):
        """Invia il resoconto statistico giornaliero su Telegram."""
        stats = get_stats()
        self.notifier.notify_daily_summary(stats)

    def job_discover_new_brokers(self):
        """Scandaglia il web alla ricerca di nuovi siti o broker che espongono i dati dell'utente."""
        logger.info("Avvio AI Web Discovery per scovare nuovi siti con i dati dell'utente...")
        new_count = self.finder.discover_and_enroll(self.user_name, self.user_emails, self.user_phone)
        logger.info(f"AI Web Discovery terminata: aggiunti {new_count} nuovi siti/broker.")

    def start(self):
        """Avvia lo scheduler 24/7."""
        # 1. Controllo inbox ogni 10 minuti
        self.scheduler.add_job(self.job_check_inbox_and_analyze, 'interval', minutes=10, id='inbox_check')

        # 2. Invio richieste GDPR ogni ora (lotti da 3 broker per volta)
        self.scheduler.add_job(self.job_process_pending_requests, 'interval', hours=1, id='gdpr_dispatch')

        # 3. Controllo leak ogni 12 ore
        self.scheduler.add_job(self.job_check_leaks, 'interval', hours=12, id='leak_sync')

        # 4. Scansione AI Web Discovery ogni 24 ore
        self.scheduler.add_job(self.job_discover_new_brokers, 'interval', hours=24, id='web_discovery')

        # 5. Report giornaliero su Telegram alle ore 20:00
        self.scheduler.add_job(self.job_daily_report, 'cron', hour=20, minute=0, id='daily_report')

        self.scheduler.start()
        self.notifier.start_polling()
        logger.info("🛡️ Privacy Agent Daemon avviato e sempre attivo in background (Polling Telegram attivo).")

        # Notifica immediata di avvio su Telegram
        self.notifier.send_message(
            "🛡️ <b>Privacy Agent AI Attivato!</b>\n"
            "Il servizio è ora in esecuzione e monitora i tuoi dati 24/7.\n"
            "Invia <code>/status</code> per ricevere aggiornamenti in tempo reale."
        )

        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.notifier.stop_polling()
            self.scheduler.shutdown()
            logger.info("Daemon arrestato.")
