import aiosqlite
from pathlib import Path
import aiosqlite

UNSET = object()


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "timetable.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    ulstu_login TEXT,
                    ulstu_password_encrypted TEXT,
                    session_cookies TEXT,
                    schedule_part INTEGER,
                    group_name TEXT,
                    subgroup INTEGER,
                    notification_time TEXT
            )
        """)

        await db.commit()


async def get_user(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT *
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        )

        return await cursor.fetchone()

async def create_user(
        telegram_id: int,
        ulstu_login: str,
        ulstu_password_encrypted: str,
        schedule_part: int,
        group_name: str,
        subgroup: int,
        notification_time: str
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
			INSERT INTO users (
				telegram_id,
				ulstu_login,
				group_name,
				subgroup,
				schedule_part,
				notification_time,
				ulstu_password_encrypted
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			""",
            (
                telegram_id,
                ulstu_login,
                group_name,
                subgroup,
                schedule_part,
                notification_time,
                ulstu_password_encrypted,
            )
        )

        await db.commit()

async def update_user(
    telegram_id: int,
    ulstu_login: str | None = None,
    group_name: str | None = None,
    subgroup: int | None | object = UNSET,
    schedule_part: int | None = None,
    notification_time: str | None = None,
    ulstu_password_encrypted: str | None = None,
    session_cookies: str | None = None,
):
    """Изменяет указанные данные пользователя."""
    fields = []
    values = []

    if ulstu_login is not None:
        fields.append("ulstu_login = ?")
        values.append(ulstu_login)

    if group_name is not None:
        fields.append("group_name = ?")
        values.append(group_name)

    if schedule_part is not None:
        fields.append("schedule_part = ?")
        values.append(schedule_part)

    if subgroup is not UNSET:
        fields.append("subgroup = ?")
        values.append(subgroup)

    if notification_time is not None:
        fields.append("notification_time = ?")
        values.append(notification_time)

    if ulstu_password_encrypted is not None:
        fields.append("ulstu_password_encrypted = ?")
        values.append(ulstu_password_encrypted)

    if session_cookies is not None:
        fields.append("session_cookies = ?")
        values.append(session_cookies)

    if not fields:
        return

    values.append(telegram_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"""
            UPDATE users
            SET {", ".join(fields)}
            WHERE telegram_id = ?
            """,
            values
        )

        await db.commit()

async def delete_user(telegram_id: int):
    """Удаляет пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            DELETE FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        )

        await db.commit()