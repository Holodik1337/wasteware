from __future__ import annotations

import logging

from .app import BotApp
from .config import Settings
from .storage import Storage
from .telegram import Poller, TelegramClient


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    storage = Storage(settings.database_path)
    telegram = TelegramClient(settings.token)
    telegram.set_commands()
    Poller(telegram, BotApp(settings, storage, telegram), settings.poll_timeout).run()

