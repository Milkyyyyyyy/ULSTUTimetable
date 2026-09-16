"""
Консольный воркер: универсальное управление ботом из терминала.

Команды stop, restart, restore_fsm, clear_cache, cache, log_level,
help, users, stats, notify, logs, delete_user, broadcast, db.
Работает с любым ботом — Telegram, VK и др.; через prompt_toolkit.
"""

import asyncio
import logging
import shutil
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.patch_stdout import patch_stdout

from console_log import APP_LOGGER_NAME, LOGS_DIR, log, set_log_level
from database import (
    DB_PATH,
    delete_user,
    get_all_users,
    get_registered_users,
    get_stats,
    get_user,
    get_users_with_notifications,
)
from telegram.notifications import get_users_for_notification, send_batch
from telegram.states.fsm_manager import restore_main_menu_states
from ulstu.schedule import (
    clear_old_cache,
    delete_all_cache,
    get_cache_info,
)

COMMANDS = [
    "stop",
    "restart",
    "restore_fsm",
    "clear_cache",
    "cache",
    "log_level",
    "help",
    "users",
    "stats",
    "notify",
    "logs",
    "delete_user",
    "broadcast",
    "db",
]

LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

HELP = {
    "stop": ("stop", "Остановить бота"),
    "restart": ("restart", "Перезапустить бота"),
    "restore_fsm": (
        "restore_fsm [id]",
        "Восстановить FSM главного меню (все или один пользователь)",
    ),
    "clear_cache": ("clear_cache [all]", "Очистить устаревший кеш (all — весь)"),
    "cache": ("cache info | cache clear [all]", "Инфо о кеше и очистка"),
    "log_level": (
        "log_level [DEBUG|INFO|WARNING|ERROR|CRITICAL]",
        "Уровень логирования (без аргумента — текущий)",
    ),
    "help": ("help [команда]", "Подсказка по командам"),
    "users": ("users [N]", "Список пользователей (первые N, по умолчанию 20)"),
    "stats": ("stats", "Статистика по пользователям"),
    "notify": (
        "notify [all]",
        "Отправить уведомления (по умолчанию — кому пора сейчас, all — всем)",
    ),
    "logs": ("logs [N]", "Последние N строк лога за сегодня (по умолчанию 30)"),
    "delete_user": ("delete_user <id>", "Удалить пользователя из БД"),
    "broadcast": ("broadcast <текст>", "Отправить сообщение всем пользователям"),
    "db": ("db backup", "Сделать резервную копию БД"),
}

completer = WordCompleter(COMMANDS, ignore_case=True)


class RestartRequested(BaseException):
    """Исключение для перезапуска бота вместо выхода с кодом 42."""


session = PromptSession(completer=completer)


async def console_worker(dp, bot):
    # patch_stdout держит строку ввода отдельно внизу терминала: логи
    # (и любые print) встают над ней, а не ломают вводимую команду.
    # raw=True — чтобы сохранить ANSI-цвета из console_log.
    with patch_stdout(raw=True):
        await _console_loop(dp, bot)


async def _console_loop(dp, bot):
    while True:
        try:
            command = await session.prompt_async("> ")
        except (EOFError, KeyboardInterrupt):
            await stop_bot(
                dp,
                "Консоль закрыта (Ctrl+D/Ctrl+C) — останавливаю бота",
            )
            return

        parts = command.strip().split(maxsplit=1)

        if not parts:
            continue

        command_name = parts[0].lower()

        if command_name not in COMMANDS:
            print(
                f"Неизвестная команда: {command}\n"
                f"Доступные команды: {', '.join(COMMANDS)}"
            )
            continue

        argument = parts[1] if len(parts) > 1 else None

        if command_name == "stop":
            await stop_bot(dp, "Получена команда stop — останавливаю бота")
            return

        elif command_name == "restart":
            await stop_bot(
                dp,
                "Получена команда restart — останавливаю polling перед перезапуском",
            )
            raise RestartRequested

        elif command_name == "restore_fsm":
            await restore_fsm(dp, bot, argument)

        elif command_name == "clear_cache":
            await clear_cache(argument)

        elif command_name == "cache":
            await cache_command(argument)

        elif command_name == "log_level":
            await log_level_command(argument)

        elif command_name == "help":
            print_help(argument)

        elif command_name == "users":
            await users_command(argument)

        elif command_name == "stats":
            await stats_command()

        elif command_name == "notify":
            await notify_command(bot, argument)

        elif command_name == "logs":
            await logs_command(argument)

        elif command_name == "delete_user":
            await delete_user_command(dp, bot, argument)

        elif command_name == "broadcast":
            await broadcast_command(bot, argument)

        elif command_name == "db":
            await db_backup_command(argument)


async def stop_bot(dp, message):
    """Останавливает polling бота."""
    log("console", message)
    await dp.stop_polling()


async def restore_fsm(dp, bot, argument):
    if argument is None:
        await restore_main_menu_states(dp, bot)
        print("FSM главного меню восстановлен для всех пользователей")
        return

    try:
        telegram_id = int(argument.split(maxsplit=1)[0])
    except ValueError:
        print("Ошибка: Telegram ID должен быть числом")
        return

    await restore_main_menu_states(dp, bot, telegram_id)
    print(f"FSM главного меню восстановлен для пользователя {telegram_id}")


async def clear_cache(argument):
    if argument is None:
        await asyncio.to_thread(clear_old_cache)
        print("Устаревший кеш очищен")

    elif argument.lower() == "all":
        await asyncio.to_thread(delete_all_cache)
        print("Весь кеш удалён")

    else:
        print("Ошибка: аргумент должен быть 'all' или отсутствовать")


async def cache_command(argument):
    if argument is None or argument.lower() == "info":
        count, size = await asyncio.to_thread(get_cache_info)
        print(f"Кеш: файлов — {count}, размер — {size / 1024 / 1024:.2f} МБ")
        return

    argument = argument.lower()

    if argument == "clear" or argument.startswith("clear "):
        rest = argument[6:].strip() if argument.startswith("clear ") else None
        await clear_cache(rest or None)
        return

    print("Использование: cache info | cache clear [all]")


async def log_level_command(argument):
    if argument is None:
        app_level = logging.getLogger(APP_LOGGER_NAME).getEffectiveLevel()
        print(f"Уровень логирования: {logging.getLevelName(app_level)}")
        return

    level_name = argument.strip().upper()

    if level_name not in LEVEL_NAMES:
        print(f"Ошибка: уровень должен быть один из {', '.join(LEVEL_NAMES)}")
        return

    set_log_level(level_name)
    print(f"Уровень логирования изменён на: {level_name}")


def print_help(argument=None):
    if argument:
        info = HELP.get(argument.lower())

        if info is None:
            print(f"Неизвестная команда: {argument}")
            return

        usage, description = info
        print(f"{usage}\n  {description}")
        return

    for usage, description in HELP.values():
        print(f"{usage:<38} — {description}")


async def users_command(argument):
    limit = 20

    if argument is not None:
        try:
            limit = int(argument.split(maxsplit=1)[0])
        except ValueError:
            print("Ошибка: число должно быть числом")
            return

    users = await get_all_users()

    print(f"Всего пользователей: {len(users)}")
    print(f"{'Telegram ID':<14} {'Группа':<16} Увед.")

    for user in users[:limit]:
        notif = "да" if user["notification_enabled"] else "—"
        print(
            f"{user['telegram_id']:<14} "
            f"{str(user['group_name'] or '—'):<16} {notif}"
        )

    if len(users) > limit:
        print(f"... ещё {len(users) - limit} пользователей")


async def stats_command():
    stats = await get_stats()

    print(
        "Статистика:\n"
        f"  Пользователей всего:          {stats['total']}\n"
        f"  С включёнными уведомлениями:  {stats['notification_enabled']}\n"
        f"  С логином УлГТУ:              {stats['with_login']}"
    )


async def notify_command(bot, argument):
    now = datetime.now().astimezone()
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%Y-%m-%d")

    if argument is not None and argument.lower() == "all":
        users = await get_users_with_notifications()
        label = "всем с включёнными уведомлениями"
    else:
        users = await get_users_for_notification(
            current_time,
            current_date,
        )
        label = f"по расписанию ({current_time})"

    if not users:
        print(f"Нет пользователей для отправки ({label})")
        return

    print(f"Отправка уведомлений {len(users)} пользователям ({label})...")
    await send_batch(bot, users, current_date)
    print("Уведомления отправлены")


def read_log_tail(limit: int) -> str:
    path = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    if not path.exists():
        return "Лог за сегодня не найден"

    lines = path.read_text(encoding="utf-8").splitlines()

    if not lines:
        return "(лог пуст)"

    return "\n".join(lines[-limit:])


async def logs_command(argument):
    limit = 30

    if argument is not None:
        try:
            limit = int(argument.split(maxsplit=1)[0])
        except ValueError:
            print("Ошибка: число строк должно быть числом")
            return

    print(await asyncio.to_thread(read_log_tail, limit))


async def delete_user_command(dp, bot, argument):
    if argument is None:
        print("Использование: delete_user <telegram_id>")
        return

    try:
        telegram_id = int(argument.split(maxsplit=1)[0])
    except ValueError:
        print("Ошибка: Telegram ID должен быть числом")
        return

    user = await get_user(telegram_id)

    if user is None:
        print(f"Пользователь {telegram_id} не найден")
        return

    group = user["group_name"] or "—"
    confirm = await session.prompt_async(
        f"Удалить {telegram_id} (группа {group})? [y/N] "
    )

    if confirm.strip().lower() != "y":
        print("Отменено")
        return

    await delete_user(telegram_id)

    context = dp.fsm.get_context(
        bot=bot,
        chat_id=telegram_id,
        user_id=telegram_id,
    )
    await context.set_state(None)

    log("console", f"Пользователь {telegram_id} удалён из БД", telegram_id)


async def broadcast_command(bot, argument):
    if argument is None:
        print("Использование: broadcast <текст>")
        return

    users = await get_registered_users()

    if not users:
        print("Нет зарегистрированных пользователей")
        return

    confirm = await session.prompt_async(
        f"Отправить сообщение {len(users)} пользователям? [y/N] "
    )

    if confirm.strip().lower() != "y":
        print("Отменено")
        return

    sent = 0
    failed = 0

    for user in users:
        telegram_id = user["telegram_id"]

        try:
            await bot.send_message(chat_id=telegram_id, text=argument)
            sent += 1

        except Exception as e:
            failed += 1
            log(
                "console",
                f"Ошибка отправки сообщения: {type(e).__name__}: {e}",
                telegram_id,
                level="ERROR",
            )

        await asyncio.sleep(0.05)

    print(f"Рассылка завершена: отправлено — {sent}, ошибок — {failed}")


async def db_backup_command(argument):
    if argument is None or argument.lower() != "backup":
        print("Использование: db backup")
        return

    if not DB_PATH.exists():
        print(f"База данных не найдена: {DB_PATH}")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.with_name(f"timetable_backup_{timestamp}.db")

    await asyncio.to_thread(shutil.copy2, DB_PATH, backup_path)

    log("console", f"Создана резервная копия БД: {backup_path}")
    print(f"Резервная копия создана: {backup_path}")
