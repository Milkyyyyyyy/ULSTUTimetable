from aiogram import Bot, Dispatcher

from console_log import log
from database import get_registered_users
from states.states import MainMenu


async def restore_main_menu_states(
        dp: Dispatcher,
        bot: Bot,
        telegram_id: int | None = None,
):
    if telegram_id is None:
        users = await get_registered_users()

        log(
            "bot",
            f"Восстановление FSM для {len(users)} пользователей"
        )

        for user in users:
            user_id = user["telegram_id"]

            context = dp.fsm.get_context(
                bot=bot,
                chat_id=user_id,
                user_id=user_id,
            )

            await context.set_state(MainMenu.main_menu)

        log("bot", "FSM главного меню восстановлен")

    else:
        context = dp.fsm.get_context(
            bot=bot,
            chat_id=telegram_id,
            user_id=telegram_id,
        )

        await context.set_state(MainMenu.main_menu)

        log(
            "bot",
            f"FSM главного меню восстановлен для пользователя {telegram_id}"
        )
