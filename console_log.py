"""
Логирование на стандартном модуле logging.

Одновременно пишет в консоль (с цветовой подсветкой) и в файл
logs/YYYY-MM-DD.log. Ошибки и предупреждения сторонних библиотек
(aiogram, aiohttp и т.д.) тоже попадают в общий поток логов.

Оформление:
  • время  — ГГГГ-ММ-ДД ЧЧ:ММ:СС.миллисекунды, подсвечивается бирюзовым;
  • место (place) — подсвечивается пурпурным;
  • уровень DEBUG/INFO/WARNING/ERROR/CRITICAL — своим цветом;
  • стандартный вывод ошибок со стек-трейсом при exception-логах.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"

APP_LOGGER_NAME = "ulstu.app"

# ANSI-цвета
RESET = "\033[0m"
BOLD = "\033[1m"
GRAY = "\033[90m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"

LEVEL_COLORS = {
    logging.DEBUG: GRAY,
    logging.INFO: CYAN,
    logging.WARNING: YELLOW,
    logging.ERROR: RED,
    logging.CRITICAL: RED + BOLD,
}


def _use_colors() -> bool:
    """Цвета только в настоящем терминале; отключаются через NO_COLOR."""
    if os.environ.get("NO_COLOR"):
        return False

    try:
        return sys.stdout.isatty()
    except (AttributeError, OSError):
        return False


class _ColorFormatter(logging.Formatter):
    """Форматирует запись с цветами в консоль и без цветов в файл."""

    def __init__(self, use_colors: bool):
        super().__init__()
        self._use_colors = use_colors

    def _format_parts(self, record: logging.LogRecord) -> str:
        message = record.getMessage()

        created = datetime.fromtimestamp(record.created)
        timestamp = created.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        place = getattr(record, "place", record.name or "-")
        who_id = getattr(record, "who", None)
        who = f"user={who_id}" if who_id is not None else "system"

        if self._use_colors:
            color_level = LEVEL_COLORS.get(record.levelno, RESET)
            return (
                f"[{CYAN}{timestamp}{RESET}] "
                f"[{MAGENTA}{place}{RESET}] "
                f"[{GRAY}{who}{RESET}] "
                f"{color_level}{record.levelname:<8}{RESET} "
                f"{message}"
            )

        return (
            f"[{timestamp}] "
            f"[{place}] "
            f"[{who}] "
            f"{record.levelname:<8} "
            f"{message}"
        )

    def format(self, record: logging.LogRecord) -> str:
        line = self._format_parts(record)

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            line += "\n" + record.exc_text

        return line


class _ConsoleHandler(logging.Handler):
    """Пишет в текущий sys.stdout (учитывает patch_stdout в console_worker).

    Обычный logging.StreamHandler захватывает поток один раз при создании,
    поэтому вывод в обход patch_stdout ломал бы строку ввода промпта.
    Здесь поток берётся в момент записи — и логи корректно встают над строкой
    ввода, не перемешиваясь с ней.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


class _DailyFileHandler(logging.Handler):
    """Пишет в файл logs/YYYY-MM-DD.log; каждый день — новый файл."""

    def __init__(self, logs_dir: Path, encoding: str = "utf-8"):
        super().__init__()
        self._logs_dir = logs_dir
        self._encoding = encoding
        self._stream = None
        self._current_date = None
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        self._open_file()

    def _open_file(self) -> None:
        self._current_date = datetime.now().strftime("%Y-%m-%d")
        path = self._logs_dir / f"{self._current_date}.log"
        self._stream = open(path, "a", encoding=self._encoding)

    def emit(self, record: logging.LogRecord) -> None:
        today = datetime.now().strftime("%Y-%m-%d")

        if today != self._current_date:
            self._close_stream()
            self._open_file()

        try:
            message = self.format(record)
            self._stream.write(message + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def close(self) -> None:
        self._close_stream()
        super().close()


_configured = False


def setup_logging() -> None:
    """Настраивает корневой логгер: цветная консоль + ежедневный файл.

    Корневой логгер ловит информацию с уровня WARNING, поэтому ошибки и
    предупреждения сторонних модулей (aiogram, aiohttp и др.) попадают
    в общий поток. Собственные сообщения приложения логируются с INFO.
    """
    global _configured

    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.WARNING)

    console_handler = _ConsoleHandler()
    console_handler.setFormatter(_ColorFormatter(use_colors=_use_colors()))

    file_handler = _DailyFileHandler(LOGS_DIR)
    file_handler.setFormatter(_ColorFormatter(use_colors=False))

    # Убираем хендлеры, добавленные кем-то другим (например, lastResort)
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # warnings.warn тоже уходит в логи
    logging.captureWarnings(True)

    # Логгер приложения: пишет всё от INFO и выше
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = True

    _configured = True


app_logger = logging.getLogger(APP_LOGGER_NAME)


def set_log_level(level: str | int) -> int:
    """Меняет порог логирования для приложения и сторонних модулей.

    Принимает "DEBUG"/"INFO"/"WARNING"/"ERROR"/"CRITICAL" или
    соответствующую константу logging.
    """
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())

        if not isinstance(level, int):
            raise ValueError(f"Неизвестный уровень логирования: {level}")

    level_name = logging.getLevelName(level)
    log("logging", f"Изменение уровня логирования: {level_name}")

    logging.getLogger().setLevel(level)
    app_logger.setLevel(level)

    return level


def log(
        place: str,
        message: str,
        user_id: int | None = None,
        level: str | int = logging.INFO,
) -> None:
    """Логирует сообщение приложения в едином формате.

    place — откуда лог (например, "bot", "main_menu");
    user_id — если задан, выводится как user=<id>;
    level — logging.INFO / "WARNING" / logging.ERROR и т.п.
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    app_logger.log(
        level,
        message,
        extra={"place": place, "who": user_id},
    )


setup_logging()