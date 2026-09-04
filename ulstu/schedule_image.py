from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Шрифты
# ---------------------------------------------------------------------------

def get_font(size: int, bold: bool = False):
	"""
	Ищет шрифт сначала в Windows, затем в Linux.
	"""

	if bold:
		candidates = [
			"C:/Windows/Fonts/arialbd.ttf",
			"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
		]
	else:
		candidates = [
			"C:/Windows/Fonts/arial.ttf",
			"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
		]

	for path in candidates:
		if Path(path).exists():
			return ImageFont.truetype(path, size)

	return ImageFont.load_default()


FONT_TITLE = get_font(28, bold=True)

FONT_DAY = get_font(22, bold=True)

FONT_HEADER = get_font(20, bold=True)

FONT_SUBJECT = get_font(19, bold=True)
FONT_TYPE = get_font(17)
FONT_TEACHER = get_font(17)
FONT_ROOM = get_font(17)


# ---------------------------------------------------------------------------
# Перенос текста
# ---------------------------------------------------------------------------

def wrap_text(
		draw: ImageDraw.ImageDraw,
		text: str,
		font,
		max_width: int,
) -> list[str]:

	words = text.split()

	if not words:
		return [""]

	lines = []
	current_line = words[0]

	for word in words[1:]:

		test_line = f"{current_line} {word}"

		bbox = draw.textbbox(
			(0, 0),
			test_line,
			font=font,
		)

		width = bbox[2] - bbox[0]

		if width <= max_width:
			current_line = test_line

		else:
			lines.append(current_line)
			current_line = word

	lines.append(current_line)

	return lines


# ---------------------------------------------------------------------------
# Фильтр подгруппы
# ---------------------------------------------------------------------------

def filter_lessons(
		lesson_items: list[dict],
		user_subgroup: int | None,
) -> list[dict]:

	result = []

	for item in lesson_items:

		# Общее занятие
		if item["subgroup"] is None:
			result.append(item)

		# Наша подгруппа
		elif (
				user_subgroup is None
				or item["subgroup"] == user_subgroup
		):
			result.append(item)

	return result


# ---------------------------------------------------------------------------
# Генерация расписания на неделю
# ---------------------------------------------------------------------------

def generate_week_schedule_image(
		week: dict,
		user_subgroup: int | None = None,
) -> BytesIO:

	days = week.get("days", [])

	if not days:
		result = BytesIO()

		image = Image.new(
			"RGB",
			(800, 300),
			"white",
		)

		draw = ImageDraw.Draw(image)

		draw.text(
			(30, 30),
			"Расписание отсутствует",
			fill="black",
			font=FONT_TITLE,
		)

		image.save(
			result,
			format="PNG",
		)

		result.seek(0)

		return result

	# ------------------------------------------------------------------
	# Все номера пар
	# ------------------------------------------------------------------

	lesson_numbers = set()

	for day in days:
		for lesson in day.get("lessons", []):
			lesson_numbers.add(
				lesson["lesson_number"]
			)

	lesson_numbers = sorted(lesson_numbers)

	# ------------------------------------------------------------------
	# Размеры колонок
	# ------------------------------------------------------------------

	day_column_width = 150
	lesson_column_width = 270

	title_height = 65
	header_height = 75

	# Временно создаём canvas только для измерения текста.
	measure_image = Image.new(
		"RGB",
		(1, 1),
		"white",
	)

	measure_draw = ImageDraw.Draw(
		measure_image
	)

	# ------------------------------------------------------------------
	# Вычисляем высоту каждой строки
	# ------------------------------------------------------------------

	row_heights = []

	for day in days:

		row_height = 80

		for lesson in day.get("lessons", []):

			lesson_height = calculate_lesson_height(
				draw=measure_draw,
				lesson=lesson,
				max_width=lesson_column_width - 20,
				user_subgroup=user_subgroup,
			)

			row_height = max(
				row_height,
				lesson_height,
			)

		row_heights.append(row_height)

	# ------------------------------------------------------------------
	# Размер изображения
	# ------------------------------------------------------------------

	table_width = (
			day_column_width
			+ lesson_column_width
			* len(lesson_numbers)
	)

	table_height = (
			title_height
			+ header_height
			+ sum(row_heights)
			+ 20
	)

	image = Image.new(
		"RGB",
		(
			table_width,
			table_height,
		),
		"white",
	)

	draw = ImageDraw.Draw(image)

	# ------------------------------------------------------------------
	# Заголовок
	# ------------------------------------------------------------------

	week_number = week["week"]
	date_range = week.get("date_range") or ()
	start_date = date_range[0] if len(date_range) > 0 else ""
	end_date = date_range[1] if len(date_range) > 1 else ""

	title = (
		f"Расписание • Неделя {week_number} • "
		f"{start_date} — {end_date}"
	)

	draw.text(
		(10, 15),
		title,
		fill="black",
		font=FONT_TITLE,
	)

	table_top = title_height

	# ------------------------------------------------------------------
	# Заголовок таблицы
	# ------------------------------------------------------------------

	draw.rectangle(
		[
			0,
			table_top,
			day_column_width,
			table_top + header_height,
		],
		outline="black",
		width=2,
	)

	draw.text(
		(
			15,
			table_top + 12,
		),
		"День",
		fill="black",
		font=FONT_HEADER,
	)

	draw.text(
		(
			15,
			table_top + 42,
		),
		"Дата",
		fill="black",
		font=FONT_TYPE,
	)

	# ------------------------------------------------------------------
	# Заголовки пар
	# ------------------------------------------------------------------

	for lesson_index, lesson_number in enumerate(
			lesson_numbers
	):

		x1 = (
				day_column_width
				+ lesson_index
				* lesson_column_width
		)

		x2 = x1 + lesson_column_width

		draw.rectangle(
			[
				x1,
				table_top,
				x2,
				table_top + header_height,
			],
			outline="black",
			width=2,
		)

		lesson_time = ""

		for day in days:

			for lesson in day.get("lessons", []):

				if lesson["lesson_number"] == lesson_number:
					lesson_time = lesson["time"]
					break

			if lesson_time:
				break

		draw.text(
			(
				x1 + 10,
				table_top + 10,
			),
			f"{lesson_number}-я",
			fill="black",
			font=FONT_HEADER,
		)

		draw.text(
			(
				x1 + 10,
				table_top + 42,
			),
			lesson_time,
			fill="black",
			font=FONT_TYPE,
		)

	# ------------------------------------------------------------------
	# Строки дней
	# ------------------------------------------------------------------

	current_y = (
			table_top
			+ header_height
	)

	for day_index, day in enumerate(days):

		row_top = current_y
		row_bottom = (
				row_top
				+ row_heights[day_index]
		)

		# --------------------------------------------------------------
		# День
		# --------------------------------------------------------------

		draw.rectangle(
			[
				0,
				row_top,
				day_column_width,
				row_bottom,
			],
			outline="black",
			width=2,
		)

		day_parts = day["day"].split(",")

		day_name = day_parts[0].strip()
		day_date = day["date"]

		draw.text(
			(
				15,
				row_top + 20,
			),
			day_name,
			fill="black",
			font=FONT_DAY,
		)

		draw.text(
			(
				15,
				row_top + 52,
			),
			day_date,
			fill="black",
			font=FONT_HEADER,
		)

		# --------------------------------------------------------------
		# Пары
		# --------------------------------------------------------------

		for lesson_index, lesson_number in enumerate(
				lesson_numbers
		):

			x1 = (
					day_column_width
					+ lesson_index
					* lesson_column_width
			)

			x2 = (
					x1
					+ lesson_column_width
			)

			draw.rectangle(
				[
					x1,
					row_top,
					x2,
					row_bottom,
				],
				outline="black",
				width=2,
			)

			# ----------------------------------------------------------
			# Ищем пару
			# ----------------------------------------------------------

			current_lesson = None

			for lesson in day.get("lessons", []):

				if lesson["lesson_number"] == lesson_number:
					current_lesson = lesson
					break

			if current_lesson is None:
				continue

			visible_lessons = filter_lessons(
				current_lesson["lessons"],
				user_subgroup,
			)

			if not visible_lessons:
				continue

			# ----------------------------------------------------------
			# Вывод
			# ----------------------------------------------------------

			y = row_top + 10

			for item_index, item in enumerate(
					visible_lessons
			):

				subject_lines = wrap_text(
					draw,
					item["subject"],
					FONT_SUBJECT,
					lesson_column_width - 20,
				)

				for line in subject_lines:

					draw.text(
						(
							x1 + 10,
							y,
						),
						line,
						fill="black",
						font=FONT_SUBJECT,
					)

					y += 23

				draw.text(
					(
						x1 + 10,
						y,
					),
					item["type"],
					fill="black",
					font=FONT_TYPE,
				)

				y += 22

				teacher_lines = wrap_text(
					draw,
					item["teacher"],
					FONT_TEACHER,
					lesson_column_width - 20,
				)

				for line in teacher_lines:

					draw.text(
						(
							x1 + 10,
							y,
						),
						line,
						fill="black",
						font=FONT_TEACHER,
					)

					y += 22

				draw.text(
					(
						x1 + 10,
						y,
					),
					f"Ауд. {item['room']}",
					fill="black",
					font=FONT_ROOM,
				)

				y += 23

				if (
						item_index
						< len(visible_lessons) - 1
				):

					draw.line(
						(
							x1 + 10,
							y + 3,
							x2 - 10,
							y + 3,
						),
						fill="gray",
						width=1,
					)

					y += 12

		current_y = row_bottom

	# ------------------------------------------------------------------
	# Сохраняем
	# ------------------------------------------------------------------

	result = BytesIO()

	image.save(
		result,
		format="PNG",
	)

	result.seek(0)

	return result


def calculate_lesson_height(
		draw: ImageDraw.ImageDraw,
		lesson: dict | None,
		max_width: int,
		user_subgroup: int | None,
) -> int:
	"""
	Вычисляет, сколько места нужно ячейке с одной парой.
	"""

	if lesson is None:
		return 0

	visible_lessons = filter_lessons(
		lesson["lessons"],
		user_subgroup,
	)

	if not visible_lessons:
		return 0

	height = 10

	for index, item in enumerate(visible_lessons):

		# Предмет
		subject_lines = wrap_text(
			draw,
			item["subject"],
			FONT_SUBJECT,
			max_width,
		)

		height += len(subject_lines) * 23

		# Тип
		height += 22

		# Преподаватель
		teacher_lines = wrap_text(
			draw,
			item["teacher"],
			FONT_TEACHER,
			max_width,
		)

		height += len(teacher_lines) * 22

		# Аудитория
		height += 23

		# Разделитель
		if index < len(visible_lessons) - 1:
			height += 15

	height += 10

	return height
