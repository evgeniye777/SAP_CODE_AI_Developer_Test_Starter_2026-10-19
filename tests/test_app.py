import sys
import os
import tempfile
import unittest
from pathlib import Path

# Добавляем родительскую папку, чтобы Python увидел файл app.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import process_event

# Базовые валидные данные для тестов
GOOD = {
    "source": "telegram",
    "external_id": "event-100",
    "customer": "Иван Иванов",
    "message": "Нужна доставка в Казань",
}

class LeadProcessorTests(unittest.TestCase):
    def setUp(self):
        # Используем временную БД, чтобы не засорять основную leads.db
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "leads_test.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    # --- ОСНОВНЫЕ СЦЕНАРИИ (уже были у вас) ---

    def test_new_lead_creates_record(self):
        """Проверка успешного создания новой заявки"""
        response = process_event(dict(GOOD), self.db_path)
        self.assertEqual(response["status"], "created")
        self.assertIsInstance(response["id"], int)

    def test_duplicate_lead_is_detected(self):
        """Проверка дедупликации: второй лид с теми же source+external_id должен быть дубликатом"""
        first = process_event(dict(GOOD), self.db_path)
        second = process_event(dict(GOOD), self.db_path)
        
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(second["id"], first["id"])

    def test_different_source_is_new_lead(self):
        """Проверка того, что другой source создает новую заявку"""
        first = process_event(dict(GOOD), self.db_path)
        second = process_event({**GOOD, "source": "max"}, self.db_path)
        
        self.assertEqual(second["status"], "created")
        self.assertNotEqual(first["id"], second["id"])

    def test_missing_required_field_is_invalid(self):
        """Проверка валидации: пустое поле customer делает заявку невалидной"""
        result = process_event({**GOOD, "customer": "   "}, self.db_path)
        self.assertEqual(result["status"], "invalid")

    def test_non_string_field_is_invalid(self):
        """Проверка типов данных: external_id должен быть строкой"""
        response = process_event({**GOOD, "external_id": 100}, self.db_path)
        self.assertEqual(response["status"], "invalid")

    def test_whitespace_is_trimmed(self):
        """Проверка обрезки пробелов: ' telegram ' == 'telegram'"""
        first = process_event({**GOOD, "source": " telegram ", "external_id": " event-100 "}, self.db_path)
        second = process_event(dict(GOOD), self.db_path)
        
        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(first["id"], second["id"])

    def test_data_immutability_on_retry(self):
        """Проверка, что при дубликате данные не обновляются (сохраняется первая версия)"""
        first = process_event(dict(GOOD), self.db_path)
        
        # Пытаемся прислать другие данные для того же ID
        response = process_event({
            **GOOD, 
            "customer": "Другой Клиент", 
            "message": "Измененный текст"
        }, self.db_path)
        
        self.assertEqual(response["status"], "duplicate")
        
        # Проверяем в БД, что данные остались старыми
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT customer, message FROM leads WHERE id=?", (first["id"],)).fetchone()
        self.assertEqual(row, (GOOD["customer"], GOOD["message"]))

    # --- НОВЫЕ ТЕСТЫ (EDGE CASES) ---

    def test_sql_injection_protection(self):
        """Проверка защиты от SQL-инъекций: вредоносный код не должен ломать БД"""
        malicious_payload = "1'); DROP TABLE leads; --"
        
        # 1. Создаем запись с вредоносным кодом в message
        res1 = process_event({
            "source": "sec", "external_id": "inj1", 
            "customer": "Hacker", "message": malicious_payload
        }, self.db_path)
        self.assertEqual(res1["status"], "created")

        # 2. Пытаемся создать дубликат. Если бы таблицу удалили, была бы ошибка.
        res2 = process_event({
            "source": "sec", "external_id": "inj1", 
            "customer": "Hacker2", "message": "test"
        }, self.db_path)
        
        self.assertEqual(res2["status"], "duplicate")

    def test_very_long_message(self):
        """Стресс-тест: обработка очень длинного сообщения (5000 символов)"""
        long_text = "A" * 5000
        
        response = process_event({
            "source": "long", 
            "external_id": "long1", 
            "customer": "Big Text", 
            "message": long_text
        }, self.db_path)
        
        self.assertEqual(response["status"], "created")
        self.assertIsInstance(response["id"], int)

    def test_special_characters_in_customer(self):
        """Проверка работы с спецсимволами и Unicode в имени клиента"""
        special = {**GOOD, "customer": "Иван #$%^&*()_+ Иванов"}
        
        response = process_event(special, self.db_path)
        self.assertEqual(response["status"], "created")
        
        # Проверка дубликата
        response2 = process_event(special, self.db_path)
        self.assertEqual(response2["status"], "duplicate")


if __name__ == "__main__":
    unittest.main()