import sqlite3
import os

DB_PATH = "leads.db"

def _initialize_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                customer TEXT NOT NULL,
                message TEXT NOT NULL,
                UNIQUE(source, external_id) 
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                FOREIGN KEY(lead_id) REFERENCES leads(id)
            );
        """)
        conn.commit()
    finally:
        conn.close()

# Инициализация при импорте
_initialize_db()


def process_event(event: dict, db_path: str = DB_PATH) -> dict:
    # --- 1. ВАЛИДАЦИЯ ---
    required_fields = ["source", "external_id", "customer", "message"]
    for field in required_fields:
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            return {"status": "invalid"}

    # --- 2. НОРМАЛИЗАЦИЯ (Обрезаем пробелы СРАЗУ) ---
    source = event["source"].strip()
    external_id = event["external_id"].strip()
    customer = event["customer"].strip()
    message = event["message"].strip()

    # --- 3. РАБОТА С БАЗОЙ (используем уже ЧИСТЫЕ переменные) ---
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Поиск дубликата по ОЧИЩЕННЫМ данным
        cur.execute(
            "SELECT id FROM leads WHERE source = ? AND external_id = ?", 
            (source, external_id)
        )
        row = cur.fetchone()
        
        if row:
            conn.close()
            return {"status": "duplicate", "id": row["id"]}

        # Создание новой записи
        cur.execute(
            "INSERT INTO leads (source, external_id, customer, message) VALUES (?, ?, ?, ?)",
            (source, external_id, customer, message)
        )
        lead_id = cur.lastrowid

        # Создание уведомления
        cur.execute("INSERT INTO notifications (lead_id) VALUES (?)", (lead_id,))
        
        conn.commit()
        conn.close()
        
        return {"status": "created", "id": lead_id}

    except Exception as e:
        return {"status": "error"}