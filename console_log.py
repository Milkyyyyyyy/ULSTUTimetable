"""
Простой консольный логгер:
пишет в stdout и сохраняет логи в logs/YYYY-MM-DD.log.
"""

from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"


def log(
        place: str,
        message: str,
        user_id: int | None = None,
) -> None:
    """
    Лог:
    [время] [место] [кто] что произошло

    Одновременно выводится в консоль и записывается
    в файл logs/YYYY-MM-DD.log.
    """

    now = datetime.now()

    time = now.strftime("%Y-%m-%d %H:%M:%S")
    date = now.strftime("%Y-%m-%d")

    who = (
        f"user={user_id}"
        if user_id is not None
        else "system"
    )

    log_message = (
        f"[{time}] [{place}] [{who}] {message}"
    )

    # Вывод в консоль
    print(log_message)

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        log_file = LOGS_DIR / f"{date}.log"
        with log_file.open("a", encoding="utf-8") as file:
            file.write(f"{log_message}\n")

    except OSError as e:
        print(f"Ошибка записи лога: {e}")