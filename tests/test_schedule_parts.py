"""Тесты разбора ссылок на части расписания lk.ulstu.ru/timetable/."""
import asyncio

import pytest

from ulstu.client import (
	LOGIN_URL,
	SCHEDULE_URLS,
	clear_schedule_parts_cache,
	extract_part_number,
	parse_schedule_part_links,
	resolve_schedule_url,
)

PARTIAL_HTML = """
<html><body>
  <nav>
    <a href="/timetable/">Расписание</a>
    <a href="shared/schedule/Часть 1 - МФ, РТФ, ЭФ/raspisan.html">
      Часть 1 - МФ, РТФ, ЭФ (очная, очно-заочная формы обучения)
    </a>
    <a href="shared/schedule/Часть 2 – ФИСТ, ГФ/raspisan.html">
      Часть 2 – ФИСТ, ГФ
    </a>
  </nav>
</body></html>
"""


class FakeSession:
	"""Отдаёт заранее заданный HTML страницы расписания."""

	def __init__(self, html: str):
		self.html = html
		self.requests = 0

	async def get(self, url, *args, **kwargs):
		self.requests += 1

		return FakeResponse(self.html)


class BrokenSession:
	"""Сессия, которая падает на любом запросе."""

	async def get(self, url, *args, **kwargs):
		raise RuntimeError("boom")


class FakeResponse:
	def __init__(self, text: str):
		self.status = 200
		self.url = LOGIN_URL
		self._text = text

	async def text(self):
		return self._text

	def raise_for_status(self):
		pass


def run(coroutine):
	"""Запускает корутину: pytest-asyncio в проекте нет."""
	return asyncio.run(coroutine)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
	"""Чистим кеш ссылок и не пишем CSV-лог запросов во время тестов."""
	monkeypatch.setattr(
		"ulstu.client.log_request",
		lambda **kwargs: None,
	)

	clear_schedule_parts_cache()

	yield

	clear_schedule_parts_cache()


# --- extract_part_number ---


def test_extract_part_number_from_text():
	assert extract_part_number("Часть 3 – ИАТУ, ИЭФ") == 3


def test_extract_part_number_is_case_insensitive():
	assert extract_part_number("часть 5 – СФ") == 5


def test_extract_part_number_from_encoded_url():
	url = "https://lk.ulstu.ru/timetable/shared/schedule/Часть 4 – КЭИ/raspisan.html"

	assert extract_part_number("", url) == 4


def test_extract_part_number_prefers_text():
	# В тексте часть 2, в URL часть 7 — верим тексту ссылки
	assert extract_part_number(
		"Часть 2 – ФИСТ",
		"https://lk.ulstu.ru/timetable/shared/schedule/Часть 7/raspisan.html",
	) == 2


def test_extract_part_number_returns_none():
	assert extract_part_number("ФИСТ, ГФ", "https://lk.ulstu.ru/") is None


def test_extract_part_number_handles_long_titles():
	assert extract_part_number(
		"Часть 1 - МФ, РТФ, ЭФ (очная, очно-заочная формы обучения), "
		"ИФМИ, группы искусственного интеллекта (магистр)"
	) == 1


# --- parse_schedule_part_links ---


def test_parse_schedule_part_links():
	parts = parse_schedule_part_links(PARTIAL_HTML, LOGIN_URL)

	assert parts == {
		1: (
			f"{LOGIN_URL}shared/schedule/"
			"Часть 1 - МФ, РТФ, ЭФ/raspisan.html"
		),
		2: f"{LOGIN_URL}shared/schedule/Часть 2 – ФИСТ, ГФ/raspisan.html",
	}


def test_parse_schedule_part_links_ignores_other_links():
	html = """
	<a href="https://lk.ulstu.ru/timetable/auth/login">Войти</a>
	<a href="/timetable/personal/">Личный кабинет</a>
	"""

	assert parse_schedule_part_links(html, LOGIN_URL) == {}


def test_parse_schedule_part_links_takes_number_from_url():
	html = """
	<a href="shared/schedule/Часть 5 – СФ/raspisan.html">
		<span>Расписание СФ</span>
	</a>
	"""

	parts = parse_schedule_part_links(html, LOGIN_URL)

	assert list(parts) == [5]
	assert parts[5].endswith("Часть 5 – СФ/raspisan.html")


def test_parse_schedule_part_links_skips_duplicates():
	html = """
	<a href="shared/schedule/Часть 1 - старый/raspisan.html">Часть 1 - старый</a>
	<a href="shared/schedule/Часть 1 - новый/raspisan.html">Часть 1 - новый</a>
	"""

	parts = parse_schedule_part_links(html, LOGIN_URL)

	assert list(parts) == [1]
	assert "старый" in parts[1]


def test_parse_schedule_part_links_absolute_href():
	html = """
	<a href="https://lk.ulstu.ru/timetable/shared/schedule/Часть 4 – КЭИ/raspisan.html">
		Часть 4 – КЭИ
	</a>
	"""

	parts = parse_schedule_part_links(html, LOGIN_URL)

	assert parts == {
		4: (
			"https://lk.ulstu.ru/timetable/shared/schedule/"
			"Часть 4 – КЭИ/raspisan.html"
		),
	}


def test_parse_schedule_part_links_empty_html():
	assert parse_schedule_part_links("", LOGIN_URL) == {}


# --- resolve_schedule_url ---


def test_resolve_schedule_url_uses_site_value():
	session = FakeSession(PARTIAL_HTML)

	url = run(resolve_schedule_url(session, 2, telegram_id=1))

	assert "Часть 2" in url
	assert url != SCHEDULE_URLS[2]


def test_resolve_schedule_url_falls_back_when_site_has_no_part():
	session = FakeSession(PARTIAL_HTML)

	url = run(resolve_schedule_url(session, 5, telegram_id=1))

	assert url == SCHEDULE_URLS[5]


def test_resolve_schedule_url_falls_back_on_error():
	url = run(resolve_schedule_url(BrokenSession(), 1, telegram_id=1))

	assert url == SCHEDULE_URLS[1]


def test_resolve_schedule_url_unknown_part():
	with pytest.raises(ValueError, match="Неизвестная часть расписания"):
		run(resolve_schedule_url(FakeSession(PARTIAL_HTML), 42, telegram_id=1))


def test_resolve_schedule_url_uses_cache_without_second_request():
	first_session = FakeSession(PARTIAL_HTML)
	second_session = FakeSession(PARTIAL_HTML)

	first = run(resolve_schedule_url(first_session, 1, telegram_id=1))
	second = run(resolve_schedule_url(second_session, 2, telegram_id=1))

	assert first_session.requests == 1
	assert second_session.requests == 0
	assert first == parse_schedule_part_links(PARTIAL_HTML, LOGIN_URL)[1]
	assert second == parse_schedule_part_links(PARTIAL_HTML, LOGIN_URL)[2]


def test_resolve_schedule_url_force_refresh_skips_cache():
	first_session = FakeSession(PARTIAL_HTML)
	second_session = FakeSession(PARTIAL_HTML)

	run(resolve_schedule_url(first_session, 1, telegram_id=1))
	run(resolve_schedule_url(
		second_session,
		1,
		telegram_id=1,
		force_refresh=True,
	))

	assert first_session.requests == 1
	assert second_session.requests == 1