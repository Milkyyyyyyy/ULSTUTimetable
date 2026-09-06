import asyncio

from console_log import log
from fsm_manager import restore_main_menu_states
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter

COMMANDS = [
    "stop",
    "restart",
    "restore_fsm",
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