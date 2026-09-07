"""
Общие inline-клавиатуры, используемые в нескольких обработчиках
(регистрация, настройки), чтобы не дублировать их описание.
"""

from aiogram.types import InlineKeyboardButton
from aiogram.types import InlineKeyboardMarkup


# Выбор части расписания (факультета) при регистрации и в настройках
schedule_parts_keyboard = InlineKeyboardMarkup(
	inline_keyboard=[
		[
			InlineKeyboardButton(
				text="МФ, РТФ, ЭФ, ИФМИ",
				callback_data="schedule_part:1",
				style="success"
			),
			InlineKeyboardButton(
				text="ФИСТ, ГФ",
				callback_data="schedule_part:2",
				style="success"
			)
		],
		[
			InlineKeyboardButton(
				text="ИАТУ, ИЭФ, ЗВФ ИННО",
				callback_data="schedule_part:3",
				style="success"
			),
			InlineKeyboardButton(
				text="КЭИ",
				callback_data="schedule_part:4",
				style="success"
			)
		],
		[
			InlineKeyboardButton(
				text="СФ",
				callback_data="schedule_part:5",
				style="success"
			)
		],
	]
)


def build_subgroup_keyboard(skip_label: str) -> InlineKeyboardMarkup:
	"""Клавиатура выбора подгруппы; skip-кнопка получает свой текст."""
	return InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(
					text="1 подгруппа",
					callback_data="subgroup:1",
					style="primary"
				),
				InlineKeyboardButton(
					text="2 подгруппа",
					callback_data="subgroup:2",
					style="primary"
				)
			],
			[
				InlineKeyboardButton(
					text=skip_label,
					callback_data="subgroup:skip",
					style="danger"
				)
			]
		]
	)