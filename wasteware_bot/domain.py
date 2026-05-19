from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"


class TicketStatus(StrEnum):
    DRAFT = "draft"
    NEW = "new"
    IN_WORK = "in_work"
    WAITING_CLIENT = "waiting_client"
    DONE = "done"
    CANCELED = "canceled"


class OrderStep(StrEnum):
    STYLE = "style"
    DURATION = "duration"
    DEADLINE = "deadline"
    REFERENCES = "references"
    BUDGET = "budget"
    CONTACT = "contact"
    COMMENT = "comment"
    CONFIRM = "confirm"


ORDER_STEPS = [
    OrderStep.STYLE,
    OrderStep.DURATION,
    OrderStep.DEADLINE,
    OrderStep.REFERENCES,
    OrderStep.BUDGET,
    OrderStep.CONTACT,
    OrderStep.COMMENT,
    OrderStep.CONFIRM,
]

STYLE_PRESETS = {
    "km": "КМ эдит / динамичный монтаж под музыку",
    "film": "Киношный эдит / атмосферная нарезка",
    "manga": "Манга / аниме стиль",
    "cars": "Автомобильный эдит",
    "ads": "Рекламный ролик / промо",
    "other": "Другое / обсудим отдельно",
}

PRICE_CATALOG = [
    ("Быстрый TikTok/Reels эдит", "до 20 сек", "от 300 ₽"),
    ("КМ эдит", "20–45 сек", "от 600 ₽"),
    ("Кино/манга эдит", "30–60 сек", "от 900 ₽"),
    ("Авто/спорт эдит", "30–60 сек", "от 800 ₽"),
    ("Промо для канала/бренда", "до 90 сек", "от 1500 ₽"),
    ("Срочный заказ", "вне очереди", "+50%"),
]

FAQ = {
    "how_long": ("Сколько занимает монтаж?", "Обычно 1–3 дня. Срочные заказы можно обсудить отдельно."),
    "source": ("Что нужно прислать?", "Видео/фото, музыку, референсы, дедлайн и пожелания по стилю."),
    "payment": ("Как оплата?", "После согласования ТЗ. Для крупных заказов возможна предоплата."),
    "edits": ("Правки входят?", "Одна небольшая правка входит в цену, большие переделки обсуждаются отдельно."),
    "formats": ("В каких форматах отдаёшь?", "MP4 под TikTok, Reels, Shorts или другой формат по запросу."),
}


@dataclass(frozen=True)
class Button:
    text: str
    callback_data: str | None = None
    url: str | None = None


Keyboard = list[list[Button]]


@dataclass
class TelegramUser:
    id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None

    @property
    def mention(self) -> str:
        if self.username:
            return f"@{self.username}"
        name = " ".join(part for part in [self.first_name, self.last_name] if part)
        return name or str(self.id)


@dataclass
class MessageContext:
    chat_id: int
    message_id: int | None
    user: TelegramUser
    text: str
    payload: dict[str, Any]


@dataclass
class CallbackContext:
    id: str
    chat_id: int
    message_id: int | None
    user: TelegramUser
    data: str
    payload: dict[str, Any]


def money_table() -> str:
    rows = ["<b>Прайс Edit Studio</b>", ""]
    for title, details, price in PRICE_CATALOG:
        rows.append(f"• <b>{title}</b> — {details}: <code>{price}</code>")
    rows.append("")
    rows.append("Точная цена зависит от исходников, дедлайна и количества правок.")
    return "\n".join(rows)


def faq_text() -> str:
    lines = ["<b>FAQ</b>", ""]
    for question, answer in FAQ.values():
        lines.append(f"<b>{question}</b>\n{answer}\n")
    return "\n".join(lines).strip()


def order_summary(data: dict[str, Any]) -> str:
    style = STYLE_PRESETS.get(str(data.get("style", "")), data.get("style", "—"))
    fields = [
        ("Стиль", style),
        ("Длительность", data.get("duration", "—")),
        ("Дедлайн", data.get("deadline", "—")),
        ("Референсы", data.get("references", "—")),
        ("Бюджет", data.get("budget", "—")),
        ("Контакт", data.get("contact", "—")),
        ("Комментарий", data.get("comment", "—")),
    ]
    return "\n".join(f"<b>{name}:</b> {value}" for name, value in fields)

