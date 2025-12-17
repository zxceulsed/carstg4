# db.py (асинхронный, безопасный)
import aiosqlite
import asyncio

DB_NAME = "cars.db"

# Глобальная блокировка, чтобы не было параллельных записей
lock = asyncio.Lock()


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:

        # WAL — позволяет читать во время записи, уменьшает шанс блокировки
        await db.execute("PRAGMA journal_mode=WAL;")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT UNIQUE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                custom_link TEXT
            )
        """)

        await db.execute(
            "INSERT OR IGNORE INTO config (id, custom_link) VALUES (1, NULL)"
        )

        await db.commit()


async def ad_exists(link: str) -> bool:
    async with lock:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                "SELECT 1 FROM ads WHERE link = ?",
                (link,)
            )
            row = await cursor.fetchone()
            return row is not None


async def add_ad(link: str):
    async with lock:
        async with aiosqlite.connect(DB_NAME) as db:
            try:
                await db.execute(
                    "INSERT INTO ads (link) VALUES (?)",
                    (link,)
                )
                await db.commit()
            except aiosqlite.IntegrityError:
                pass  # уже есть


async def set_custom_link(link: str):
    async with lock:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT OR REPLACE INTO config (id, custom_link) VALUES (1, ?)",
                (link,)
            )
            await db.commit()


async def get_custom_link() -> str | None:
    async with lock:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                "SELECT custom_link FROM config WHERE id = 1"
            )
            row = await cursor.fetchone()
            return row[0] if row else None
