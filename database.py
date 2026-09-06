from pathlib import Path

import aiosqlite

from console_log import log

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
                    notification_time TEXT,
                    notification_enabled INTEGER NOT NULL DEFAULT 0,
                    notification_last_sent TEXT
            )
        """)

		await db.commit()

	log("database", f"Таблица users готова ({DB_PATH})")


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
    session_cookies: str = "",
    schedule_part: int | None = None,
    group_name: str | None = None,
    subgroup: int | None = None,
    notification_time: str | None = None,
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
                ulstu_password_encrypted,
                session_cookies
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_id,
                ulstu_login,
                group_name,
                subgroup,
                schedule_part,
                notification_time,
                ulstu_password_encrypted,
                session_cookies,
            )
        )

        await db.commit()

    log(
        "database",
        f"Создан пользователь: login={ulstu_login}, "
        f"group={group_name}, part={schedule_part}, "
        f"subgroup={subgroup}",
        telegram_id,
    )


async def update_user(
		telegram_id: int,
		ulstu_login: str | None = None,
		group_name: str | None = None,
		subgroup: int | None | object = UNSET,
		schedule_part: int | None = None,
		notification_time: str | None = None,
		ulstu_password_encrypted: str | None = None,
		session_cookies: str | None = None,
		notification_enabled: bool | None = None,
		notification_last_sent: str | None = None,
):
	fields = []
	values = []
	changed = []

	if ulstu_login is not None:
		fields.append("ulstu_login = ?")
		values.append(ulstu_login)
		changed.append("login")

	if group_name is not None:
		fields.append("group_name = ?")
		values.append(group_name)
		changed.append("group")

	if schedule_part is not None:
		fields.append("schedule_part = ?")
		values.append(schedule_part)
		changed.append("schedule_part")

	if subgroup is not UNSET:
		fields.append("subgroup = ?")
		values.append(subgroup)
		changed.append("subgroup")

	if notification_time is not None:
		fields.append("notification_time = ?")
		values.append(notification_time)
		changed.append("notification_time")

	if notification_last_sent is not None:
		fields.append("notification_last_sent = ?")
		values.append(notification_last_sent)
		changed.append("notification_last_sent")

	if notification_enabled is not None:
		fields.append("notification_enabled = ?")
		values.append(int(notification_enabled))
		changed.append("notification_enabled")

	if ulstu_password_encrypted is not None:
		fields.append("ulstu_password_encrypted = ?")
		values.append(ulstu_password_encrypted)
		changed.append("password")

	if session_cookies is not None:
		fields.append("session_cookies = ?")
		values.append(session_cookies)
		changed.append("session_cookies")

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

	log(
		"database",
		f"Обновлены поля: {', '.join(changed)}",
		telegram_id,
	)


async def delete_user(telegram_id: int):
	async with aiosqlite.connect(DB_PATH) as db:
		await db.execute(
			"""
			DELETE FROM users
			WHERE telegram_id = ?
			""",
			(telegram_id,)
		)

		await db.commit()

	log("database", "Пользователь удалён", telegram_id)


async def get_users_for_notification(current_time: str, current_date: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT *
            FROM users
            WHERE notification_enabled = 1
              AND notification_time IS NOT NULL
              AND notification_time != ''
              AND notification_time <= ?
              AND (
                  notification_last_sent IS NULL
                  OR notification_last_sent != ?
              )
            """,
            (current_time, current_date)
        )

        return await cursor.fetchall()


async def get_registered_users():
	async with aiosqlite.connect(DB_PATH) as db:
		db.row_factory = aiosqlite.Row

		cursor = await db.execute(
			"""
			SELECT telegram_id
			FROM users
			"""
		)

		users = await cursor.fetchall()

	return [dict(user) for user in users]
