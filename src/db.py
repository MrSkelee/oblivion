import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "privacy_vault.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS brokers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            domain TEXT NOT NULL,
            email TEXT NOT NULL,
            country TEXT,
            category TEXT,
            status TEXT DEFAULT 'PENDING', -- PENDING, SENT, IN_REVIEW, CONFIRMED, REFUSED
            last_contacted_at TEXT,
            confirmed_at TEXT,
            notes TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker_id TEXT,
            direction TEXT NOT NULL, -- OUTGOING, INCOMING
            subject TEXT,
            body TEXT,
            classification TEXT, -- SUCCESS, OPT_OUT_LINK, VERIFICATION_REQUIRED, REJECTED, UNKNOWN
            detected_link TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (broker_id) REFERENCES brokers(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            breach_title TEXT NOT NULL,
            breach_date TEXT,
            data_classes TEXT, -- JSON array of leaked fields
            is_resolved INTEGER DEFAULT 0,
            detected_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def seed_brokers(json_path=None):
    if json_path is None:
        json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "brokers.json")

    if not os.path.exists(json_path):
        return 0

    with open(json_path, "r", encoding="utf-8") as f:
        brokers = json.load(f)

    conn = get_db()
    cursor = conn.cursor()
    inserted = 0

    for b in brokers:
        cursor.execute("""
            INSERT OR IGNORE INTO brokers (id, name, domain, email, country, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (b["id"], b["name"], b["domain"], b["email"], b.get("country", ""), b.get("category", "")))
        if cursor.rowcount > 0:
            inserted += 1

    conn.commit()
    conn.close()
    return inserted

def get_pending_brokers(limit=5):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM brokers WHERE status = 'PENDING' LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_broker_status(broker_id, status, notes=None):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    if status == 'CONFIRMED':
        cursor.execute("UPDATE brokers SET status = ?, confirmed_at = ?, notes = ? WHERE id = ?", (status, now, notes, broker_id))
    elif status == 'SENT':
        cursor.execute("UPDATE brokers SET status = ?, last_contacted_at = ?, notes = ? WHERE id = ?", (status, now, notes, broker_id))
    else:
        cursor.execute("UPDATE brokers SET status = ?, notes = ? WHERE id = ?", (status, notes, broker_id))
    conn.commit()
    conn.close()

def record_interaction(broker_id, direction, subject, body, classification=None, detected_link=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO interactions (broker_id, direction, subject, body, classification, detected_link)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (broker_id, direction, subject, body, classification, detected_link))
    interaction_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return interaction_id

def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, count(*) as count FROM brokers GROUP BY status")
    stats = {r["status"]: r["count"] for r in cursor.fetchall()}
    cursor.execute("SELECT count(*) as count FROM leaks WHERE is_resolved = 0")
    active_leaks = cursor.fetchone()["count"]
    conn.close()
    return {
        "pending": stats.get("PENDING", 0),
        "sent": stats.get("SENT", 0),
        "confirmed": stats.get("CONFIRMED", 0),
        "refused": stats.get("REFUSED", 0),
        "active_leaks": active_leaks
    }
