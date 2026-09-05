import csv
from datetime import datetime
from pathlib import Path


REQUEST_LOG_PATH = Path("logs/request_log.csv")

FIELDS = [
    "timestamp",
    "telegram_id",
    "operation",
    "schedule_part",
    "url",
    "cache_hit",
    "success",
]


def log_request(
    operation: str,
    telegram_id: int | None = None,
    schedule_part: int | None = None,
    url: str = "",
    cache_hit: bool | None = None,
    success: bool = True,
):
    REQUEST_LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_exists = REQUEST_LOG_PATH.exists()

    with REQUEST_LOG_PATH.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDS,
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "timestamp": datetime.now().astimezone().isoformat(),
            "telegram_id": telegram_id,
            "operation": operation,
            "schedule_part": schedule_part,
            "url": url,
            "cache_hit": cache_hit,
            "success": success,
        })