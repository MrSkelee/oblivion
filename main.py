import argparse
import sys
import os
from dotenv import load_dotenv

# Forza codifica UTF-8 su console Windows per supportare emoji
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Carica il file .env se presente
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Prova a caricare da .env.example come fallback informativo
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env.example"))

from src.db import init_db, seed_brokers, get_stats, get_pending_brokers
from src.legal_generator import generate_gdpr_request
from src.telegram_notifier import TelegramNotifier
from src.daemon import PrivacyDaemon

def cmd_status():
    init_db()
    seed_brokers()
    stats = get_stats()
    print("\n" + "="*45)
    print(" 🛡️  STATO ATTUALE PRIVACY VAULT")
    print("="*45)
    print(f" ⏳ Broker in attesa di contatto : {stats['pending']}")
    print(f" 📤 Richieste inviate          : {stats['sent']}")
    print(f" ✅ Cancellazioni confermate   : {stats['confirmed']}")
    print(f" ❌ Rifiuti registrati         : {stats['refused']}")
    print(f" 🚨 Leak attivi monitorati     : {stats['active_leaks']}")
    print("="*45 + "\n")

def cmd_preview():
    user_name = os.getenv("USER_FULL_NAME", "John Doe")
    user_emails = [e.strip() for e in os.getenv("USER_EMAILS", "john.doe@example.com").split(",")]
    user_phone = os.getenv("USER_PHONE", "+1 555 123 4567")

    req = generate_gdpr_request("Acxiom", user_name, user_emails, user_phone, language="it")
    print("\n--- ANTEPRIMA RICHIESTA GDPR (ITALIANO) ---")
    print(f"Oggetto: {req['subject']}\n")
    print(req['body'])
    print("-------------------------------------------\n")

def cmd_test_telegram():
    notifier = TelegramNotifier()
    if not notifier.is_configured():
        print("❌ Errore: TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID mancanti nel file .env!")
        return

    print("Invio notifica di prova a Telegram...")
    success = notifier.send_message(
        "🔔 <b>Test Notifica Privacy Agent</b>\n\n"
        "La connessione tra il tuo agente AI e Telegram è attiva e funzionante!"
    )
    if success:
        print("✅ Notifica inviata con successo sul tuo Telegram!")
    else:
        print("❌ Errore durante l'invio. Verifica che il Bot Token e il Chat ID siano corretti.")

def main():
    parser = argparse.ArgumentParser(description="AI Personal Privacy Agent (Self-Hosted Incogni)")
    subparsers = parser.add_subparsers(dest="command", help="Comando da eseguire")

    subparsers.add_parser("start", help="Avvia l'agente AI sempre attivo in background")
    subparsers.add_parser("status", help="Mostra lo stato e le statistiche dei dati rimossi")
    subparsers.add_parser("preview", help="Mostra un'anteprima della lettera legale GDPR generata")
    subparsers.add_parser("test-telegram", help="Invia una notifica di prova al tuo bot Telegram")
    subparsers.add_parser("run-once", help="Esegue un singolo ciclo di controllo e invio")
    subparsers.add_parser("discover", help="Scandaglia il web per nuovi broker che espongono i tuoi dati")

    args = parser.parse_args()

    if args.command == "start":
        daemon = PrivacyDaemon()
        daemon.start()
    elif args.command == "status":
        cmd_status()
    elif args.command == "preview":
        cmd_preview()
    elif args.command == "test-telegram":
        cmd_test_telegram()
    elif args.command == "discover":
        daemon = PrivacyDaemon()
        print("Avvio scansione AI Web Discovery...")
        daemon.job_discover_new_brokers()
        cmd_status()
    elif args.command == "run-once":
        daemon = PrivacyDaemon()
        print("Esecuzione scansione leak...")
        daemon.job_check_leaks()
        print("Controllo posta in arrivo e analisi AI...")
        daemon.job_check_inbox_and_analyze()
        print("Elaborazione lotto richieste GDPR...")
        daemon.job_process_pending_requests()
        cmd_status()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
