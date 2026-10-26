import os
import re
import json
import urllib.request

BROKERS_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "brokers.json")
ERASER_YAML_URL = "https://raw.githubusercontent.com/digisamroc/eraser/master/data/brokers.yaml"

def parse_simple_yaml(yaml_text: str):
    """Semplice parser YAML per estrarre la lista brokers senza dipendenze pesanti."""
    brokers = []
    current = {}
    
    for line in yaml_text.splitlines():
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#") or line_clean.startswith("brokers:"):
            continue
            
        if line_clean.startswith("- id:") or line_clean.startswith("- name:"):
            if current and current.get("email"):
                brokers.append(current)
            current = {}
            parts = line_clean.replace("- ", "", 1).split(":", 1)
            if len(parts) == 2:
                current[parts[0].strip()] = parts[1].strip().strip('"').strip("'")
        elif ":" in line_clean:
            parts = line_clean.split(":", 1)
            k = parts[0].strip()
            v = parts[1].strip().strip('"').strip("'")
            current[k] = v
            
    if current and current.get("email"):
        brokers.append(current)
        
    return brokers

def extract_domain(website: str, email: str) -> str:
    if website:
        cleaned = re.sub(r"^https?://(www\.)?", "", website).split("/")[0].strip().lower()
        if cleaned:
            return cleaned
    if email and "@" in email:
        return email.split("@")[1].strip().lower()
    return ""

def main():
    print("--- Avvio Importazione Broker da fonti Open-Source ---")
    
    # 1. Carica i broker attuali
    existing_brokers = []
    if os.path.exists(BROKERS_JSON_PATH):
        with open(BROKERS_JSON_PATH, "r", encoding="utf-8") as f:
            existing_brokers = json.load(f)
            
    print(f"Broker esistenti nel database: {len(existing_brokers)}")
    
    existing_domains = {b.get("domain", "").lower() for b in existing_brokers if b.get("domain")}
    existing_emails = {b.get("email", "").lower() for b in existing_brokers if b.get("email")}
    existing_ids = {b.get("id", "").lower() for b in existing_brokers if b.get("id")}
    
    # 2. Scarica il dataset di Eraser
    print(f"Scaricamento dataset da {ERASER_YAML_URL}...")
    req = urllib.request.Request(ERASER_YAML_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        yaml_content = resp.read().decode("utf-8")
        
    eraser_items = parse_simple_yaml(yaml_content)
    print(f"Broker estratti da Eraser: {len(eraser_items)}")
    
    # 3. Merge e deduplicazione
    added_count = 0
    for item in eraser_items:
        email = item.get("email", "").strip().lower()
        if not email or "@" not in email:
            continue
            
        name = item.get("name", "").strip() or item.get("id", "").capitalize()
        website = item.get("website", "")
        domain = extract_domain(website, email)
        
        # Deduplica
        if email in existing_emails or (domain and domain in existing_domains):
            continue
            
        broker_id = item.get("id", "").strip().lower()
        if not broker_id or broker_id in existing_ids:
            broker_id = domain.replace(".", "_") if domain else f"broker_{len(existing_brokers) + added_count}"
            
        region = item.get("region", "global").upper()
        category = item.get("category", "Data Broker").replace("-", " ").title()
        
        entry = {
            "id": broker_id,
            "name": name,
            "domain": domain,
            "email": email,
            "country": region,
            "category": category
        }
        
        opt_out = item.get("opt_out_url")
        if opt_out:
            entry["opt_out_url"] = opt_out
            
        existing_brokers.append(entry)
        existing_emails.add(email)
        if domain:
            existing_domains.add(domain)
        existing_ids.add(broker_id)
        added_count += 1
        
    print(f"Nuovi broker unici aggiunti: {added_count}")
    print(f"Totale broker aggregati: {len(existing_brokers)}")
    
    # 4. Salva il file brokers.json aggiornato
    with open(BROKERS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(existing_brokers, f, indent=2, ensure_ascii=False)
        
    print(f"File salvato con successo in {BROKERS_JSON_PATH}")

if __name__ == "__main__":
    main()
