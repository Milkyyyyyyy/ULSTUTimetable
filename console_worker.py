"""
Консольный воркер: позволяет управлять ботом из терминала
(команды stop, restart, restore_fsm) через prompt_toolkit.
"""

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter

from console_log import log
from states.fsm_manager import restore_main_menu_states
from ulstu.schedule import clear_old_cache, delete_all_cache

COMMANDS = [
    "stop",
    "restart",
    "restore_fsm",
    "clear_cache",
]

completer = WordCompleter(
    COMMANDS,
    ignore_case=True,
)

session = PromptSession(completer=completer)


async def console_worker(dp, bot):
    while True:
        command = await session.prompt_async("> ")

        parts = command.strip().split(maxsplit=1)

        if not parts:
            continue

        command_name = parts[0].lower()
        argument = parts[1] if len(parts) > 1 else None

        if command_name == "stop":
            await stop_bot(dp)
            return

        elif command_name == "restore_fsm":
            await restore_fsm(dp, bot, argument)

        elif command_name == "restart":
            log("console", "Получена команда restart")
            await stop_bot(dp)
            raise SystemExit(42)
        elif command_name == "clear_cache":
            if argument == "all":
                delete_all_cache();
            else:
                clear_old_cache()

        else:
            print(f"Неизвестная команда: {command}")


async def stop_bot(dp):
    log("console", "Получена команда stop")
    await dp.stop_polling()

async def restore_fsm(dp, bot, argument):
    if argument is None:
        await restore_main_menu_states(dp, bot)
    else:
        try:
            telegram_id = int(argument)
        except ValueError:
            print("Ошибка: Telegram ID должен быть числом")
            return

        await restore_main_menu_states(
            dp,
            bot,
            telegram_id,
        )