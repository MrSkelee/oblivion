import requests
import logging
import os
from .db import get_db

logger = logging.getLogger(__name__)

class LeakChecker:
    def __init__(self, hibp_api_key: str = None):
        self.hibp_api_key = hibp_api_key or os.getenv("HIBP_API_KEY", "")

    def check_email_breaches(self, email: str) -> list[dict]:
        """
        Verifica se l'email compare in violazioni pubbliche (HaveIBeenPwned API).
        Se non è presente una chiave HIBP, interroga endpoint alternativi o restituisce il log.
        """
        if not self.hibp_api_key:
            logger.info(f"Nessuna HIBP_API_KEY configurata. Scansione simulata per {email}.")
            return []

        url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=false"
        headers = {
            "hibp-api-key": self.hibp_api_key,
            "user-agent": "PersonalPrivacyAgent-AI"
        }

        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                breaches = res.json()
                return breaches
            elif res.status_code == 404:
                return []
            else:
                logger.warning(f"HIBP API status: {res.status_code}")
                return []
        except Exception as e:
            logger.error(f"Errore controllo breach per {email}: {e}")
            return []

    def sync_new_breaches(self, emails: list[str], notifier=None) -> int:
        """
        Scansiona la lista di email, salva i nuovi leak nel database e invia notifica Telegram.
        """
        conn = get_db()
        cursor = conn.cursor()
        new_count = 0

        for em in emails:
            breaches = self.check_email_breaches(em)
            for b in breaches:
                title = b.get("Title", "Unknown Breach")
                date = b.get("BreachDate", "")
                data_classes = b.get("DataClasses", [])

                # Verifica se già registrato
                cursor.execute("SELECT id FROM leaks WHERE email = ? AND breach_title = ?", (em, title))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO leaks (email, breach_title, breach_date, data_classes)
                        VALUES (?, ?, ?, ?)
                    """, (em, title, date, str(data_classes)))
                    new_count += 1

                    if notifier:
                        notifier.notify_leak_detected(em, title, date, data_classes)

        conn.commit()
        conn.close()
        return new_count
