"""Тесты шрифтов картинки расписания.

Главная проверка — картинка не зависит от шрифтов, установленных на машине:
шрифт берётся из assets/fonts, обращения к fontconfig не происходит.
"""
import importlib
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from PIL import ImageFont

from ulstu import schedule_image
from ulstu.schedule_image import (
	BUNDLED_FONTS,
	FONTS_DIR,
	generate_week_schedule_image,
	get_font,
)

MODULE_FONTS = {
	"FONT_TITLE": schedule_image.FONT_TITLE,
	"FONT_DAY": schedule_image.FONT_DAY,
	"FONT_HEADER": schedule_image.FONT_HEADER,
	"FONT_SUBJECT": schedule_image.FONT_SUBJECT,
	"FONT_TYPE": schedule_image.FONT_TYPE,
	"FONT_TEACHER": schedule_image.FONT_TEACHER,
	"FONT_ROOM": schedule_image.FONT_ROOM,
}

# Символ из приватной области Unicode: в шрифте его точно нет,
# поэтому Pillow рисует для него «плашку» .notdef.
MISSING_GLYPH = "\ue000"

CYRILLIC = (
	"АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
	"абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
	"№—«»…"
)


def _render_mask(font: ImageFont.FreeTypeFont, text: str) -> bytes:
	return bytes(font.getmask(text))


def _week() -> dict:
	return {
		"week": 3,
		"date_range": ("14.09.2026", "20.09.2026"),
		"days": [
			{
				"day": "Понедельник, 14.09.2026",
				"date": "14.09",
				"lessons": [
					{
						"lesson_number": 1,
						"time": "08:00 - 09:30",
						"lessons": [
							{
								"type": "лек.",
								"subject": "Математика — дифференциальные уравнения",
								"teacher": "Иванов Иван Иванович",
								"room": "Г-204",
								"subgroup": None,
							},
						],
					},
					{
						"lesson_number": 2,
						"time": "09:50 - 11:20",
						"lessons": [
							{
								"type": "пр.",
								"subject": "Иностранный язык",
								"teacher": "Петрова А. С.",
								"room": "А-12",
								"subgroup": 2,
							},
						],
					},
				],
			},
			{
				"day": "Вторник, 15.09.2026",
				"date": "15.09",
				"lessons": [],
			},
		],
	}


# --- Встроенные файлы шрифтов ---


def test_bundled_font_files_exist():
	assert FONTS_DIR.is_dir()

	for bold in (False, True):
		path = BUNDLED_FONTS[bold]

		assert path.is_file(), f"Нет встроенного шрифта: {path}"
		assert path.stat().st_size > 50_000


def test_bundled_fonts_not_ignored_by_git():
	gitignore = FONTS_DIR.parent.parent / ".gitignore"

	if not gitignore.is_file():
		pytest.skip(".gitignore не найден")

	patterns = [
		line.strip()
		for line in gitignore.read_text(encoding="utf-8").splitlines()
		if line.strip() and not line.startswith("#")
	]

	assert not any(
		pattern in ("*.ttf", "*.otf", "assets/", "assets/fonts/")
		for pattern in patterns
	), "Шрифты не должны попадать под .gitignore"


def test_license_file_present():
	assert (FONTS_DIR / "OFL.txt").is_file()


# --- Выбор шрифта ---


def test_find_font_file_returns_bundled():
	assert schedule_image.find_font_file(False) == str(BUNDLED_FONTS[False])
	assert schedule_image.find_font_file(True) == str(BUNDLED_FONTS[True])


def test_module_fonts_come_from_bundled_files():
	for name, font in MODULE_FONTS.items():
		assert isinstance(font, ImageFont.FreeTypeFont), f"{name} не TrueType"

		path = Path(font.path)

		assert path.parent == FONTS_DIR, f"{name} загружен не из assets/fonts: {path}"


def test_bold_and_regular_are_different_files():
	regular = get_font(20)
	bold = get_font(20, bold=True)

	assert regular.path != bold.path
	assert _render_mask(regular, "Расписание") != _render_mask(bold, "Расписание")


def test_font_size_is_respected():
	assert get_font(28, bold=True).size == 28
	assert get_font(17).size == 17


# --- Кириллица ---


@pytest.mark.parametrize("bold", [False, True])
def test_cyrillic_glyphs_are_not_tofu(bold):
	"""Каждый символ должен иметь свой глиф, а не заглушку .notdef."""
	font = get_font(20, bold=bold)

	missing_box = _render_mask(font, MISSING_GLYPH)

	assert missing_box, "Символ вне cmap должен что-то рисоваться"

	for char in CYRILLIC:
		assert _render_mask(font, char) != missing_box, (
			f"Символ {char!r} (U+{ord(char):04X}) отрисован заглушкой"
		)


# --- Запасные варианты ---


def test_fallback_to_system_font(tmp_path, monkeypatch):
	fake_system_font = tmp_path / "FakeSystem.ttf"
	fake_system_font.write_bytes(BUNDLED_FONTS[False].read_bytes())

	monkeypatch.setattr(
		schedule_image,
		"BUNDLED_FONTS",
		{False: tmp_path / "нет-регулярного.ttf", True: tmp_path / "нет-жирного.ttf"},
	)
	monkeypatch.setattr(schedule_image, "SYSTEM_FONT_CANDIDATES", {True: [], False: []})
	monkeypatch.setattr(schedule_image, "_linux_font_via_fontconfig", lambda bold: None)

	monkeypatch.setitem(
		schedule_image.SYSTEM_FONT_CANDIDATES,
		False,
		[str(fake_system_font)],
	)

	assert schedule_image.find_font_file(False) == str(fake_system_font)

	font = get_font(20)

	assert isinstance(font, ImageFont.FreeTypeFont)
	assert font.path == str(fake_system_font)


def test_fallback_to_pillow_default_font(tmp_path, monkeypatch):
	monkeypatch.setattr(
		schedule_image,
		"BUNDLED_FONTS",
		{False: tmp_path / "нет.ttf", True: tmp_path / "нет-жирного.ttf"},
	)
	monkeypatch.setattr(schedule_image, "SYSTEM_FONT_CANDIDATES", {True: [], False: []})
	monkeypatch.setattr(schedule_image, "_linux_font_via_fontconfig", lambda bold: None)

	assert schedule_image.find_font_file() is None

	font = get_font(20)

	assert font.size == 20


# --- Картинка целиком ---


def test_week_image_is_png():
	image = generate_week_schedule_image(
		_week(),
		user_subgroup=2,
		group_name="ИВТИ-83-1",
	)

	data = image.getvalue()

	assert data[:8] == b"\x89PNG\r\n\x1a\n"
	assert len(data) > 1_000


def test_week_image_is_deterministic():
	"""Два одинаковых расписания дают побайтово одинаковые картинки."""
	first = generate_week_schedule_image(_week(), user_subgroup=2, group_name="ИВТИ-83-1")
	second = generate_week_schedule_image(_week(), user_subgroup=2, group_name="ИВТИ-83-1")

	assert first.getvalue() == second.getvalue()


def _fail_on_fontconfig(*args, **kwargs):
	raise AssertionError("Обращение к fontconfig недопустимо: шрифт встроенный")


def _reload_module(monkeypatch) -> ModuleType:
	"""Переимпортирует модуль, запретив любой поиск шрифта в системе."""
	monkeypatch.setattr(subprocess, "run", _fail_on_fontconfig)

	try:
		return importlib.reload(schedule_image)
	finally:
		monkeypatch.undo()


def test_image_does_not_use_system_fonts(monkeypatch):
	"""Системные шрифты не участвуют: картинка совпадает с эталонной."""
	expected = generate_week_schedule_image(
		_week(),
		user_subgroup=2,
		group_name="ИВТИ-83-1",
	).getvalue()

	reloaded = _reload_module(monkeypatch)

	try:
		for name in MODULE_FONTS:
			font = getattr(reloaded, name)

			assert Path(font.path).parent == FONTS_DIR

		actual = reloaded.generate_week_schedule_image(
			_week(),
			user_subgroup=2,
			group_name="ИВТИ-83-1",
		).getvalue()
	finally:
		importlib.reload(schedule_image)

	assert actual == expected
