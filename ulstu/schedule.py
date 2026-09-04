import asyncio
import json
import re
from html import escape
from datetime import datetime, date, timedelta
from pathlib import Path

from aiogram.types import Message
from bs4 import BeautifulSoup

from database import get_user
from ulstu.client import get_group_schedule
from utils import build_delete_button
from validator.group import normalize_group

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / 'cache'
CACHE_TTL = timedelta(minutes=120)


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
	soup = BeautifulSoup(html, "html.parser")

	tables = soup.find_all("table")

	result = []

	for table in tables:
		# Ищем заголовок недели перед таблицей.
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

		# Вторая строка таблицы содержит время.
		time_cells = rows[1].find_all("td")

		lesson_times = []

		for cell in time_cells[1:]:
			lesson_times.append(
				cell.get_text(" ", strip=True)
			)

		days = []

		# Остальные строки — дни недели.
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
	lines = [
		line.strip()
		for line in text.splitlines()
		if line.strip()
	]

	if not lines:
		return []

	lessons = []

	# Ищем начало каждого отдельного занятия.
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

		# Минимально ожидаем:
		# тип
		# предмет
		# [подгруппа]
		# преподаватель
		# аудитория
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

		# Последние две строки предполагаем
		# преподавателем и аудиторией.
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
	user = await get_user(telegram_id)

	if user is None:
		raise ValueError("Пользователь не найден")

	group_name = normalize_group(user["group_name"])
	schedule_part = user["schedule_part"]

	cache_path = get_cache_path(
		schedule_part,
		group_name
	)

	# Сначала проверяем локальный кэш.
	cached_data = load_schedule_cache(cache_path)

	if cached_data is not None:
		print("Используем расписание из кэша")
		return cached_data["schedule"]

	# Только теперь идём в УлГТУ.
	print("Кэш отсутствует или устарел. Обновляем расписание...")

	html = await get_group_schedule(telegram_id)

	schedule = parse_schedule(html)

	save_schedule_cache(
		cache_path,
		group_name,
		schedule_part,
		schedule
	)

	return schedule


def format_schedule_error(error: BaseException) -> str:
	"""
	Превращает ошибку получения расписания
	в понятное сообщение с подсказкой.
	"""

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


def is_cache_fresh(updated_at: str) -> bool:
	updated = datetime.fromisoformat(updated_at)

	if updated.tzinfo is None:
		now = datetime.now()
	else:
		now = datetime.now().astimezone()

	return now - updated < CACHE_TTL


def escape_html(value) -> str:
	return escape(str(value), quote=False)


def get_cache_path(schedule_part: int, group_name: str) -> Path:
	part_dir = CACHE_DIR / str(schedule_part)
	part_dir.mkdir(parents=True, exist_ok=True)

	group_name = normalize_group(group_name)

	return part_dir / f"{group_name}.json"


def load_schedule_cache(path: Path) -> dict | None:
	if not path.exists():
		return None

	try:
		with path.open("r", encoding="utf-8") as file:
			data = json.load(file)

		if not isinstance(data, dict):
			return None

		updated_at = data.get("updated_at")
		schedule = data.get("schedule")

		if not updated_at or schedule is None:
			return None

		if not is_cache_fresh(updated_at):
			return None

		return data

	except (OSError, json.JSONDecodeError, ValueError):
		return None


def save_schedule_cache(
		path: Path,
		group_name: str,
		schedule_part: int,
		schedule: list[dict]
):
	data = {
		"group": group_name,
		"schedule_part": schedule_part,
		"updated_at": datetime.now().astimezone().isoformat(),
		"schedule": schedule
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
	"""
	Формирует готовое сообщение с расписанием на день.

	Если telegram_id передан:
		применяется фильтр по подгруппе пользователя.

	Если telegram_id не передан:
		показываются все занятия.
	"""

	# --------------------------------------------------
	# Получаем подгруппу пользователя
	# --------------------------------------------------

	user_subgroup = None

	if telegram_id is not None:
		user = await get_user(telegram_id)

		if user is not None:
			user_subgroup = user["subgroup"]

	# --------------------------------------------------
	# Заголовок
	# --------------------------------------------------

	schedule_date = escape_html(day_schedule["date"])

	message = (
		f"📅 <b>Расписание на {schedule_date}</b>\n\n"
	)

	# --------------------------------------------------
	# Обрабатываем пары
	# --------------------------------------------------

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

		# Если после фильтрации ничего не осталось —
		# не показываем эту пару.
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
				f"<b><u>{escape_html(item['type'])}</u>"
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

	# --------------------------------------------------
	# Если пар нет
	# --------------------------------------------------

	if visible_lessons_count == 0:
		message += "<i>Пар нет.</i>"

	return message


async def send_schedule(
		message: Message,
		schedule: dict,
):
	message_text = await format_day_schedule(
		schedule,
		message.chat.id,
	)

	await message.answer(
		text=message_text,
		parse_mode="HTML",
		reply_markup=await build_delete_button(message),
	)
