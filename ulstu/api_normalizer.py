"""
Нормализация ответа JSON API time.ulstu.ru во внутреннюю модель расписания,
совместимую с форматом, который ожидает format_day_schedule и остальной код.

Внутренняя модель (сводка):
  list[dict]  — список недель
    {"week": int, "date_range": tuple|None, "days": list[dict]}
      day: {"day": str, "date": str|None, "lessons": list[dict]}
        lesson: {"lesson_number": int, "time": str, "lessons": list[dict]}
          class: {"type": str, "subject": str, "subgroup": int|None,
                  "teacher": str, "room": str}

week — это НОМЕР СЕМЕСТРОВОЙ НЕДЕЛИ, как его показывает сайт УлГТУ
(а не относительный индекс из JSON, где 1 = текущая неделя).
"""

import re
from datetime import date, timedelta

from ulstu.api_errors import ULSTUResponseError

# Стандартное расписание пар УлГТУ (used as fallback when API has no times)
LESSON_TIMES = [
	"08:30-09:50",
	"10:00-11:20",
	"11:30-12:50",
	"13:30-14:50",
	"15:00-16:20",
	"16:30-17:50",
	"18:00-19:20",
	"19:30-20:50",
]

DAY_NAMES = [
	"Понедельник",
	"Вторник",
	"Среда",
	"Четверг",
	"Пятница",
	"Суббота",
]

# Regex для разбора nameOfLesson: "лек. Название предмета – 1 п/г"
_LESSON_TYPE_RE = re.compile(
	r"^(лек\.|пр\.|лаб\.)\s+"
	r"(.*?)"
	r"(?:\s*[-–]\s*(\d)(?:-я)?\s*п/г)?\s*$"
)


def _parse_name_of_lesson(raw: str) -> dict:
	"""Разбирает nameOfLesson на type, subject, subgroup.

	Примеры:
	  "лек. Базы данных" -> type="лек.", subject="Базы данных", subgroup=None
	  "лаб. Алгоритмы – 1 п/г" -> type="лаб.", subject="Алгоритмы", subgroup=1
	  "пр. Структуры данных 2 п/г" -> type="пр.", subject="Структуры данных", subgroup=2
	"""
	m = _LESSON_TYPE_RE.match(raw.strip())
	if m:
		return {
			"type": m.group(1),
			"subject": m.group(2).strip(),
			"subgroup": int(m.group(3)) if m.group(3) else None,
		}
	# Если не удалось распарсить — возвращаем как есть
	return {
		"type": "",
		"subject": raw.strip(),
		"subgroup": None,
	}


def _monday_of(value: date) -> date:
	"""Возвращает понедельник недели, в которую входит дата."""
	return value - timedelta(days=value.weekday())


def _semester_start_monday(reference_date: date | None = None) -> date:
	"""Понедельник недели начала текущего семестра.

	Осенний семестр начинается 1 сентября, весенний — 1 февраля.
	Сайт УлГТУ нумерует неделю, содержащую дату начала семестра, как 1-ю.
	"""
	if reference_date is None:
		reference_date = date.today()

	candidates = [
		date(reference_date.year, 9, 1),
		date(reference_date.year, 2, 1),
		date(reference_date.year - 1, 9, 1),
	]

	latest = max(c for c in candidates if c <= reference_date)

	return _monday_of(latest)


def _absolute_week_number(week_monday: date, reference_date: date | None = None) -> int:
	"""Номер семестровой недели (как на сайте УлГТУ) по понедельнику недели.

	Пример: при reference_date = 2026-09-13, понедельник 2026-09-07 → 2-я неделя,
	понедельник 2026-09-14 → 3-я неделя.
	"""
	anchor_monday = _semester_start_monday(reference_date)
	return (week_monday - anchor_monday).days // 7 + 1


def _compute_day_date(week_number: int, day_index: int, reference_date: date | None = None) -> date:
	"""Вычисляет дату дня по номеру недели и индексу дня (0=Пн).

	week_number=1, day_index=0 → текущий понедельник
	week_number=2, day_index=3 → следующий четверг и т.д.

	reference_date — дата для определения текущей недели (по умолчанию date.today()).
	"""
	if reference_date is None:
		reference_date = date.today()

	# Текущий понедельник
	current_monday = reference_date - timedelta(days=reference_date.weekday())
	# Смещение: week_number=1 → текущая неделя, week_number=2 → следующая
	week_offset = timedelta(weeks=week_number - 1)
	return current_monday + week_offset + timedelta(days=day_index)


def normalize_api_schedule(raw_weeks: dict, reference_date: date | None = None) -> list[dict]:
	"""Нормализует raw_weeks из API-ответа во внутреннюю модель расписания.

	Вход: {"1": {"days": [{"day": 0, "lessons": [[...], [], ...]}]}}
	Выход: [{"week": 2, "date_range": ("07.09.2026", "13.09.2026"), "days": [...]}]

	reference_date — дата, относительно которой определяются недели
	(по умолчанию — date.today()); передаётся в тестах для детерминизма.
	week получает номер СЕМЕСТРОВОЙ недели по подсчёту сайта УлГТУ,
	а не относительный ключ из JSON (1 = текущая неделя).
	"""
	if not isinstance(raw_weeks, dict):
		raise ULSTUResponseError(f"Ожидался dict с неделями, получен {type(raw_weeks).__name__}")

	schedule = []

	for week_key in sorted(raw_weeks.keys(), key=lambda x: int(x)):
		week_data = raw_weeks[week_key]

		if not isinstance(week_data, dict):
			continue

		week_number = int(week_key)
		api_days = week_data.get("days", [])

		if not isinstance(api_days, list):
			continue

		days = []
		for api_day in api_days:
			if not isinstance(api_day, dict):
				continue

			day_index = api_day.get("day")
			api_lessons = api_day.get("lessons", [])

			if not isinstance(day_index, int) or day_index < 0 or day_index >= len(DAY_NAMES):
				continue

			# Вычисляем дату
			computed_date = _compute_day_date(week_number, day_index, reference_date)
			date_str = computed_date.strftime("%d.%m.%Y")
			day_name = f"{DAY_NAMES[day_index]} {date_str}"

			# Нормализуем пары
			lessons = []
			if isinstance(api_lessons, list):
				for pair_index, pair in enumerate(api_lessons):
					if not isinstance(pair, list):
						continue

					# Пустая пара — пропускаем (как делает HTML-парсер)
					if not pair:
						continue

					# Время берём из стандартного расписания
					time_str = (
						LESSON_TIMES[pair_index]
						if pair_index < len(LESSON_TIMES)
						else ""
					)

					# Нормализуем каждое занятие в паре
					normalized_classes = []
					for item in pair:
						if not isinstance(item, dict):
							continue

						name_info = _parse_name_of_lesson(item.get("nameOfLesson", ""))
						normalized_classes.append({
							"type": name_info["type"],
							"subject": name_info["subject"],
							"subgroup": name_info["subgroup"],
							"teacher": item.get("teacher", ""),
							"room": item.get("room", ""),
						})

					if normalized_classes:
						lessons.append({
							"lesson_number": pair_index + 1,
							"time": time_str,
							"lessons": normalized_classes,
						})

			days.append({
				"day": day_name,
				"date": date_str,
				"lessons": lessons,
			})

		# Диапазон дат недели: понедельник — воскресенье (как на сайте УлГТУ)
		week_monday = _compute_day_date(week_number, 0, reference_date)
		week_sunday = _compute_day_date(week_number, 6, reference_date)

		schedule.append({
			"week": _absolute_week_number(week_monday, reference_date),
			"date_range": (
				week_monday.strftime("%d.%m.%Y"),
				week_sunday.strftime("%d.%m.%Y"),
			),
			"days": days,
		})

	return schedule