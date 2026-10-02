"""Тесты фолбэка на устаревший кеш списка групп."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from ulstu.api_errors import ULSTUNotFoundError
from ulstu.schedule import (
	format_stale_groups_warning,
	get_available_groups,
	get_groups_cache_path,
)

USER = {"schedule_part": 2, "group_name": "ПИбд-11", "subgroup": None}

OLD_GROUPS = [
	{"group": "ПИбд-11", "url": "https://lk.ulstu.ru/old/raspisan.html"},
	{"group": "ПИбд-12", "url": "https://lk.ulstu.ru/old/raspisan.html"},
]


def run(coroutine):
	"""Запускает корутину: pytest-asyncio в проекте нет."""
	return asyncio.run(coroutine)


def returns(value):
	"""Заглушка async-функции, возвращающей value."""

	async def inner(*args, **kwargs):
		return value

	return inner


def write_groups_cache(groups, age: timedelta):
	"""Кладёт список групп в кеш с указанным «возрастом»."""
	cache_path = get_groups_cache_path(USER["schedule_part"])
	cache_path.parent.mkdir(parents=True, exist_ok=True)

	cache_path.write_text(
		json.dumps(
			{
				"schedule_part": USER["schedule_part"],
				"groups": groups,
				"updated_at": (
					datetime.now(timezone.utc) - age
				).isoformat(),
			},
			ensure_ascii=False,
		),
		encoding="utf-8",
	)

	return cache_path


def patch_groups_fetch(monkeypatch, result):
	"""Подменяет сетевой запрос списка групп на result/исключение."""

	async def fake_get_schedule_groups(
		telegram_id,
		override_schedule_part=None,
	):
		if isinstance(result, BaseException):
			raise result

		return result

	monkeypatch.setattr(
		"ulstu.schedule.get_schedule_groups",
		fake_get_schedule_groups,
	)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
	"""Кеш пишется в tmp, пользователь всегда есть."""
	monkeypatch.setattr("ulstu.schedule.CACHE_DIR", tmp_path)
	monkeypatch.setattr("ulstu.schedule.get_user", returns(USER))


# --- Фолбэк на устаревший кеш ---


def test_uses_stale_cache_on_404(monkeypatch):
	write_groups_cache(OLD_GROUPS, age=timedelta(days=40))
	patch_groups_fetch(monkeypatch, ULSTUNotFoundError("404"))

	snapshot = run(get_available_groups(1))

	assert snapshot.is_stale is True
	assert snapshot.groups == OLD_GROUPS
	assert snapshot.updated_at is not None


def test_stale_cache_keeps_own_timestamp(monkeypatch):
	cache_path = write_groups_cache(OLD_GROUPS, age=timedelta(days=40))
	updated_before = json.loads(
		cache_path.read_text(encoding="utf-8")
	)["updated_at"]

	patch_groups_fetch(monkeypatch, ULSTUNotFoundError("404"))

	run(get_available_groups(1))

	updated_after = json.loads(
		cache_path.read_text(encoding="utf-8")
	)["updated_at"]

	assert updated_after == updated_before


def test_stale_cache_on_network_error(monkeypatch):
	write_groups_cache(OLD_GROUPS, age=timedelta(days=40))
	patch_groups_fetch(monkeypatch, TimeoutError("долго нет ответа"))

	snapshot = run(get_available_groups(1))

	assert snapshot.is_stale is True
	assert snapshot.groups == OLD_GROUPS


def test_auth_error_is_not_hidden_by_stale_cache(monkeypatch):
	write_groups_cache(OLD_GROUPS, age=timedelta(days=40))
	patch_groups_fetch(
		monkeypatch,
		RuntimeError("Сессия УлГТУ больше недействительна"),
	)

	with pytest.raises(RuntimeError, match="Сессия УлГТУ"):
		run(get_available_groups(1))


def test_no_cache_raises_original_error(monkeypatch):
	patch_groups_fetch(monkeypatch, ULSTUNotFoundError("404"))

	with pytest.raises(ULSTUNotFoundError):
		run(get_available_groups(1))


# --- Обычные сценарии ---


def test_fresh_cache_is_used_without_request(monkeypatch):
	write_groups_cache(OLD_GROUPS, age=timedelta(hours=2))
	patch_groups_fetch(monkeypatch, ULSTUNotFoundError("не должен вызываться"))

	snapshot = run(get_available_groups(1))

	assert snapshot.is_stale is False
	assert snapshot.groups == OLD_GROUPS


def test_successful_update_saves_cache(monkeypatch):
	fresh_groups = [
		{"group": "ПИбд-11", "url": "https://lk.ulstu.ru/new/raspisan.html"},
	]
	patch_groups_fetch(monkeypatch, fresh_groups)

	snapshot = run(get_available_groups(1))

	assert snapshot.is_stale is False
	assert snapshot.groups == fresh_groups

	saved = json.loads(
		get_groups_cache_path(2).read_text(encoding="utf-8")
	)

	assert saved["groups"] == fresh_groups
	assert saved["schedule_part"] == 2


# --- Текст предупреждения ---


def test_stale_warning_contains_date():
	warning = format_stale_groups_warning(
		datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
	)

	assert "устаревшим данным" in warning
	assert "20.09.2026" in warning


def test_stale_warning_without_date():
	warning = format_stale_groups_warning(None)

	assert "устаревшим данным" in warning
	assert "данные от" not in warning