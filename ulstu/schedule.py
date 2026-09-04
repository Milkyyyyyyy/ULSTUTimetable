from datetime import date
from bs4 import BeautifulSoup
import re

from database import get_user
from ulstu.client import get_group_schedule
from validator.group import normalize_group
from datetime import datetime, date, timedelta
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / 'cache'
CACHE_TTL = timedelta(minutes=60)

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
def is_cache_fresh(updated_at: str) -> bool:
    updated = datetime.fromisoformat(updated_at)
    return datetime.now().astimezone() - updated < CACHE_TTL

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
