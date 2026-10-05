import asyncio
from datetime import date
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.conn: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()

    async def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS usage (
                user_id INTEGER NOT NULL,
                usage_date TEXT NOT NULL,
                successful_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, usage_date)
            );

            CREATE TABLE IF NOT EXISTS user_limits (
                user_id INTEGER PRIMARY KEY,
                daily_limit INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NOT NULL,
                telegram_name TEXT NOT NULL,
                nickname TEXT NOT NULL,
                link TEXT NOT NULL,
                request_text TEXT NOT NULL,
                response_text TEXT,
                error_text TEXT
            );
            """
        )
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def _fetchone(self, query: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        assert self.conn is not None
        async with self.conn.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def get_limit(self, user_id: int, default_limit: int) -> int:
        row = await self._fetchone(
            "SELECT daily_limit FROM user_limits WHERE user_id = ?",
            (user_id,),
        )
        if row is not None:
            return int(row["daily_limit"])

        row = await self._fetchone(
            "SELECT value FROM settings WHERE key = 'global_daily_limit'"
        )
        if row is not None:
            return int(row["value"])

        return default_limit

    async def set_user_limit(self, user_id: int, daily_limit: int) -> None:
        assert self.conn is not None
        async with self.lock:
            await self.conn.execute(
                """
                INSERT INTO user_limits(user_id, daily_limit)
                VALUES(?, ?)
                ON CONFLICT(user_id) DO UPDATE SET daily_limit = excluded.daily_limit
                """,
                (user_id, daily_limit),
            )
            await self.conn.commit()

    async def set_global_limit(self, daily_limit: int) -> None:
        assert self.conn is not None
        async with self.lock:
            await self.conn.execute(
                """
                INSERT INTO settings(key, value)
                VALUES('global_daily_limit', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(daily_limit),),
            )
            await self.conn.commit()

    async def get_successful_count(self, user_id: int, usage_date: str | None = None) -> int:
        usage_date = usage_date or date.today().isoformat()
        row = await self._fetchone(
            """
            SELECT successful_count FROM usage
            WHERE user_id = ? AND usage_date = ?
            """,
            (user_id, usage_date),
        )
        return int(row["successful_count"]) if row else 0

    async def try_reserve_slot(
        self,
        user_id: int,
        limit: int,
        usage_date: str | None = None,
    ) -> bool:
        """Атомарно проверяет дневной лимит до вызова ИИ.

        Резервация не увеличивает successful_count: счётчик меняется
        только после успешного ответа ИИ.
        """
        usage_date = usage_date or date.today().isoformat()
        if limit <= 0:
            return False

        async with self.lock:
            current = await self.get_successful_count(user_id, usage_date)
            return current < limit

    async def increment_successful(self, user_id: int, usage_date: str | None = None) -> None:
        usage_date = usage_date or date.today().isoformat()
        assert self.conn is not None
        async with self.lock:
            await self.conn.execute(
                """
                INSERT INTO usage(user_id, usage_date, successful_count)
                VALUES(?, ?, 1)
                ON CONFLICT(user_id, usage_date)
                DO UPDATE SET successful_count = successful_count + 1
                """,
                (user_id, usage_date),
            )
            await self.conn.commit()

    async def log_ai_call(
        self,
        user_id: int,
        telegram_name: str,
        nickname: str,
        link: str,
        request_text: str,
        response_text: str | None,
        error_text: str | None,
    ) -> None:
        assert self.conn is not None
        async with self.lock:
            await self.conn.execute(
                """
                INSERT INTO ai_logs(
                    user_id, telegram_name, nickname, link,
                    request_text, response_text, error_text
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    telegram_name,
                    nickname,
                    link,
                    request_text,
                    response_text,
                    error_text,
                ),
            )
            await self.conn.commit()

    async def export_logs_markdown(self) -> str:
        assert self.conn is not None
        async with self.conn.execute(
            """
            SELECT created_at, telegram_name, user_id, nickname, link,
                   request_text, response_text, error_text
            FROM ai_logs
            ORDER BY id ASC
            """
        ) as cursor:
            rows = await cursor.fetchall()

        parts: list[str] = ["# Логи обращений к ИИ", ""]
        for row in rows:
            parts.extend(
                [
                    f"## {row['created_at']} — {row['telegram_name']}|{row['user_id']}",
                    f"**Ник:** {row['nickname']}",
                    f"**Link:** {row['link']}",
                    "",
                    "**Запрос:**",
                    row["request_text"],
                    "",
                    "**Что ему ответила ИИ:**",
                    row["response_text"] or f"Ошибка API: {row['error_text'] or 'неизвестная ошибка'}",
                    "",
                    "---",
                    "",
                ]
            )

        return "\n".join(parts)

    async def count_logs(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS count FROM ai_logs")
        return int(row["count"]) if row else 0
