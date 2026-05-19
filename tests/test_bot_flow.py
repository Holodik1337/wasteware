from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wasteware_bot.app import BotApp
from wasteware_bot.config import Settings
from wasteware_bot.domain import CallbackContext, MessageContext, TelegramUser
from wasteware_bot.storage import Storage


class FakeTelegram:
    def __init__(self):
        self.messages = []
        self.callbacks = []

    def send_message(self, chat_id, text, keyboard=None, disable_web_page_preview=True):
        self.messages.append({"chat_id": chat_id, "text": text, "keyboard": keyboard})
        return {"message_id": len(self.messages)}

    def answer_callback(self, callback_id, text=None, alert=False):
        self.callbacks.append((callback_id, text, alert))


def settings(tmp_path: Path) -> Settings:
    return Settings(
        token="test-token",
        admin_ids={777},
        database_path=tmp_path / "bot.sqlite3",
        public_site_url="https://example.test",
        portfolio_url="https://t.me/portfolio",
        price_url="https://t.me/price",
        contact_username="wasteware",
    )


def user(user_id=100) -> TelegramUser:
    return TelegramUser(id=user_id, username=f"u{user_id}", first_name="Test", last_name=None, language_code="ru")


def message(text: str, user_id=100) -> MessageContext:
    return MessageContext(chat_id=user_id, message_id=1, user=user(user_id), text=text, payload={})


def callback(data: str, user_id=100) -> CallbackContext:
    return CallbackContext(id=f"cb-{data}", chat_id=user_id, message_id=1, user=user(user_id), data=data, payload={})


def make_app(tmp_path: Path):
    cfg = settings(tmp_path)
    storage = Storage(cfg.database_path)
    fake = FakeTelegram()
    return BotApp(cfg, storage, fake), storage, fake


class BotFlowTest(unittest.TestCase):
    def run_with_tmpdir(self, test):
        with tempfile.TemporaryDirectory() as directory:
            return test(Path(directory))

    def test_start_renders_main_menu(self):
        def scenario(tmp_path: Path):
            app, storage, fake = make_app(tmp_path)
            app(message("/start"))
            self.assertEqual(storage.user(100)["username"], "u100")
            self.assertIn("Edit Studio", fake.messages[-1]["text"])
            self.assertEqual(fake.messages[-1]["keyboard"][0][0].text, "Заказать эдит")

        self.run_with_tmpdir(scenario)

    def test_order_flow_creates_ticket_and_notifies_admin(self):
        def scenario(tmp_path: Path):
            app, storage, fake = make_app(tmp_path)
            app(message("/order"))
            app(callback("order:style:km"))
            app(message("30 сек"))
            app(message("завтра"))
            app(callback("order:skip_refs"))
            app(callback("order:budget:500–1000 ₽"))
            app(message("@client"))
            app(message("мрачный стиль, быстрые переходы"))
            app(callback("order:confirm"))

            tickets = storage.user_tickets(100)
            self.assertEqual(len(tickets), 1)
            data = json.loads(tickets[0]["data"])
            self.assertEqual(data["style"], "km")
            self.assertEqual(data["duration"], "30 сек")
            self.assertEqual(fake.messages[-1]["chat_id"], 777)
            self.assertIn("Новая заявка", fake.messages[-1]["text"])

        self.run_with_tmpdir(scenario)

    def test_admin_can_change_ticket_status(self):
        def scenario(tmp_path: Path):
            app, storage, fake = make_app(tmp_path)
            storage.upsert_user(user(100))
            ticket_id = storage.create_ticket(100, {"style": "km"})
            app(callback(f"admin:set:in_work:{ticket_id}", user_id=777))
            self.assertEqual(storage.ticket(ticket_id)["status"], "in_work")
            self.assertTrue(any(msg["chat_id"] == 100 and "взяли в работу" in msg["text"] for msg in fake.messages))

        self.run_with_tmpdir(scenario)


if __name__ == "__main__":
    unittest.main()
