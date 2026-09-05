import random
from datetime import date, timedelta, datetime

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from console_log import log
from database import get_user, update_user
from states.states import MainMenu, ScheduleSelection, NotificationSettings
from ulstu.schedule import (
    get_schedule_for_date,
    get_schedule,
    send_schedule,
    format_schedule_error,
)
from ulstu.schedule_image import generate_week_schedule_image
from utils import safe_edit_text, build_delete_button, delete_after

router = Router()

WELCOME_MESSAGES = [
    "С возвращением!",
    "Добро пожаловать обратно!",
    "Рад снова тебя видеть.",
    "Что сегодня по расписанию?",
    "Проверим расписание?",
    "Готово. Можно посмотреть расписание.",
    "Расписание готово.",
    "Можно начинать.",
    "Что тебя ждёт сегодня?",
    "Посмотрим, что запланировано.",
    "Всё готово к работе.",
    "Добро пожаловать!",
    "Хорошего дня!",
    "Давай посмотрим расписание.",
    "Расписание на месте.",
]


def build_empty_day(target_date: date) -> dict:
    return {
        "day": target_date.strftime("%d.%m.%Y"),
        "date": target_date.strftime("%d.%m.%Y"),
        "lessons": [],
    }


async def build_main_menu_buttons(
        telegram_id: int,
) -> InlineKeyboardMarkup:

    user = await get_user(telegram_id)

    buttons = []

    if user["notification_enabled"] == 1:
        buttons.append([
            InlineKeyboardButton(
                text="🔔 Автооповещение: ВКЛ",
                callback_data="notification_settings:open",
                style="primary",
            )
        ])

    else:
        buttons.append([
            InlineKeyboardButton(
                text="🔔 Автооповещение: ВЫКЛ",
                callback_data="notification_settings:open",
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="🗓 Сегодня",
            callback_data="schedule:today",
            style="success",
        ),
        InlineKeyboardButton(
            text="🗓 Завтра",
            callback_data="schedule:tomorrow",
            style="success",
        ),
    ])

    buttons.append([
        InlineKeyboardButton(
            text="На неделю",
            callback_data="schedule_week:this",
            style="success",
        ),
        InlineKeyboardButton(
            text="На следующую неделю",
            callback_data="schedule_week:next",
            style="success",
        ),
    ])

    buttons.append([
        InlineKeyboardButton(
            text="📅 Расписание на дату",
            callback_data="schedule:select",
            style="success",
        ),
    ])

    buttons.append([
        InlineKeyboardButton(
            text="⚙ Настройки",
            callback_data="open_settings",
            style="primary",
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


async def show_main_menu(
        message: Message,
        state: FSMContext,
        edit_previous_message: bool = False,
):
    log("main_menu", "Открытие главного меню", message.chat.id)

    await state.clear()
    await state.set_state(MainMenu.main_menu)

    message_text = random.choice(WELCOME_MESSAGES)

    if edit_previous_message:
        await safe_edit_text(
            message,
            message_text,
            await build_main_menu_buttons(message.chat.id),
        )
    else:
        await message.answer(
            message_text,
            reply_markup=await build_main_menu_buttons(message.chat.id),
        )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    log("main_menu", "Назад в главное меню", callback.from_user.id)
    await show_main_menu(callback.message, state, edit_previous_message=True)


# Клавиатура выбора недели и дня

def build_schedule_keyboard(
        schedule: list[dict],
        week_index: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Защита от некорректного индекса
    if not schedule:
        return builder.as_markup()

    if week_index < 0:
        week_index = 0

    if week_index >= len(schedule):
        week_index = len(schedule) - 1

    week = schedule[week_index]
    days = week.get("days", [])

    # Кнопки дней

    for row_index in range(3):
        row_buttons = []

        for day_index in (row_index, row_index + 3):
            if day_index >= len(days):
                continue

            row_buttons.append(
                InlineKeyboardButton(
                    text=days[day_index]["day"],
                    callback_data=f"schedule_day:{week_index}:{day_index}",
                )
            )

        if row_buttons:
            builder.row(*row_buttons)

    # Воскресенье выносим в отдельную строку
    if len(days) > 6:
        day = days[6]

        builder.row(
            InlineKeyboardButton(
                text=day["day"],
                callback_data=f"schedule_day:{week_index}:6",
            )
        )

    # Навигация по неделям

    navigation_buttons = []

    if week_index > 0:
        navigation_buttons.append(
            InlineKeyboardButton(
                text="←",
                callback_data=f"schedule_select_week:{week_index - 1}",
            )
        )

    navigation_buttons.append(
        InlineKeyboardButton(
            text=f"Неделя {week['week']}",
            callback_data=f"schedule_week_current:{week_index}",
            style="success",
        )
    )

    if week_index < len(schedule) - 1:
        navigation_buttons.append(
            InlineKeyboardButton(
                text="→",
                callback_data=f"schedule_select_week:{week_index + 1}",
            )
        )

    builder.row(*navigation_buttons)

    builder.row(
        InlineKeyboardButton(
            text="◀ Назад",
            callback_data="back_to_menu",
            style="primary",
        )
    )

    return builder.as_markup()


# Открытие расписания: сегодня / завтра

@router.callback_query(
    MainMenu.main_menu,
    F.data.startswith("schedule:"),
)
async def schedule_button_handler(
        callback: CallbackQuery,
        state: FSMContext,
):
    await callback.answer()

    action = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    log("main_menu", f"Запрос расписания: {action}", user_id)

    try:
        schedule = await get_schedule(user_id)
    except Exception as error:
        log(
            "main_menu",
            f"Ошибка получения расписания ({action}): {error}",
            user_id,
        )
        sent_message = await callback.message.answer(
            format_schedule_error(error)
        )
        await delete_after(sent_message, 8)
        return

    if action == "today":
        today = date.today()
        schedule_date = get_schedule_for_date(
            schedule,
            today,
        )
        log("main_menu", f"Отправка расписания на {today}", user_id)

        await send_schedule(
            callback.message,
            schedule_date or build_empty_day(today),
        )

        return

    if action == "tomorrow":
        tomorrow = date.today() + timedelta(days=1)

        schedule_date = get_schedule_for_date(
            schedule,
            tomorrow,
        )
        log("main_menu", f"Отправка расписания на {tomorrow}", user_id)

        await send_schedule(
            callback.message,
            schedule_date or build_empty_day(tomorrow),
        )

        return

    if action == "select":

        if not schedule:
            log("main_menu", "Расписание пустое при выборе даты", user_id)
            await callback.message.edit_text(
                "❌ Расписание отсутствует.\n\n"
                "💡 Возможно, оно ещё не опубликовано "
                "на сайте УлГТУ. Попробуйте позже."
            )
            return

        # Сохраняем schedule в FSM, чтобы при переключении недель не запрашивать его заново
        await state.update_data(
            schedule=schedule,
            week_index=0,
        )

        await state.set_state(
            ScheduleSelection.selecting_day
        )

        keyboard = build_schedule_keyboard(
            schedule,
            week_index=0,
        )

        log("main_menu", "Открыт выбор дня", user_id)
        await callback.message.edit_text(
            text="📅 <b>Выберите день:</b>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )


# Переключение недель

@router.callback_query(
    F.data.startswith("schedule_select_week:")
)
async def schedule_week_handler(
        callback: CallbackQuery,
        state: FSMContext,
):
    await callback.answer()

    data = await state.get_data()
    schedule = data.get("schedule")

    if not schedule:
        log(
            "main_menu",
            "Нет schedule в FSM при переключении недели",
            callback.from_user.id,
        )
        await callback.message.edit_text(
            "Не удалось получить расписание. Откройте выбор даты заново."
        )
        return

    week_index = int(
        callback.data.split(":", 1)[1]
    )
    log(
        "main_menu",
        f"Переключение на неделю index={week_index}",
        callback.from_user.id,
    )

    # Защита от выхода за пределы
    if week_index < 0 or week_index >= len(schedule):
        return

    await state.update_data(
        week_index=week_index
    )

    keyboard = build_schedule_keyboard(
        schedule,
        week_index,
    )

    await callback.message.edit_reply_markup(
        reply_markup=keyboard
    )


# Кнопка номера текущей недели

@router.callback_query(
    F.data.startswith("schedule_week_current:")
)
async def schedule_week_current_handler(
        callback: CallbackQuery,
):
    """
    Кнопка «Неделя N» ничего не делает —
    она просто показывает текущую неделю.
    """
    await callback.answer()


# Выбор конкретного дня

@router.callback_query(
    F.data.startswith("schedule_day:")
)
async def schedule_day_handler(
        callback: CallbackQuery,
        state: FSMContext,
):
    await callback.answer()

    data = await state.get_data()
    schedule = data.get("schedule")

    if not schedule:
        log(
            "main_menu",
            "Нет schedule в FSM при выборе дня",
            callback.from_user.id,
        )
        await callback.message.edit_text(
            "Не удалось получить расписание. Откройте выбор даты заново."
        )
        return

    # schedule_day:week_index:day_index
    _, week_index, day_index = callback.data.split(":")

    week_index = int(week_index)
    day_index = int(day_index)
    log(
        "main_menu",
        f"Выбран день week={week_index}, day={day_index}",
        callback.from_user.id,
    )

    # Защита от некорректных индексов
    if week_index < 0 or week_index >= len(schedule):
        return

    week = schedule[week_index]

    if day_index < 0 or day_index >= len(week["days"]):
        return

    day_schedule = week["days"][day_index]

    await state.set_state(
        ScheduleSelection.selecting_day
    )

    await send_schedule(
        callback.message,
        day_schedule,
    )


def get_week_index_for_date(
        schedule: list[dict],
        target_date: date,
) -> int | None:

    target_date_string = target_date.strftime("%d.%m.%Y")

    for week_index, week in enumerate(schedule):

        for day in week.get("days", []):

            if day.get("date") == target_date_string:
                return week_index

    for week_index, week in enumerate(schedule):

        date_range = week.get("date_range")

        if not date_range or len(date_range) < 2:
            continue

        start_date = parse_schedule_date(
            date_range[0]
        )

        end_date = parse_schedule_date(
            date_range[1]
        )

        if start_date is None or end_date is None:
            continue

        if start_date <= target_date <= end_date:
            return week_index

    return None


def parse_schedule_date(value: str) -> date | None:
    try:
        return datetime.strptime(
            value,
            "%d.%m.%Y",
        ).date()
    except ValueError:
        return None


@router.callback_query(
    MainMenu.main_menu,
    F.data.in_({"schedule_week:this", "schedule_week:next"}),
)
async def schedule_week_image_handler(
        callback: CallbackQuery,
        state: FSMContext,
):
    await callback.answer()

    action = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    log("main_menu", f"Запрос картинки недели: {action}", user_id)

    try:
        schedule = await get_schedule(user_id)
    except Exception as error:
        log(
            "main_menu",
            f"Ошибка получения расписания (week:{action}): {error}",
            user_id,
        )
        await callback.message.answer(
            format_schedule_error(error)
        )
        return

    if not schedule:
        log("main_menu", "Расписание пустое при запросе недели", user_id)
        await callback.message.answer(
            "❌ Расписание отсутствует.\n\n"
            "💡 Возможно, оно ещё не опубликовано "
            "на сайте УлГТУ. Попробуйте позже."
        )
        return

    # Находим текущую неделю
    current_week_index = get_week_index_for_date(
        schedule,
        date.today(),
    )

    if current_week_index is None:
        await callback.message.answer(
            "Не удалось определить текущую неделю "
            "в расписании."
        )
        return

    # Определяем нужную неделю
    if action == "this":
        week_index = current_week_index

    else:
        week_index = current_week_index + 1

    # Проверяем, существует ли запрошенная неделя
    if week_index >= len(schedule):

        if action == "next":
            await callback.message.answer(
                "Следующей недели в расписании нет."
            )

        return

    week = schedule[week_index]
    date_range = week.get("date_range") or ()
    start_date = date_range[0] if len(date_range) > 0 else ""
    end_date = date_range[1] if len(date_range) > 1 else ""

    # Получаем подгруппу пользователя
    user = await get_user(
        callback.from_user.id
    )

    user_subgroup = None

    if user is not None:
        user_subgroup = user["subgroup"]

    image = generate_week_schedule_image(
        week,
        user_subgroup=user["subgroup"],
        group_name=user["group_name"],
    )

    photo = BufferedInputFile(
        image.getvalue(),
        filename=f"schedule_week_{week['week']}.png",
    )

    caption = (
        f"📅 <b>Расписание на неделю {week['week']}</b>\n"
        f"{start_date} — {end_date}"
    )

    log(
        "main_menu",
        f"Отправка картинки недели {week['week']}",
        user_id,
    )
    await callback.message.answer_photo(
        photo=photo,
        caption=caption,
        parse_mode="HTML",
        reply_markup=await build_delete_button(
            callback.message
        ),
    )


async def build_notification_settings_button(user) -> InlineKeyboardMarkup:
    buttons = []
    if user['notification_time'] is not None and user['notification_time'] != "":
        enabled = user['notification_enabled']
        if enabled:
            buttons.append([
                InlineKeyboardButton(
                    text="Включено",
                    callback_data="notification_settings:toggle",
                    style="primary"
                )
            ])
        else:
            buttons.append([
                InlineKeyboardButton(
                    text="Выключено",
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
    log("main_menu", f"Настройки оповещений: {action}", telegram_id)

    if action == "toggle":
        enabled = not bool(user['notification_enabled'])
        log(
            "main_menu",
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
    if user is None:
        telegram_id = message.chat.id
        user = await get_user(telegram_id)

    await state.set_state(NotificationSettings.notification_setting)

    if user['notification_time'] is None or user['notification_time'] == "":
        message_text = "Настройте время"
    else:
        message_text = ("Время оповещения:\n"
                        f"🕒{user['notification_time']}")
    await safe_edit_text(
        message,
        message_text,
        reply_markup=await build_notification_settings_button(user)
    )


def is_valid_time(value: str) -> bool:
    try:
        datetime.strptime(value, "%H:%M")
        return True
    except ValueError:
        return False

def normalize_time(value: str) -> str:
    value = value.strip()

    parsed = datetime.strptime(value, "%H:%M")

    return parsed.strftime("%H:%M")

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

    log("main_menu", f"Установлено время оповещения: {time}", message.chat.id)
    await update_user(
        message.chat.id,
        notification_time=normalize_time(time)
    )

    data = await state.get_data()

    await message.delete()
    await data.get("previous_message").delete()
    callback_message = data.get("callback_message")

    await render_notification_settings_menu(
        callback_message,
        state
    )
