import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
import os
import logging
import requests

logger = logging.getLogger(__name__)

class MailService:
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_user = os.getenv("EMAIL_USER", "")
        self.smtp_pass = os.getenv("EMAIL_PASSWORD", "")

        self.imap_host = os.getenv("IMAP_HOST", "imap.gmail.com")
        self.imap_port = int(os.getenv("IMAP_PORT", 993))

    def is_configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_pass)

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        if not self.is_configured():
            logger.error("Credenziali email non configurate in .env")
            return False

        msg = MIMEMultipart()
        msg['From'] = self.smtp_user
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        try:
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                server.starttls()

            server.login(self.smtp_user, self.smtp_pass)
            server.sendmail(self.smtp_user, to_email, msg.as_string())
            server.quit()
            logger.info(f"Email inviata con successo a {to_email}")
            return True
        except Exception as e:
            logger.error(f"Errore durante l'invio dell'email a {to_email}: {e}")
            return False

    def fetch_unread_replies(self) -> list[dict]:
        """
        Controlla la posta in arrivo tramite IMAP per nuovi messaggi non letti.
        Restituisce una lista di dict con mittente, oggetto e corpo testuale.
        """
        if not self.is_configured():
            return []

        messages = []
        try:
            mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            mail.login(self.smtp_user, self.smtp_pass)
            mail.select("INBOX")

            status, search_data = mail.search(None, '(UNSEEN)')
            if status != "OK":
                mail.close()
                mail.logout()
                return []

            email_ids = search_data[0].split()
            for e_id in email_ids[-10:]: # Controlla gli ultimi 10 non letti
                res, data = mail.fetch(e_id, '(RFC822)')
                if res != "OK":
                    continue

                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Decodifica Oggetto
                subject_header = decode_header(msg.get("Subject", ""))[0]
                subject = subject_header[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(subject_header[1] or "utf-8", errors="replace")

                from_header = msg.get("From", "")

                # Estrazione corpo del messaggio
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode(errors="replace")
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="replace")

                messages.append({
                    "id": e_id.decode(),
                    "from": from_header,
                    "subject": subject,
                    "body": body
                })

            mail.close()
            mail.logout()
        except Exception as e:
            logger.error(f"Errore durante la lettura IMAP: {e}")

        return messages

    @staticmethod
    def visit_confirmation_link(url: str) -> bool:
        """
        Visita automaticamente un link di conferma opt-out/cancellazione ricevuto via email.
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            res = requests.get(url, headers=headers, timeout=15)
            logger.info(f"Link di opt-out visitato: {url} - Status Code: {res.status_code}")
            return res.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Errore nella visita del link {url}: {e}")
            return False
