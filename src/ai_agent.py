import os
import json
import logging
import requests

logger = logging.getLogger(__name__)

# Modelli OpenRouter 100% GRATUITI con failover a cascata
# 'openrouter/free' fa da router automatico al miglior modello gratuito attivo in quel momento
FREE_MODELS = [
    "openrouter/free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "liquid/lfm-2.5-2.6b:free"
]

class OpenRouterPrivacyAgent:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def analyze_broker_email(self, broker_name: str, subject: str, body: str) -> dict:
        """
        Analizza l'email del broker passando a cascata tra i modelli FREE di OpenRouter.
        Se un modello è temporaneamente saturo o in rate-limit (429), passa subito al successivo.
        """
        if not self.is_configured():
            logger.warning("OPENROUTER_API_KEY mancante nel file .env: fallback di sicurezza.")
            return {
                "classification": "UNKNOWN",
                "summary": "Email ricevuta (OpenRouter API key mancante).",
                "detected_link": None,
                "action_required": True,
                "model_used": "none"
            }

        prompt = f"""You are a legal assistant specializing in GDPR, CCPA, and data privacy rights.
Analyze this email reply received from the Data Broker / Company '{broker_name}'.

Subject: {subject}
Email Body:
{body[:3500]}

Return STRICTLY valid JSON with no markdown tags or conversational filler:
{{
  "classification": "SUCCESS" | "OPT_OUT_LINK" | "VERIFICATION_REQUIRED" | "REJECTED" | "UNKNOWN",
  "summary": "Concise 1-2 sentence summary in English explaining what the company states",
  "detected_link": "Complete URL of confirmation or opt-out link if present in text, otherwise null",
  "action_required": true
}}

Classification guidelines:
- SUCCESS: Confirmed data erasure, processed opt-out, or stated user is not in their records.
- OPT_OUT_LINK: Provided a link that must be visited or submitted to complete removal.
- VERIFICATION_REQUIRED: Requests ID verification, phone number, utility bill, or portal sign-in.
- REJECTED: Refused deletion request or invoked an exemption.
- UNKNOWN: Automated ticket acknowledgement or generic marketing newsletter.
"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/privacy-agent",
            "X-Title": "Personal Privacy Agent AI",
            "Content-Type": "application/json"
        }

        # Prova i modelli free uno alla volta in caso di errore o limite raggiunto
        for model in FREE_MODELS:
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1
            }

            try:
                res = requests.post(self.base_url, headers=headers, json=payload, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"].strip()

                    # Pulisci eventuali blocchi markdown ```json ... ```
                    if content.startswith("```"):
                        lines = content.split("\n")
                        content = "\n".join([l for l in lines if not l.startswith("```")]).strip()

                    parsed = json.loads(content)
                    parsed["model_used"] = model
                    logger.info(f"Analisi completata con successo usando il modello free: {model}")
                    return parsed
                elif res.status_code in [429, 503]:
                    logger.warning(f"Modello {model} saturo (Status {res.status_code}). Switch al prossimo modello free...")
                    continue
                else:
                    logger.warning(f"Errore {res.status_code} su modello {model}: {res.text}. Switch al prossimo...")
                    continue
            except Exception as e:
                logger.warning(f"Eccezione su {model}: {e}. Switch al prossimo...")
                continue

        return {
            "classification": "UNKNOWN",
            "summary": "Tutti i modelli free temporaneamente occupati. Richiesta salvata per analisi successiva.",
            "detected_link": None,
            "action_required": True,
            "model_used": "failed_all"
        }
