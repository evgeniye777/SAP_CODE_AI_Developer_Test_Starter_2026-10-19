import sqlite3
import os

def _prepare_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            customer TEXT NOT NULL,
            message TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL
        );
        """
    )

def process_event(event: dict, db_path: str) -> dict:
    """Принимает событие и возвращает dict со статусом и, при успехе, id заявки.

    Контракт статусов и бизнес-правила описаны в README.md.
    """
    db_path = os.path.abspath(db_path)

    with sqlite3.connect(db_path) as connection:
        _prepare_db(connection)

        # 1. Получаем "сырые" данные БЕЗ .strip()
        source = event.get("source", "")
        external_id = event.get("external_id", "")
        customer = event.get("customer", "")
        message = event.get("message", "")

        # 2. Валидация типов и обязательности (ДО обрезки пробелов)
        if not isinstance(external_id, str):
            return {"status": "invalid", "reason": "external_id must be a string"}
        
        # Проверяем остальные поля на тип строки, чтобы избежать таких же ошибок
        if not isinstance(source, str):
            return {"status": "invalid", "reason": "source must be a string"}
        if not isinstance(customer, str):
            return {"status": "invalid", "reason": "customer must be a string"}
        if not isinstance(message, str):
            return {"status": "invalid", "reason": "message must be a string"}

        # 3. Теперь безопасно применяем .strip()
        source = source.strip()
        external_id = external_id.strip()
        customer = customer.strip()
        message = message.strip()

        # 4. Валидация на пустоту (после обрезки)
        if not source:
            return {"status": "invalid", "reason": "Source is required"}
        if not external_id:
            return {"status": "invalid", "reason": "External ID is required"}
        if not customer:
            return {"status": "invalid", "reason": "Customer is required"}
        if not message:
            return {"status": "invalid", "reason": "Message is required"}

        # 5. Бизнес-логика (дедупликация и вставка)
        cursor = connection.execute(
            "SELECT id FROM leads WHERE source = ? AND external_id = ?", 
            (source, external_id)
        )
        existing_lead = cursor.fetchone()

        if existing_lead:
            return {"status": "duplicate", "id": existing_lead[0]}

        cursor = connection.execute(
            """
            INSERT INTO leads (source, external_id, customer, message)
            VALUES (?, ?, ?, ?)
            """,
            (source, external_id, customer, message),
        )
        lead_id = cursor.lastrowid
        
        connection.execute(
            "INSERT INTO notifications (lead_id) VALUES (?)", (lead_id,)
        )
        
        return {"status": "created", "id": lead_id}