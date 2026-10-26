import requests
import re
import urllib.parse
import logging
import html
import os
from .db import get_db, record_interaction

logger = logging.getLogger(__name__)

# Domini da ignorare (servizi essenziali o motori che non sono data broker)
IGNORED_DOMAINS = {
    "google.com", "google.it", "youtube.com", "github.com", "microsoft.com",
    "telegram.org", "discord.com", "apple.com", "steamcommunity.com",
    "twitch.tv", "reddit.com", "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "facebook.com", "openrouter.ai", "wikipedia.org",
    "yahoo.com", "bing.com", "duckduckgo.com", "amazon.it", "amazon.com"
}

class AIBrokerFinder:
    def __init__(self, ai_agent=None, notifier=None):
        self.ai_agent = ai_agent
        self.notifier = notifier
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

    def search_duckduckgo(self, query: str, max_results: int = 10) -> list[str]:
        """Esegue una ricerca web su DuckDuckGo (HTML) ed estrae gli URL trovati."""
        urls = []
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            res = requests.post(url, data={"q": query}, headers=self.headers, timeout=12)
            if res.status_code == 200:
                raw_urls = re.findall(r'class="result__url"[^>]*href="([^"]+)"', res.text)
                if not raw_urls:
                    raw_urls = re.findall(r'href="([^"]*uddg=[^"]*)"', res.text)

                for u in raw_urls:
                    if "uddg=" in u:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
                        if "uddg" in parsed:
                            u = parsed["uddg"][0]
                    if u.startswith("http"):
                        urls.append(u)
                        if len(urls) >= max_results:
                            break
        except Exception as e:
            logger.warning(f"Errore ricerca DuckDuckGo per '{query}': {e}")

        return urls

    def extract_privacy_email_from_site(self, domain: str) -> str:
        """Cerca l'email del DPO o privacy navigando la homepage o la privacy policy."""
        candidate_paths = ["", "/privacy", "/privacy-policy", "/gdpr", "/contacts", "/legal"]
        emails_found = []

        for path in candidate_paths:
            target_url = f"https://{domain}{path}"
            try:
                res = requests.get(target_url, headers=self.headers, timeout=8, allow_redirects=True)
                if res.status_code == 200:
                    text = res.text
                    # Trova tutti gli indirizzi email nella pagina
                    matches = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
                    for m in matches:
                        clean = m.lower().strip(".")
                        # Esclude estensioni di file o falsi positivi
                        if not any(clean.endswith(ext) for ext in [".png", ".jpg", ".webp", ".css", ".js", ".svg"]):
                            emails_found.append(clean)
            except Exception:
                continue

            # Se abbiamo trovato un'email specifica di privacy, possiamo fermarci
            best_emails = [e for e in emails_found if any(k in e for k in ["privacy", "dpo", "legal", "gdpr", "optout"])]
            if best_emails:
                return best_emails[0]

        # Ritorna l'email più appropriata
        if emails_found:
            for pref in ["privacy", "dpo", "legal", "compliance", "support", "info", "contact"]:
                for e in emails_found:
                    if pref in e:
                        return e
            return emails_found[0]

        return None

    def discover_and_enroll(self, user_name: str, emails: list[str], phone: str = "") -> int:
        """
        Cerca menzioni pubbliche dei dati dell'utente su internet,
        scova nuovi broker e li aggiunge automaticamente al database per la rimozione.
        """
        queries = []
        for e in emails:
            queries.append(f'"{e}"')

        if phone:
            queries.append(f'"{phone}"')
            clean_phone = re.sub(r'[^0-9]', '', phone)
            if len(clean_phone) >= 9:
                queries.append(f'"{clean_phone[-10:]}"')

        if user_name:
            queries.append(f'"{user_name}" phone OR email OR privacy OR directory')

        discovered_domains = set()
        for q in queries:
            logger.info(f"Ricerca web OSINT: {q}")
            results = self.search_duckduckgo(q, max_results=8)
            for u in results:
                try:
                    netloc = urllib.parse.urlparse(u).netloc.lower()
                    if netloc.startswith("www."):
                        netloc = netloc[4:]
                    if netloc and not any(netloc.endswith(ig) for ig in IGNORED_DOMAINS):
                        discovered_domains.add(netloc)
                except Exception:
                    pass

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT domain FROM brokers")
        existing_domains = {r["domain"].lower() for r in cursor.fetchall()}

        newly_added = 0
        for domain in discovered_domains:
            if domain in existing_domains:
                continue

            logger.info(f"Analisi nuovo dominio trovato online: {domain}")
            privacy_email = self.extract_privacy_email_from_site(domain)

            if privacy_email:
                broker_id = domain.replace(".", "_")
                name = domain.split(".")[0].capitalize()

                cursor.execute("""
                    INSERT OR IGNORE INTO brokers (id, name, domain, email, country, category, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    broker_id,
                    name,
                    domain,
                    privacy_email,
                    "Global",
                    "Discovered via Web Search",
                    "Trovato automaticamente da AI Web Discovery"
                ))

                if cursor.rowcount > 0:
                    newly_added += 1
                    existing_domains.add(domain)
                    logger.info(f"✅ Nuovo broker censito con successo: {name} ({domain}) -> {privacy_email}")

                    if self.notifier:
                        self.notifier.send_message(
                            f"🌐 <b>Nuovo Sito con tuoi dati individuato!</b>\n\n"
                            f"🏢 <b>Sito/Broker:</b> {name} (<code>{domain}</code>)\n"
                            f"✉️ <b>Email Privacy estratta:</b> <code>{privacy_email}</code>\n"
                            f"🛡️ <i>Aggiunto alla lista di rimozione GDPR in attesa di invio.</i>"
                        )

        conn.commit()
        conn.close()
        return newly_added
