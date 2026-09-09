"""
Работа с расписанием: парсинг HTML-страниц УлГТУ, JSON API time.ulstu.ru,
локальный кэш, форматирование сообщений и отправка расписания пользователю.
"""

import asyncio
import json
import re
from html import escape
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
import random

from aiogram.types import Message
from bs4 import BeautifulSoup

from console_log import log
from database import get_user
from ulstu.client import get_group_schedule, get_schedule_groups, get_group_schedule_api
from ulstu.api_normalizer import normalize_api_schedule
from utils import build_delete_button
from validator.group import normalize_group

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / 'cache'
# Расписание обновляется часто, список групп — редко
CACHE_TTL = timedelta(minutes=120)
GROUPS_CACHE_TTL = timedelta(days=1)

# Флаг: True → JSON API time.ulstu.ru, False → старый HTML парсинг
USE_SCHEDULE_API = True

CACHE_CLEANUP_INTERVAL = timedelta(hours=3)

async def cache_cleanup_loop():
    while True:
        try:
            clear_old_cache()

        except Exception as e:
            log(
                "clear_old_cache",
                f"Ошибка фоновой очистки: {e}"
            )

        await asyncio.sleep(
            CACHE_CLEANUP_INTERVAL.total_seconds()
        )

def clear_old_cache():
    log("clear_old_cache", "Очистка устаревшего кеша...")

    now = datetime.now(timezone.utc)
    deleted_count = 0

    for json_path in CACHE_DIR.rglob("*.json"):
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

        except (json.JSONDecodeError, OSError):
            continue

        updated_at_raw = data.get("updated_at")

        if updated_at_raw is None:
            try:
                json_path.unlink()

            except FileNotFoundError:
                pass

            except OSError as e:
                log(
                    "clear_old_cache",
                    f"Не удалось удалить {json_path}: {e}"
                )

            else:
                deleted_count += 1
                log(
                    "clear_old_cache",
                    f"Удалён (нет updated_at): {json_path}"
                )

            continue

        try:
            updated_at = datetime.fromisoformat(updated_at_raw)

        except (ValueError, TypeError):
            try:
                json_path.unlink()

            except FileNotFoundError:
                pass

            except OSError as e:
                log(
                    "clear_old_cache",
                    f"Не удалось удалить {json_path}: {e}"
                )

            else:
                deleted_count += 1
                log(
                    "clear_old_cache",
                    f"Удалён (невалидный updated_at): {json_path}"
                )

            continue

        # Если timezone отсутствует — считаем UTC.
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(
                tzinfo=timezone.utc
            )

        age = now - updated_at

        # Выбираем TTL в зависимости от типа кэша.
        ttl = (
            GROUPS_CACHE_TTL
            if json_path.name == "groups.json"
            else CACHE_TTL
        )

        if age > ttl:
            try:
                json_path.unlink()

            except FileNotFoundError:
                pass

            except OSError as e:
                log(
                    "clear_old_cache",
                    f"Не удалось удалить {json_path}: {e}"
                )

            else:
                deleted_count += 1
                log(
                    "clear_old_cache",
                    f"Удалён (устарел на {age}, TTL={ttl}): "
                    f"{json_path}"
                )

    if deleted_count == 0:
        log(
            "clear_old_cache",
            "Очистка завершена: устаревших файлов не найдено."
        )
    else:
        log(
            "clear_old_cache",
            f"Очистка завершена: удалено файлов — {deleted_count}."
        )

def get_schedule_for_date(
        schedule: list[dict],
        target_date: date
) -> dict | None:
    target_date_str = target_date.strftime("%d.%m.%Y")

    for week in schedule:
        for day in week["days"]:
            if day["date"] == target_date_str:
                return day

    return None


def parse_schedule(html: str) -> list[dict]:
    """Разбирает HTML расписания на список недель с днями и парами."""
    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")

    result = []

    for table in tables:
        # Ищем заголовок недели перед таблицей
        previous_text = table.find_previous(
            string=re.compile(r"Неделя:")
        )

        if previous_text is None:
            continue

        week_text = previous_text.parent.get_text(" ", strip=True)

        week_match = re.search(
            r"Неделя:\s*(\d+)-я",
            week_text
        )

        date_match = re.search(
            r"\((\d{2}\.\d{2}\.\d{4})–(\d{2}\.\d{2}\.\d{4})\)",
            week_text
        )

        if week_match is None:
            continue

        week_number = int(week_match.group(1))

        date_range = None

        if date_match:
            date_range = (
                date_match.group(1),
                date_match.group(2)
            )

        rows = table.find_all("tr")

        if len(rows) < 3:
            continue

        # Вторая строка таблицы содержит время
        time_cells = rows[1].find_all("td")

        lesson_times = []

        for cell in time_cells[1:]:
            lesson_times.append(
                cell.get_text(" ", strip=True)
            )

        days = []

        # Остальные строки — дни недели
        for row in rows[2:]:
            cells = row.find_all("td")

            if len(cells) < 2:
                continue

            day_name = cells[0].get_text(
                " ",
                strip=True
            )

            date_match = re.search(
                r"(\d{2}\.\d{2}\.\d{4})",
                day_name
            )

            date = (
                date_match.group(1)
                if date_match
                else None
            )

            lessons = []

            for lesson_number, cell in enumerate(
                    cells[1:],
                    start=1
            ):
                lesson_text = cell.get_text(
                    "\n",
                    strip=True
                )

                if not lesson_text:
                    continue

                lessons.append({
                    "lesson_number": lesson_number,
                    "time": lesson_times[
                        lesson_number - 1
                        ],
                    "lessons": parse_lesson_text(lesson_text)
                })

            days.append({
                "day": day_name,
                "date": date,
                "lessons": lessons
            })

        result.append({
            "week": week_number,
            "date_range": date_range,
            "days": days
        })

    return result


def parse_lesson_text(text: str) -> list[dict]:
    """Разбирает многострочную ячейку пары на отдельные занятия."""
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:
        return []

    lessons = []

    # Ищем начало каждого отдельного занятия
    lesson_starts = [
        i
        for i, line in enumerate(lines)
        if line in ("лек.", "пр.", "лаб.")
    ]

    for index, start in enumerate(lesson_starts):
        end = (
            lesson_starts[index + 1]
            if index + 1 < len(lesson_starts)
            else len(lines)
        )

        lesson_lines = lines[start:end]

        lesson_type = lesson_lines[0]

        # Минимально ожидаем: тип, предмет, подгруппа, преподаватель, аудитория
        if len(lesson_lines) < 4:
            continue

        subject = lesson_lines[1]

        subgroup = None
        current_index = 2

        subgroup_match = re.fullmatch(
            r"([1-9])(?:-я)?\s*п/г",
            lesson_lines[current_index]
        )

        if subgroup_match:
            subgroup = int(subgroup_match.group(1))
            current_index += 1

        # Последние две строки — преподаватель и аудитория
        if len(lesson_lines) - current_index < 2:
            continue

        teacher = lesson_lines[current_index]
        room = lesson_lines[current_index + 1]

        lessons.append({
            "type": lesson_type,
            "subject": subject,
            "subgroup": subgroup,
            "teacher": teacher,
            "room": room,
        })

    return lessons


async def get_schedule(telegram_id: int) -> list[dict]:
	"""Возвращает расписание пользователя, используя локальный кэш."""
	user = await get_user(telegram_id)

	if user is None:
		raise ValueError("Пользователь не найден")

	group_name = normalize_group(user["group_name"])
	schedule_part = user["schedule_part"]

	cache_path = get_cache_path(
		schedule_part,
		group_name
	)

	log(
		"ulstu.schedule",
		f"Запрос расписания: group={user['group_name']}, "
		f"part={schedule_part}",
		telegram_id,
	)

	# Сначала проверяем локальный кэш
	cached_schedule = load_cache(cache_path, "schedule", CACHE_TTL)

	if cached_schedule is not None:
		log(
			"ulstu.schedule",
			"Используем расписание из кэша",
			telegram_id,
		)
		return cached_schedule

	# Только теперь идём в УлГТУ
	log(
		"ulstu.schedule",
		"Кэш отсутствует или устарел — обновляем",
		telegram_id,
	)

	if USE_SCHEDULE_API:
		# Путь через JSON API time.ulstu.ru
		raw_weeks = await get_group_schedule_api(
			telegram_id,
			group_name,
		)
		schedule = normalize_api_schedule(raw_weeks)
	else:
		# Путь через HTML расписания УлГТУ
		groups = await get_available_groups(
			telegram_id,
			override_schedule_part=schedule_part,
		)
		html = await get_group_schedule(
			telegram_id,
			groups,
		)
		schedule = parse_schedule(html)

	save_cache(
		cache_path,
		"schedule",
		schedule,
		group=group_name,
		schedule_part=schedule_part,
	)
	log(
		"ulstu.schedule",
		f"Расписание обновлено и сохранено в кэш "
		f"({len(schedule)} недель)",
		telegram_id,
	)

	return schedule


def format_schedule_error(error: BaseException) -> str:
    """Превращает ошибку в понятное сообщение с подсказкой."""
    message = str(error)

    if (
        "Авторизация на УлГТУ не удалась" in message
        or "Сессия УлГТУ больше недействительна" in message
        or "после авторизации" in message
    ):
        return (
            "❌ Не удалось авторизоваться в системе УлГТУ.\n\n"
            "Возможные причины:\n"
            "• неверный логин или пароль\n"
            "• временные проблемы личного кабинета\n\n"
            "💡 Проверьте логин и пароль в ⚙ Настройки "
            "и нажмите «Применить изменения»."
        )

    if "не найдена в расписании" in message:
        return (
            "❌ Группа не найдена в расписании.\n\n"
            "Возможные причины:\n"
            "• опечатка в названии группы\n"
            "• выбран неверный факультет "
            "(часть расписания)\n\n"
            "💡 Проверьте группу и факультет "
            "в ⚙ Настройки."
        )

    if "Неизвестная часть расписания" in message:
        return (
            "❌ Некорректный факультет "
            "в настройках.\n\n"
            "💡 Выберите факультет заново "
            "в ⚙ Настройки."
        )

    if "Пользователь не найден" in message:
        return (
            "❌ Профиль не найден.\n\n"
            "💡 Пройдите регистрацию заново "
            "через /start."
        )

    if isinstance(
        error,
        (TimeoutError, asyncio.TimeoutError),
    ) or "Timeout" in type(error).__name__:
        return (
            "❌ Сервер УлГТУ не ответил вовремя.\n\n"
            "💡 Попробуйте ещё раз чуть позже."
        )

    error_name = type(error).__name__

    if (
        "ClientError" in error_name
        or "ClientResponseError" in error_name
        or "Connection" in error_name
    ):
        return (
            "❌ Не удалось связаться "
            "с сервером УлГТУ.\n\n"
            "💡 Проверьте интернет "
            "и попробуйте позже."
        )

    return (
        "❌ Не удалось получить расписание.\n\n"
        f"Причина: {message or error_name}\n\n"
        "💡 Попробуйте позже или проверьте данные "
        "в ⚙ Настройки."
    )


def escape_html(value) -> str:
    """Экранирует значение для безопасной вставки в HTML-сообщение."""
    return escape(str(value), quote=False)


def get_cache_path(schedule_part: int, group_name: str) -> Path:
    """Путь к JSON-кэшу расписания конкретной группы."""
    part_dir = CACHE_DIR / str(schedule_part)
    part_dir.mkdir(parents=True, exist_ok=True)

    return part_dir / f"{normalize_group(group_name)}.json"


def load_cache(path: Path, data_key: str, ttl: timedelta):
    """Возвращает данные из кэша по ключу, или None если кэш устарел/поврежден."""
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return None

        updated_at = data.get("updated_at")
        payload = data.get(data_key)

        if not updated_at or payload is None:
            return None

        updated = datetime.fromisoformat(updated_at)

        # Нормализуем к UTC: если время без timezone, считаем UTC
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)

        if now - updated >= ttl:
            return None

        return payload

    except (OSError, json.JSONDecodeError, ValueError):
        return None


def save_cache(path: Path, data_key: str, payload, **meta) -> None:
    """Сохраняет данные в JSON-кэш вместе с дополнительными полями **meta."""
    data = {
        **meta,
        data_key: payload,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4
        )


async def format_day_schedule(
        day_schedule: dict,
        telegram_id: int | None = None,
) -> str:
    """Формирует сообщение с расписанием на день.

    Если telegram_id передан — занятия фильтруются по подгруппе
    пользователя, иначе показываются все.
    """

    user_subgroup = None

    if telegram_id is not None:
        user = await get_user(telegram_id)

        if user is not None:
            user_subgroup = user["subgroup"]

    schedule_date = escape_html(day_schedule["date"])

    message = (
        f"📅 <b>Расписание на {schedule_date}</b>\n\n"
    )

    visible_lessons_count = 0

    for lesson in day_schedule["lessons"]:

        visible_lessons = []

        for item in lesson["lessons"]:

            # Общее занятие
            if item["subgroup"] is None:
                visible_lessons.append(item)

            # Занятие нашей подгруппы
            elif (
                    user_subgroup is None
                    or item["subgroup"] == user_subgroup
            ):
                visible_lessons.append(item)

        # Если пара полностью отфильтрована — не показываем её
        if not visible_lessons:
            continue

        visible_lessons_count += 1

        lesson_text = (
            f"<blockquote>"
            f"<b>{lesson['lesson_number']}-я пара "
            f"({escape_html(lesson['time'])})</b>\n\n"
        )

        for item in visible_lessons:
            item = {
                **item,
                "room": escape_html(item["room"]),
            }

            lesson_text += (
                f"<b><u>{escape_html(item['type'])}</u> "
                f"{escape_html(item['subject'])}</b>\n"
            )

            if item["subgroup"] is not None:
                lesson_text += (
                    f"<b>Подгруппа:</b> "
                    f"{escape_html(item['subgroup'])}\n"
                )

            lesson_text += (
                f"\n{escape_html(item['teacher'])}\n"
                f"<b>Аудитория:</b> {item['room']}\n\n"
            )

        lesson_text += "</blockquote>\n"

        message += lesson_text

    if visible_lessons_count == 0:
        if random.randint(1, 100) > 95:
            message += "<i>Отдыхай. Пар нет.</i>"
        else:
            message += "<i>Пар нет.</i>"

    return message


async def send_schedule(
        message: Message,
        schedule: dict,
):
    """Отправляет расписание на день с кнопкой «Удалить»."""
    message_text = await format_day_schedule(
        schedule,
        message.chat.id,
    )

    await message.answer(
        text=message_text,
        parse_mode="HTML",
        reply_markup=build_delete_button(),
    )


def get_groups_cache_path(schedule_part: int) -> Path:
    """Путь к JSON-кэшу списка групп заданной части расписания."""
    part_dir = CACHE_DIR / str(schedule_part)
    part_dir.mkdir(parents=True, exist_ok=True)

    return part_dir / "groups.json"


async def get_available_groups(
    telegram_id: int,
    override_schedule_part: int | None = None,
) -> list[dict]:
    """Возвращает список групп части расписания с кэшем на 90 дней."""
    user = await get_user(telegram_id)

    if user is None:
        raise ValueError("Пользователь не найден")

    schedule_part = (
        override_schedule_part
        if override_schedule_part is not None
        else user["schedule_part"]
    )

    log(
        "ulstu.schedule",
        f"Получение списка групп: part={schedule_part}",
        telegram_id,
    )

    cache_path = get_groups_cache_path(schedule_part)

    cached_groups = load_cache(cache_path, "groups", GROUPS_CACHE_TTL)

    if cached_groups is not None:
        log(
            "ulstu.schedule",
            f"Используем список групп из кэша: "
            f"part={schedule_part}, "
            f"groups={len(cached_groups)}",
            telegram_id,
        )

        return cached_groups

    log(
        "ulstu.schedule",
        f"Кэш групп отсутствует или устарел. "
        f"Обновляем: part={schedule_part}",
        telegram_id,
    )

    groups = await get_schedule_groups(
        telegram_id,
        override_schedule_part=schedule_part,
    )

    groups = normalize_groups(groups)

    save_cache(
        cache_path,
        "groups",
        groups,
        schedule_part=schedule_part,
    )

    log(
        "ulstu.schedule",
        f"Список групп обновлён: "
        f"part={schedule_part}, "
        f"groups={len(groups)}",
        telegram_id,
    )

    return groups

async def is_group_valid_advanced(
    telegram_id: int,
    group: str,
    override_schedule_part: int | None = None,
) -> bool:
    group = normalize_group(group)

    groups = await get_available_groups(
        telegram_id,
        override_schedule_part=override_schedule_part,
    )

    return any(
        normalize_group(item["group"]) == group
        for item in groups
    )

def normalize_groups(groups: list[dict]) -> list[dict]:
    """Разворачивает группы из строк вида "А, Б" в отдельные записи."""
    result = []

    for item in groups:
        for group_name in item["group"].split(","):
            group_name = group_name.strip()

            if not group_name:
                continue

            result.append({
                "group": group_name,
                "url": item["url"],
            })

    return result
