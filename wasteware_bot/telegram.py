from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .domain import Button, CallbackContext, MessageContext, TelegramUser

log = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str):
        self.base_url = f"https://api.telegram.org/bot{token}"

    def request(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"Telegram HTTP {exc.code}: {text}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(f"Telegram network error: {exc}") from exc
        if not data.get("ok"):
            raise TelegramError(str(data))
        return data["result"]

    def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self.request("getUpdates", payload)

    def send_message(
        self,
        chat_id: int,
        text: str,
        keyboard: list[list[Button]] | None = None,
        disable_web_page_preview: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_web_page_preview,
        }
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": [[button_payload(b) for b in row] for row in keyboard]}
        return self.request("sendMessage", payload)

    def edit_message(self, chat_id: int, message_id: int, text: str, keyboard: list[list[Button]] | None = None) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": [[button_payload(b) for b in row] for row in keyboard]}
        self.request("editMessageText", payload)

    def answer_callback(self, callback_id: str, text: str | None = None, alert: bool = False) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_id, "show_alert": alert}
        if text:
            payload["text"] = text
        self.request("answerCallbackQuery", payload)

    def set_commands(self) -> None:
        commands = [
            {"command": "start", "description": "Главное меню"},
            {"command": "order", "description": "Оформить заказ на эдит"},
            {"command": "price", "description": "Прайс"},
            {"command": "portfolio", "description": "Портфолио"},
            {"command": "status", "description": "Статус моих заказов"},
            {"command": "help", "description": "Помощь"},
        ]
        self.request("setMyCommands", {"commands": commands})


def button_payload(button: Button) -> dict[str, str]:
    payload = {"text": button.text}
    if button.url:
        payload["url"] = button.url
    if button.callback_data:
        payload["callback_data"] = button.callback_data
    return payload


def parse_user(raw: dict[str, Any]) -> TelegramUser:
    return TelegramUser(
        id=int(raw["id"]),
        username=raw.get("username"),
        first_name=raw.get("first_name"),
        last_name=raw.get("last_name"),
        language_code=raw.get("language_code"),
    )


def parse_message(update: dict[str, Any]) -> MessageContext | CallbackContext | None:
    if "message" in update:
        message = update["message"]
        if "from" not in message or "chat" not in message:
            return None
        return MessageContext(
            chat_id=int(message["chat"]["id"]),
            message_id=message.get("message_id"),
            user=parse_user(message["from"]),
            text=(message.get("text") or message.get("caption") or "").strip(),
            payload=message,
        )
    if "callback_query" in update:
        callback = update["callback_query"]
        message = callback.get("message") or {}
        return CallbackContext(
            id=callback["id"],
            chat_id=int(message.get("chat", {}).get("id", callback["from"]["id"])),
            message_id=message.get("message_id"),
            user=parse_user(callback["from"]),
            data=callback.get("data", ""),
            payload=callback,
        )
    return None


class Poller:
    def __init__(self, client: TelegramClient, handler, timeout: int):
        self.client = client
        self.handler = handler
        self.timeout = timeout
        self.offset: int | None = None
        self.running = True

    def run(self) -> None:
        log.info("Bot polling started")
        while self.running:
            try:
                updates = self.client.get_updates(self.offset, self.timeout)
            except TelegramError:
                log.exception("Cannot fetch Telegram updates")
                time.sleep(5)
                continue
            for update in updates:
                self.offset = int(update["update_id"]) + 1
                parsed = parse_message(update)
                if parsed is None:
                    continue
                try:
                    self.handler(parsed)
                except Exception:
                    log.exception("Unhandled update: %s", update)

