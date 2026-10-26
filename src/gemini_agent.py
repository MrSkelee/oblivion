import os
import json
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiPrivacyAgent:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    def is_configured(self) -> bool:
        return self.client is not None

    def analyze_broker_email(self, broker_name: str, subject: str, body: str) -> dict:
        """
        Analizza l'email ricevuta da un data broker e restituisce:
        - classification: SUCCESS | OPT_OUT_LINK | VERIFICATION_REQUIRED | REJECTED | UNKNOWN
        - summary: breve sintesi in italiano (1-2 frasi)
        - detected_link: link di conferma o opt-out (se presente)
        - action_required: bool
        """
        if not self.is_configured():
            logger.warning("Gemini API Key non impostata: fallback euristico.")
            return {
                "classification": "UNKNOWN",
                "summary": "Email ricevuta (analisi AI disattivata per mancanza API key).",
                "detected_link": None,
                "action_required": True
            }

        prompt = f"""You are a legal assistant specializing in GDPR, CCPA, and online privacy rights.
Analyze this email reply received from the Data Broker / Company '{broker_name}'.

Subject: {subject}
Email Body:
{body[:3000]}

Return STRICTLY valid JSON with no markdown tags or conversational filler:
{{
  "classification": "SUCCESS" | "OPT_OUT_LINK" | "VERIFICATION_REQUIRED" | "REJECTED" | "UNKNOWN",
  "summary": "Concise 1-2 sentence summary in English explaining what the company states",
  "detected_link": "Complete URL of confirmation or opt-out link if present in text, otherwise null",
  "action_required": true or false
}}

Classification guidelines:
- SUCCESS: Confirmed data erasure, processed opt-out, or stated user is not in their records.
- OPT_OUT_LINK: Provided a link that must be visited or submitted to complete removal.
- VERIFICATION_REQUIRED: Requests ID verification, phone number, utility bill, or portal sign-in.
- REJECTED: Refused deletion request or invoked an exemption.
- UNKNOWN: Automated ticket acknowledgement or generic marketing newsletter.
"""

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            data = json.loads(response.text)
            return data
        except Exception as e:
            logger.error(f"Errore durante l'analisi con Gemini: {e}")
            return {
                "classification": "UNKNOWN",
                "summary": f"Errore analisi AI: {str(e)}",
                "detected_link": None,
                "action_required": True
            }
