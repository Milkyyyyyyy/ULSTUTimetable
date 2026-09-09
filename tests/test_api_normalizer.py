"""Тесты нормализации JSON API time.ulstu.ru во внутреннюю модель расписания."""
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from ulstu.api_normalizer import (
	normalize_api_schedule,
	_parse_name_of_lesson,
	_compute_day_date,
	LESSON_TIMES,
	DAY_NAMES,
)
from ulstu.api_errors import ULSTUResponseError

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def api_response():
	with open(FIXTURES_DIR / "api_response.json", encoding="utf-8") as f:
		return json.load(f)


@pytest.fixture
def api_version_response():
	with open(FIXTURES_DIR / "api_version_response.json", encoding="utf-8") as f:
		return json.load(f)


# --- Tests for _parse_name_of_lesson ---


def test_parse_lecture():
	result = _parse_name_of_lesson("лек. Базы данных")
	assert result == {"type": "лек.", "subject": "Базы данных", "subgroup": None}


def test_parse_practice_with_subgroup():
	result = _parse_name_of_lesson("пр. Иностранный язык – 2 п/г")
	assert result == {"type": "пр.", "subject": "Иностранный язык", "subgroup": 2}


def test_parse_lab_with_subgroup():
	result = _parse_name_of_lesson("лаб. Алгоритмы и структуры данных – 1 п/г")
	assert result == {
		"type": "лаб.",
		"subject": "Алгоритмы и структуры данных",
		"subgroup": 1,
	}


def test_parse_fallback_unrecognized():
	result = _parse_name_of_lesson("неизвестный тип предмета")
	assert result == {"type": "", "subject": "неизвестный тип предмета", "subgroup": None}


def test_parse_with_dash_subgroup():
	result = _parse_name_of_lesson("лаб. Базы данных – 1 п/г")
	assert result == {"type": "лаб.", "subject": "Базы данных", "subgroup": 1}


def test_parse_with_ordinal_subgroup():
	result = _parse_name_of_lesson("лаб. Тест – 2-я п/г")
	assert result == {"type": "лаб.", "subject": "Тест", "subgroup": 2}


# --- Tests for _compute_day_date ---


def test_compute_day_date_current_week():
	today = date.today()
	result = _compute_day_date(week_number=1, day_index=0)
	expected = today - timedelta(days=today.weekday())
	assert result == expected


def test_compute_day_date_next_week():
	today = date.today()
	result = _compute_day_date(week_number=2, day_index=3)
	expected = (today - timedelta(days=today.weekday())) + timedelta(weeks=1, days=3)
	assert result == expected


def test_compute_day_date_with_reference():
	ref = date(2026, 9, 9)  # Среда
	result = _compute_day_date(week_number=1, day_index=0, reference_date=ref)
	# 2026-09-09 (Ср) → понедельник = 2026-09-07
	assert result == date(2026, 9, 7)


def test_compute_day_date_second_week_with_reference():
	ref = date(2026, 9, 9)
	result = _compute_day_date(week_number=2, day_index=5, reference_date=ref)
	# 2026-09-07 + 7 дней + 5 дней = 2026-09-19 (Сб)
	assert result == date(2026, 9, 19)


# --- Tests for normalize_api_schedule ---


def test_normal_basic(api_response):
	schedule = normalize_api_schedule(api_response["response"]["weeks"])

	assert len(schedule) == 1
	week = schedule[0]
	assert week["week"] == 1
	assert week["date_range"] is not None
	assert len(week["date_range"]) == 2
	assert len(week["days"]) == 6  # day 0-5 (Пн-Сб)


def test_date_range_valid(api_response):
	schedule = normalize_api_schedule(api_response["response"]["weeks"])
	week = schedule[0]
	start_date, end_date = week["date_range"]

	# Диапазон — от понедельника до субботы
	assert len(start_date) == 10  # DD.MM.YYYY
	assert len(end_date) == 10

	from datetime import datetime
	s = datetime.strptime(start_date, "%d.%m.%Y").date()
	e = datetime.strptime(end_date, "%d.%m.%Y").date()

	# Суббота = понедельник + 5 дней
	assert (e - s).days == 5


def test_day_names(api_response):
	schedule = normalize_api_schedule(api_response["response"]["weeks"])
	days = schedule[0]["days"]

	for i, day in enumerate(days):
		assert day["day"].startswith(DAY_NAMES[i])
		assert day["date"] is not None
		assert len(day["date"]) == 10  # DD.MM.YYYY


def test_lessons_not_empty(api_response):
	schedule = normalize_api_schedule(api_response["response"]["weeks"])
	monday = schedule[0]["days"][0]  # Понедельник

	# В Пн есть 3 пары
	assert len(monday["lessons"]) == 3


def test_empty_pairs_skipped(api_response):
	schedule = normalize_api_schedule(api_response["response"]["weeks"])
	saturday = schedule[0]["days"][5]  # Суббота

	# Суббота пустая
	assert len(saturday["lessons"]) == 0


def test_lesson_structure(api_response):
	schedule = normalize_api_schedule(api_response["response"]["weeks"])
	monday = schedule[0]["days"][0]
	first_lesson = monday["lessons"][0]

	assert first_lesson["lesson_number"] == 1
	assert first_lesson["time"] == LESSON_TIMES[0]
	assert len(first_lesson["lessons"]) == 1

	class_obj = first_lesson["lessons"][0]
	assert class_obj["type"] == "лек."
	assert class_obj["subject"] == "Технологии создания человеко-машинного интерфейса"
	assert class_obj["subgroup"] is None
	assert class_obj["teacher"] == "Шамшев А Б"
	assert class_obj["room"] == "3_2"


def test_multi_subgroup(api_response):
	schedule = normalize_api_schedule(api_response["response"]["weeks"])
	# Четверг (day=4), 3-я пара (index 2)
	thursday = schedule[0]["days"][4]
	pair_3 = thursday["lessons"][0]  # 3-я пара

	# В паре два занятия (1 п/г и 2 п/г)
	assert len(pair_3["lessons"]) == 2
	assert pair_3["lessons"][0]["subgroup"] == 1
	assert pair_3["lessons"][1]["subgroup"] == 2


def test_week_sorted_by_key():
	"""Недели сортируются по числовому ключу."""
	weeks_data = {
		"3": {"days": [{"day": 0, "lessons": []}]},
		"1": {"days": [{"day": 0, "lessons": []}]},
		"2": {"days": [{"day": 0, "lessons": []}]},
	}
	schedule = normalize_api_schedule(weeks_data)
	week_numbers = [w["week"] for w in schedule]
	assert week_numbers == [1, 2, 3]


def test_empty_weeks():
	schedule = normalize_api_schedule({})
	assert schedule == []


def test_invalid_weeks_type():
	with pytest.raises(ULSTUResponseError):
		normalize_api_schedule("not a dict")


def test_invalid_day_index():
	weeks = {"1": {"days": [{"day": 99, "lessons": []}]}}
	schedule = normalize_api_schedule(weeks)
	# День с невалидным индексом пропускается
	assert len(schedule[0]["days"]) == 0


def test_invalid_day_type():
	weeks = {"1": {"days": [{"day": "Monday", "lessons": []}]}}
	schedule = normalize_api_schedule(weeks)
	assert len(schedule[0]["days"]) == 0


def test_missing_days_key():
	weeks = {"1": {}}
	schedule = normalize_api_schedule(weeks)
	assert schedule[0]["days"] == []


def test_invalid_lesson_item_skipped():
	"""Невалидные элементы в паре пропускаются."""
	weeks = {"1": {"days": [{"day": 0, "lessons": [[
		{"group": "ГР1", "nameOfLesson": "лек. Тест", "teacher": "Иванов", "room": "101"},
		"invalid_string",
	]]}]}}
	schedule = normalize_api_schedule(weeks)
	lesson = schedule[0]["days"][0]["lessons"][0]
	# Только валидный объект прошёл
	assert len(lesson["lessons"]) == 1
	assert lesson["lessons"][0]["subject"] == "Тест"


def test_all_lesson_times_covered():
	"""Каждая пара получает правильное время из LESSON_TIMES."""
	assert len(LESSON_TIMES) == 8
	# Проверяем что индексы 0-7 дают корректные времена
	for i, time_str in enumerate(LESSON_TIMES):
		assert "-" in time_str
		parts = time_str.split("-")
		assert len(parts) == 2