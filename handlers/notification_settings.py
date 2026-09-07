"""
Хендлеры настроек оповещений: включение/выключение,
установка времени отправки расписания на завтра.
"""

from datetime import datetime

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from console_log import log
from database import get_user, update_user
from states.states import MainMenu, NotificationSettings
from utils import delete_after, safe_edit_text

router = Router()


async def build_notification_settings_button(user) -> InlineKeyboardMarkup:
    """Кнопки управления оповещениями: toggle и установка времени."""
    buttons = []
    if user['notification_time'] is not None and user['notification_time'] != "":
        enabled = user['notification_enabled']
        if enabled:
            buttons.append([
                InlineKeyboardButton(
                    text="🔔Включено",
                    callback_data="notification_settings:toggle",
                    style="primary"
                )
            ])
        else:
            buttons.append([
                InlineKeyboardButton(
                    text="🔕Выключено",
                    callback_data="notification_settings:toggle",
                    style="danger"
                )
            ])
    buttons.append([
        InlineKeyboardButton(
            text="🕒Задать время оповещения",
            callback_data="notification_settings:set_time"
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text="◀Назад",
            callback_data="back_to_menu"
        )
    ])
    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


@router.callback_query(
    StateFilter(
        MainMenu.main_menu,
        NotificationSettings.notification_setting
    ),
    F.data.in_({
        "notification_settings:open",
        "notification_settings:toggle",
    }),
)
async def notification_settings_menu_button_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    telegram_id = callback.from_user.id
    user = await get_user(telegram_id)
    action = callback.data.split(":")[1]
    log("notification_settings", f"Настройки оповещений: {action}", telegram_id)

    if action == "toggle":
        enabled = not bool(user['notification_enabled'])
        log(
            "notification_settings",
            f"Автооповещение -> {'ВКЛ' if enabled else 'ВЫКЛ'}",
            telegram_id,
        )
        await update_user(
            telegram_id,
            notification_enabled=enabled
        )
        user = await get_user(telegram_id)

    await render_notification_settings_menu(callback.message, state, user)


async def render_notification_settings_menu(message: Message, state: FSMContext, user: dict | None = None):
    """Рендерит меню настроек оповещений."""
    if user is None:
        telegram_id = message.chat.id
        user = await get_user(telegram_id)

    await state.set_state(NotificationSettings.notification_setting)

    message_text = "Каждый день в указанное время бот присылает расписание на завтра.\n\n"

    if user['notification_time'] is None or user['notification_time'] == "":
        message_text += "Укажите время"
    else:
        message_text += ("<b>Время отправки:</b>\n"
                        f"🕒{user['notification_time']}")
    await safe_edit_text(
        message,
        message_text,
        reply_markup=await build_notification_settings_button(user),
        parse_mode="HTML"
    )


def is_valid_time(value: str) -> bool:
    """Проверяет, что строка соответствует формату ЧЧ:ММ."""
    try:
        datetime.strptime(value, "%H:%M")
        return True
    except ValueError:
        return False


def normalize_time(value: str) -> str:
    """Нормализует время к формату ЧЧ:ММ (убирает пробелы, подтверждает формат)."""
    return datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M")


@router.callback_query(
    NotificationSettings.notification_setting,
    F.data == "notification_settings:set_time"
)
async def set_time_button_handler(
        callback: CallbackQuery,
        state: FSMContext,
):
    await callback.answer()

    sent_message = await callback.message.answer(
        "Введите время в формате ЧЧ:ММ"
    )

    await state.update_data(
        callback_message=callback.message,
        previous_message=sent_message
    )

    await state.set_state(NotificationSettings.wait_for_time)


async def get_last_sent_for_new_time(notification_time: str) -> str:
    """Если новое время ещё не наступило сегодня — сбрасывает дату последней отправки."""
    now = datetime.now().astimezone()
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%Y-%m-%d")

    if notification_time > current_time:
        return ""

    return current_date


@router.message(NotificationSettings.wait_for_time)
async def time_handle(
        message: Message,
        state: FSMContext,
):
    time = message.text.strip()

    if not is_valid_time(time):
        sent_message = await message.answer(
            "Неверный формат.\n"
            "Попробуйте ещё раз"
        )
        await delete_after(sent_message, 5)
        return

    log("notification_settings", f"Установлено время оповещения: {time}", message.chat.id)
    await update_user(
        message.chat.id,
        notification_time=normalize_time(time),
        notification_last_sent=await get_last_sent_for_new_time(time)
    )

    data = await state.get_data()

    await message.delete()
    await data.get("previous_message").delete()
    callback_message = data.get("callback_message")

    await render_notification_settings_menu(
        callback_message,
        state
    )