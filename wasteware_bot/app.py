from __future__ import annotations

import html
import json
import logging
import re
from typing import Any

from .config import Settings
from .domain import (
    FAQ,
    ORDER_STEPS,
    STYLE_PRESETS,
    Button,
    CallbackContext,
    MessageContext,
    OrderStep,
    TicketStatus,
    faq_text,
    money_table,
    order_summary,
)
from .storage import Storage
from .telegram import TelegramClient, TelegramError

log = logging.getLogger(__name__)


class BotApp:
    def __init__(self, settings: Settings, storage: Storage, telegram: TelegramClient):
        self.settings = settings
        self.storage = storage
        self.telegram = telegram

    def __call__(self, ctx: MessageContext | CallbackContext) -> None:
        is_admin = ctx.user.id in self.settings.admin_ids
        self.storage.upsert_user(ctx.user, is_admin=is_admin)
        user = self.storage.user(ctx.user.id)
        if user and user["banned"]:
            return
        if isinstance(ctx, CallbackContext):
            self.handle_callback(ctx)
        else:
            self.handle_message(ctx)

    def send(self, chat_id: int, text: str, keyboard: list[list[Button]] | None = None) -> None:
        self.telegram.send_message(chat_id, text, keyboard=keyboard)

    def safe_send(self, chat_id: int, text: str, keyboard: list[list[Button]] | None = None) -> bool:
        try:
            self.send(chat_id, text, keyboard)
            return True
        except TelegramError:
            log.exception("Failed to send message to %s", chat_id)
            return False

    def handle_message(self, ctx: MessageContext) -> None:
        text = ctx.text.strip()
        command = text.split(maxsplit=1)[0].lower() if text.startswith("/") else ""
        if command in {"/start", "/menu"}:
            self.storage.clear_session(ctx.user.id)
            self.show_home(ctx.chat_id, ctx.user.first_name)
            return
        if command == "/help":
            self.show_help(ctx.chat_id)
            return
        if command == "/price":
            self.show_price(ctx.chat_id)
            return
        if command == "/portfolio":
            self.show_portfolio(ctx.chat_id)
            return
        if command == "/order":
            self.start_order(ctx.chat_id, ctx.user.id)
            return
        if command == "/status":
            self.show_status(ctx.chat_id, ctx.user.id)
            return
        if command == "/admin" and self.is_admin(ctx.user.id):
            self.show_admin(ctx.chat_id)
            return
        if self.is_admin(ctx.user.id) and self.try_admin_text_command(ctx):
            return
        session = self.storage.get_session(ctx.user.id)
        if session:
            self.continue_session(ctx, session)
            return
        self.send(
            ctx.chat_id,
            "Я понял текст, но не понял задачу. Нажми кнопку ниже или напиши /order, чтобы оформить заказ.",
            self.main_keyboard(),
        )

    def handle_callback(self, ctx: CallbackContext) -> None:
        data = ctx.data
        try:
            self.telegram.answer_callback(ctx.id)
        except TelegramError:
            log.exception("Cannot answer callback")
        if data == "home":
            self.storage.clear_session(ctx.user.id)
            self.show_home(ctx.chat_id, ctx.user.first_name)
        elif data == "order:start":
            self.start_order(ctx.chat_id, ctx.user.id)
        elif data.startswith("order:style:"):
            style = data.rsplit(":", 1)[-1]
            self.set_order_value(ctx.chat_id, ctx.user.id, OrderStep.STYLE, style)
        elif data.startswith("order:budget:"):
            budget = data.rsplit(":", 1)[-1]
            self.set_order_value(ctx.chat_id, ctx.user.id, OrderStep.BUDGET, budget)
        elif data == "order:skip_refs":
            self.set_order_value(ctx.chat_id, ctx.user.id, OrderStep.REFERENCES, "без референсов")
        elif data == "order:skip_comment":
            self.set_order_value(ctx.chat_id, ctx.user.id, OrderStep.COMMENT, "—")
        elif data == "order:confirm":
            self.confirm_order(ctx.chat_id, ctx.user.id)
        elif data == "order:cancel":
            self.storage.clear_session(ctx.user.id)
            self.send(ctx.chat_id, "Ок, черновик заказа удалён.", self.main_keyboard())
        elif data == "price":
            self.show_price(ctx.chat_id)
        elif data == "portfolio":
            self.show_portfolio(ctx.chat_id)
        elif data == "faq":
            self.send(ctx.chat_id, faq_text(), self.back_keyboard())
        elif data == "status":
            self.show_status(ctx.chat_id, ctx.user.id)
        elif data == "admin" and self.is_admin(ctx.user.id):
            self.show_admin(ctx.chat_id)
        elif data.startswith("admin:ticket:") and self.is_admin(ctx.user.id):
            ticket_id = int(data.rsplit(":", 1)[-1])
            self.show_ticket_admin(ctx.chat_id, ticket_id)
        elif data.startswith("admin:set:") and self.is_admin(ctx.user.id):
            _, _, status, ticket_id = data.split(":")
            self.change_ticket_status(ctx.chat_id, ctx.user.id, int(ticket_id), TicketStatus(status))
        else:
            self.send(ctx.chat_id, "Кнопка устарела. Открыл главное меню.", self.main_keyboard())

    def try_admin_text_command(self, ctx: MessageContext) -> bool:
        text = ctx.text.strip()
        if text.startswith("/broadcast "):
            body = text.removeprefix("/broadcast ").strip()
            self.broadcast(ctx.chat_id, ctx.user.id, body)
            return True
        if text.startswith("/reply "):
            match = re.match(r"/reply\s+(\d+)\s+(.+)", text, flags=re.S)
            if not match:
                self.send(ctx.chat_id, "Формат: <code>/reply ID текст</code>")
                return True
            self.reply_to_ticket(ctx.chat_id, ctx.user.id, int(match.group(1)), match.group(2).strip())
            return True
        if text.startswith("/note "):
            match = re.match(r"/note\s+(\d+)\s+(.+)", text, flags=re.S)
            if not match:
                self.send(ctx.chat_id, "Формат: <code>/note ID заметка</code>")
                return True
            ok = self.storage.set_ticket_status(int(match.group(1)), TicketStatus.IN_WORK, ctx.user.id, match.group(2).strip())
            self.send(ctx.chat_id, "Заметка сохранена." if ok else "Заказ не найден.")
            return True
        return False

    def continue_session(self, ctx: MessageContext, session: dict[str, Any]) -> None:
        if session["mode"] == "order":
            step = OrderStep(session["step"])
            self.set_order_value(ctx.chat_id, ctx.user.id, step, ctx.text)
            return
        self.storage.clear_session(ctx.user.id)
        self.send(ctx.chat_id, "Сессия сброшена. Начни заново.", self.main_keyboard())

    def show_home(self, chat_id: int, first_name: str | None) -> None:
        name = html.escape(first_name or "друг")
        site = f"\nСайт: {html.escape(self.settings.public_site_url)}" if self.settings.public_site_url else ""
        self.send(
            chat_id,
            (
                f"<b>Йо, {name}. Это бот Edit Studio.</b>\n\n"
                "Здесь можно быстро заказать эдит, открыть портфолио, посмотреть прайс и не потерять ТЗ в личке."
                f"{site}"
            ),
            self.main_keyboard(),
        )

    def show_help(self, chat_id: int) -> None:
        self.send(
            chat_id,
            (
                "<b>Что умею</b>\n"
                "• принимаю ТЗ на монтаж по шагам\n"
                "• показываю прайс и портфолио\n"
                "• сохраняю заявки в SQLite\n"
                "• даю админу статусы, ответы клиентам и рассылки\n\n"
                "Команды: /order /price /portfolio /status /help"
            ),
            self.main_keyboard(),
        )

    def show_price(self, chat_id: int) -> None:
        keyboard = [[Button("Открыть полный прайс", url=self.settings.price_url)], [Button("Заказать", "order:start")]]
        self.send(chat_id, money_table(), keyboard)

    def show_portfolio(self, chat_id: int) -> None:
        keyboard = [[Button("Открыть портфолио", url=self.settings.portfolio_url)], [Button("Заказать такой же", "order:start")]]
        self.send(chat_id, "<b>Портфолио</b>\nЖми кнопку и смотри примеры работ в Telegram.", keyboard)

    def show_status(self, chat_id: int, user_id: int) -> None:
        tickets = self.storage.user_tickets(user_id)
        if not tickets:
            self.send(chat_id, "У тебя пока нет заказов. Самое время это исправить.", [[Button("Оформить заказ", "order:start")]])
            return
        lines = ["<b>Твои заказы</b>", ""]
        for ticket in tickets:
            lines.append(f"#{ticket['id']} — <code>{ticket['status']}</code>")
        self.send(chat_id, "\n".join(lines), self.main_keyboard())

    def start_order(self, chat_id: int, user_id: int) -> None:
        self.storage.set_session(user_id, "order", OrderStep.STYLE.value, {})
        keyboard = [[Button(label, f"order:style:{key}")] for key, label in STYLE_PRESETS.items()]
        keyboard.append([Button("Отмена", "order:cancel")])
        self.send(chat_id, "<b>Шаг 1/8.</b> Выбери стиль эдита.", keyboard)

    def set_order_value(self, chat_id: int, user_id: int, step: OrderStep, value: str) -> None:
        session = self.storage.get_session(user_id) or {"mode": "order", "step": step.value, "data": {}}
        data = dict(session.get("data") or {})
        data[step.value] = html.escape(value.strip()[:1500]) if isinstance(value, str) else value
        next_step = self.next_step(step)
        if next_step is None:
            self.storage.set_session(user_id, "order", OrderStep.CONFIRM.value, data)
            self.ask_confirm(chat_id, data)
            return
        self.storage.set_session(user_id, "order", next_step.value, data)
        self.ask_step(chat_id, next_step)

    def next_step(self, current: OrderStep) -> OrderStep | None:
        index = ORDER_STEPS.index(current)
        if index >= len(ORDER_STEPS) - 2:
            return None
        return ORDER_STEPS[index + 1]

    def ask_step(self, chat_id: int, step: OrderStep) -> None:
        prompts = {
            OrderStep.DURATION: ("<b>Шаг 2/8.</b> Какая длительность ролика? Например: 15 сек, 30 сек, 1 мин.", None),
            OrderStep.DEADLINE: ("<b>Шаг 3/8.</b> К какому дедлайну нужно сделать?", None),
            OrderStep.REFERENCES: ("<b>Шаг 4/8.</b> Пришли ссылки на референсы или нажми “без референсов”.", [[Button("Без референсов", "order:skip_refs")]]),
            OrderStep.BUDGET: ("<b>Шаг 5/8.</b> Какой бюджет?", [[Button("до 500 ₽", "order:budget:до 500 ₽"), Button("500–1000 ₽", "order:budget:500–1000 ₽")], [Button("1000–2000 ₽", "order:budget:1000–2000 ₽"), Button("2000+ ₽", "order:budget:2000+ ₽")]]),
            OrderStep.CONTACT: ("<b>Шаг 6/8.</b> Куда написать для обсуждения? Telegram username, номер или другой контакт.", None),
            OrderStep.COMMENT: ("<b>Шаг 7/8.</b> Дополнительные пожелания: музыка, настроение, цвет, текст, эффекты. Можно пропустить.", [[Button("Пропустить", "order:skip_comment")]]),
        }
        text, keyboard = prompts[step]
        keyboard = (keyboard or []) + [[Button("Отмена", "order:cancel")]]
        self.send(chat_id, text, keyboard)

    def ask_confirm(self, chat_id: int, data: dict[str, Any]) -> None:
        self.send(
            chat_id,
            f"<b>Шаг 8/8. Проверь заказ</b>\n\n{order_summary(data)}",
            [[Button("Отправить", "order:confirm")], [Button("Заполнить заново", "order:start"), Button("Отмена", "order:cancel")]],
        )

    def confirm_order(self, chat_id: int, user_id: int) -> None:
        session = self.storage.get_session(user_id)
        if not session or session.get("mode") != "order":
            self.send(chat_id, "Черновик не найден. Начни заново.", [[Button("Оформить заказ", "order:start")]])
            return
        ticket_id = self.storage.create_ticket(user_id, session.get("data") or {})
        self.storage.clear_session(user_id)
        self.send(chat_id, f"Заявка <b>#{ticket_id}</b> отправлена. Я напишу, когда её возьмут в работу.", self.main_keyboard())
        self.notify_admins(ticket_id)

    def notify_admins(self, ticket_id: int) -> None:
        ticket = self.storage.ticket(ticket_id)
        if not ticket:
            return
        user = self.storage.user(ticket["user_id"])
        data = json.loads(ticket["data"])
        owner = user["username"] and f"@{user['username']}" or str(ticket["user_id"])
        text = f"<b>Новая заявка #{ticket_id}</b> от {html.escape(owner)}\n\n{order_summary(data)}"
        for admin_id in self.settings.admin_ids:
            self.safe_send(admin_id, text, self.ticket_keyboard(ticket_id))

    def show_admin(self, chat_id: int) -> None:
        stats = self.storage.stats()
        tickets = self.storage.tickets_by_status([TicketStatus.NEW, TicketStatus.IN_WORK, TicketStatus.WAITING_CLIENT], limit=10)
        lines = [
            "<b>Админка Edit Studio</b>",
            "",
            f"Пользователей: <code>{stats['users']}</code>",
            f"Новых: <code>{stats[TicketStatus.NEW.value]}</code>",
            f"В работе: <code>{stats[TicketStatus.IN_WORK.value]}</code>",
            f"Готово: <code>{stats[TicketStatus.DONE.value]}</code>",
            "",
            "Команды:",
            "<code>/reply ID текст</code> — ответить клиенту",
            "<code>/broadcast текст</code> — рассылка",
            "<code>/note ID текст</code> — заметка и статус in_work",
        ]
        keyboard = [[Button(f"#{ticket['id']} — {ticket['status']}", f"admin:ticket:{ticket['id']}")] for ticket in tickets]
        self.send(chat_id, "\n".join(lines), keyboard or None)

    def show_ticket_admin(self, chat_id: int, ticket_id: int) -> None:
        ticket = self.storage.ticket(ticket_id)
        if not ticket:
            self.send(chat_id, "Заявка не найдена.")
            return
        user = self.storage.user(ticket["user_id"])
        contact = user["username"] and f"@{user['username']}" or str(ticket["user_id"])
        data = json.loads(ticket["data"])
        text = f"<b>Заявка #{ticket_id}</b>\nКлиент: {html.escape(contact)}\nСтатус: <code>{ticket['status']}</code>\n\n{order_summary(data)}"
        self.send(chat_id, text, self.ticket_keyboard(ticket_id))

    def change_ticket_status(self, chat_id: int, admin_id: int, ticket_id: int, status: TicketStatus) -> None:
        ok = self.storage.set_ticket_status(ticket_id, status, admin_id)
        if not ok:
            self.send(chat_id, "Заявка не найдена.")
            return
        ticket = self.storage.ticket(ticket_id)
        self.send(chat_id, f"Статус заявки #{ticket_id} изменён на <code>{status.value}</code>.")
        if ticket:
            messages = {
                TicketStatus.IN_WORK: "Твою заявку взяли в работу.",
                TicketStatus.WAITING_CLIENT: "По заявке нужен ответ клиента. Проверь сообщения от монтажёра.",
                TicketStatus.DONE: "Заявка отмечена как готовая. Спасибо за заказ.",
                TicketStatus.CANCELED: "Заявка отменена. Если это ошибка — напиши заново.",
            }
            if status in messages:
                self.safe_send(ticket["user_id"], f"Заявка <b>#{ticket_id}</b>: {messages[status]}")

    def reply_to_ticket(self, chat_id: int, admin_id: int, ticket_id: int, body: str) -> None:
        ticket = self.storage.ticket(ticket_id)
        if not ticket:
            self.send(chat_id, "Заявка не найдена.")
            return
        self.storage.add_ticket_message(ticket_id, admin_id, body)
        self.storage.set_ticket_status(ticket_id, TicketStatus.WAITING_CLIENT, admin_id)
        ok = self.safe_send(ticket["user_id"], f"<b>Ответ по заявке #{ticket_id}</b>\n\n{html.escape(body)}")
        self.send(chat_id, "Ответ отправлен." if ok else "Не смог отправить ответ клиенту.")

    def broadcast(self, chat_id: int, admin_id: int, body: str) -> None:
        if len(body) < 3:
            self.send(chat_id, "Текст рассылки слишком короткий.")
            return
        delivered = failed = 0
        for user in self.storage.users():
            if self.safe_send(user["id"], f"<b>Сообщение от Edit Studio</b>\n\n{html.escape(body)}"):
                delivered += 1
            else:
                failed += 1
        broadcast_id = self.storage.record_broadcast(admin_id, body, delivered, failed)
        self.send(chat_id, f"Рассылка #{broadcast_id}: доставлено {delivered}, ошибок {failed}.")

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.settings.admin_ids

    def main_keyboard(self) -> list[list[Button]]:
        rows = [
            [Button("Заказать эдит", "order:start")],
            [Button("Прайс", "price"), Button("Портфолио", "portfolio")],
            [Button("FAQ", "faq"), Button("Мои заказы", "status")],
            [Button(f"Написать @{self.settings.contact_username}", url=f"https://t.me/{self.settings.contact_username}")],
        ]
        return rows

    def back_keyboard(self) -> list[list[Button]]:
        return [[Button("Главное меню", "home")]]

    def ticket_keyboard(self, ticket_id: int) -> list[list[Button]]:
        return [
            [Button("В работу", f"admin:set:{TicketStatus.IN_WORK.value}:{ticket_id}"), Button("Ждём клиента", f"admin:set:{TicketStatus.WAITING_CLIENT.value}:{ticket_id}")],
            [Button("Готово", f"admin:set:{TicketStatus.DONE.value}:{ticket_id}"), Button("Отмена", f"admin:set:{TicketStatus.CANCELED.value}:{ticket_id}")],
        ]

