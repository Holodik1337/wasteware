from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _split_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        value = chunk.strip()
        if value:
            ids.add(int(value))
    return ids


@dataclass(frozen=True)
class Settings:
    token: str
    admin_ids: set[int]
    database_path: Path
    public_site_url: str
    portfolio_url: str
    price_url: str
    contact_username: str
    poll_timeout: int = 25

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(Path.cwd() / ".env")
        load_dotenv(Path.cwd().parent / ".env")
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN is required")
        admin_ids = _split_ids(os.getenv("ADMIN_IDS", ""))
        if not admin_ids:
            raise RuntimeError("ADMIN_IDS must contain at least one Telegram user id")
        return cls(
            token=token,
            admin_ids=admin_ids,
            database_path=Path(os.getenv("DATABASE_PATH", "./wasteware_bot.sqlite3")),
            public_site_url=os.getenv("PUBLIC_SITE_URL", "").strip(),
            portfolio_url=os.getenv("PORTFOLIO_URL", "https://t.me/+WnSO6JAMc5c4NDJh").strip(),
            price_url=os.getenv("PRICE_URL", "https://t.me/+NvLF3Fw4De43MzYx").strip(),
            contact_username=os.getenv("CONTACT_USERNAME", "wasteware").strip().lstrip("@"),
            poll_timeout=int(os.getenv("POLL_TIMEOUT", "25")),
        )
