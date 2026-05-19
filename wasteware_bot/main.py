from __future__ import annotations

import logging
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from wasteware_bot.app import BotApp
    from wasteware_bot.config import Settings
    from wasteware_bot.storage import Storage
    from wasteware_bot.telegram import Poller, TelegramClient
else:
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
