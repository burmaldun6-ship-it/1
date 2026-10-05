import os
from dataclasses import dataclass


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Не задана обязательная переменная окружения: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    admin_id: int
    database_path: str
    default_daily_limit: int


def load_settings() -> Settings:
    admin_id_raw = required_env("ADMIN_ID")
    default_limit_raw = os.getenv("DEFAULT_DAILY_LIMIT", "5")

    try:
        admin_id = int(admin_id_raw)
        default_limit = int(default_limit_raw)
    except ValueError as exc:
        raise RuntimeError("ADMIN_ID и DEFAULT_DAILY_LIMIT должны быть целыми числами") from exc

    if default_limit < 0:
        raise RuntimeError("DEFAULT_DAILY_LIMIT не может быть отрицательным")

    return Settings(
        bot_token=required_env("BOT_TOKEN"),
        openai_api_key=required_env("OPENAI_API_KEY"),
        # Можно указать https://api.openai.com/v1 или endpoint совместимого API.
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        admin_id=admin_id,
        database_path=os.getenv("DATABASE_PATH", "data/bot.sqlite3"),
        default_daily_limit=default_limit,
    )


settings = load_settings()
