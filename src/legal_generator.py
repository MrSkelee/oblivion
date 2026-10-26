def generate_gdpr_request(broker_name: str, user_name: str, user_emails: list[str], user_phone: str = "", language: str = "it") -> dict:
    emails_str = ", ".join(user_emails)
    phone_line_it = f"- Recapito telefonico: {user_phone}\n" if user_phone else ""
    phone_line_en = f"- Phone number: {user_phone}\n" if user_phone else ""

    if language == "it":
        subject = f"Richiesta di cancellazione dati personali ex Art. 17 GDPR - {user_name}"
        body = f"""Spettabile Responsabile della Protezione dei Dati (DPO) di {broker_name},

Il/La sottoscritto/a {user_name}, ai sensi dell'Articolo 17 del Regolamento Generale sulla Protezione dei Dati (Regolamento UE 2016/679 - GDPR), richiede formalmente con la presente la cancellazione immediata di tutti i dati personali che mi riguardano conservati nei vostri archivi, database, sistemi di profilazione e backup.

Dati identificativi di riferimento:
- Nome e Cognome: {user_name}
- Indirizzo/i Email associati: {emails_str}
{phone_line_it}
Inoltre, ai sensi dell'Articolo 19 del GDPR, chiedo che tale cancellazione venga comunicata a ciascuno dei destinatari o terzi cui sono stati eventualmente trasmessi i miei dati personali.

Richiedo altresì l'inserimento permanente dei miei recapiti in una 'suppression list' (lista di soppressione/opt-out) per impedire il ripopolamento futuro o la re-indicizzazione del mio profilo tramite fonti terze.

Si ricorda che, ai sensi dell'Articolo 12, paragrafo 3 del GDPR, siete tenuti a dare riscontro all'interessato senza ingiustificato ritardo e al più tardi entro un mese dal ricevimento della presente richiesta.

In attesa di una vostra tempestiva conferma scritta di avvenuta cancellazione, porgo distinti saluti.

{user_name}
"""
    else:
        subject = f"Formal Data Deletion Request (GDPR Art. 17 & CCPA Opt-Out) - {user_name}"
        body = f"""To the Data Protection Officer / Privacy Team at {broker_name},

I am writing to formally exercise my right to erasure under Article 17 of the General Data Protection Regulation (GDPR - Regulation EU 2016/679) as well as any applicable global privacy laws (including CCPA opt-out from data sale/sharing).

Please immediately delete and expunge all personal records, identifying data, tracking records, and profile associations concerning me from your systems, databases, partners, and downstream caches.

Identifying details to locate and delete my records:
- Full Name: {user_name}
- Email address(es): {emails_str}
{phone_line_en}
In accordance with GDPR Article 19, please also notify any third parties or data recipients to whom my personal data has been disclosed of this erasure.

Furthermore, please place my contact details on your permanent suppression / do-not-track list so that my profile is not re-scraped or repopulated from third-party data brokers in the future.

Under GDPR Article 12(3), you are obligated to provide confirmation of erasure without undue delay and at the latest within one month of receipt.

I look forward to receiving your prompt written confirmation once the deletion has been completed.

Sincerely,

{user_name}
"""

    return {
        "subject": subject,
        "body": body
    }
