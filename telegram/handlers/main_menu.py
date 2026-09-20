"""
Главное меню: приветствие, кнопки настроек/расписания, выбор дня,
недели и отправка изображения расписания.
"""

import random
from datetime import UTC, date, datetime, timedelta
from time import timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.types.input_media_photo import InputMediaPhoto
from aiogram.types.input_media_union import InputMediaUnion
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from console_log import log
from database import get_user

from ..states.states import MainMenu, ScheduleSelection
from ..utils import build_delete_button, delete_after, send_schedule
from ulstu.schedule import (
    format_schedule_error,
    get_schedule,
    get_schedule_for_date,
)
from ulstu.schedule_image import generate_week_schedule_image

router = Router()

# Тексты reply-кнопок главного меню
MENU_TODAY = "🗓 Сегодня"
MENU_TOMORROW = "🗓 Завтра"
MENU_THIS_WEEK = "На неделю"
MENU_NEXT_WEEK = "На следующую неделю"
MENU_BY_DATE = "📅 Расписание на дату"
MENU_NOTIFY = "🔔 Автооповещение"
MENU_SETTINGS = "⚙ Настройки"

WELCOME_MESSAGES = {
    "night": [
        "Доброй ночи.",
        "Расписание подождёт до утра.",
        "Спишь? А расписание не спит.",
        "Ночью лучше спать, но давай посмотрим.",
        "Надеюсь, ты просто проверяешь пары, а не садишься за курсач.",
        "Кто-то доделывает лабы в последнюю ночь?"
    ],
    "early_morning": [
        "Доброе утро.",
        "Ещё темно, а мы уже смотрим расписание.",
        "Ранняя пташка? Доброе утро.",
        "Кто рано встает, тому первую пару не проспать.",
        "Герой ранних подъёмов. Доброе утро."
    ],
    "morning": [
        "Доброе утро.",
        "Новый день — новые пары.",
        "Доброе утро. Что у нас сегодня?",
        "Просыпаемся и смотрим расписание.",
        "С добрым утром. Надеюсь, первая пара не слишком душная."
    ],
    "day": [
        "Добрый день.",
        "Привет. Что там по расписанию?",
        "Добрый день. Чем могу помочь?",
        "Учёба в самом разгаре.",
        "Смотрим пары?"
    ],
    "evening": [
        "Добрый вечер.",
        "Пары кончились? Смотрим планы на завтра.",
        "День окончен. Что там дальше по расписанию?",
        "Вечер. Можно выдохнуть.",
        "Добрый вечер. Завтра к какой паре?"
    ],
}


def build_empty_day(target_date: date) -> dict:
    return {
        "day": target_date.strftime("%d.%m.%Y"),
        "date": target_date.strftime("%d.%m.%Y"),
        "lessons": [],
    }

async def get_welcome_message() -> str:
    hour = datetime.now().hour

    if 0 <= hour < 6:
        period = "night"
    elif 6 <= hour < 8:
        period = "early_morning"
    elif 8 <= hour < 12:
        period = "morning"
    elif 12 <= hour < 18:
        period = "day"
    else:
        period = "evening"

    return random.choice(WELCOME_MESSAGES[period])

async def build_main_menu_buttons() -> ReplyKeyboardMarkup:

    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=MENU_TODAY),
        KeyboardButton(text=MENU_TOMORROW),
    )
    builder.row(
        KeyboardButton(text=MENU_THIS_WEEK),
        KeyboardButton(text=MENU_NEXT_WEEK),
    )
    builder.row(
        KeyboardButton(text=MENU_BY_DATE),
    )
    builder.row(
        KeyboardButton(text=MENU_NOTIFY),
    )
    builder.row(
        KeyboardButton(text=MENU_SETTINGS),
    )

    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
        is_persistent=True,
    )


async def build_main_menu_text(telegram_id: int) -> str:
    user = await get_user(telegram_id)

    if user is None:
        raise ValueError("Пользователь не найден")

    message = (
        "<b>📚 Расписание УлГТУ</b>\n"
        f"<i>{await get_welcome_message()}</i>\n\n"
        f"Группа: {user['group_name']}"
    )

    if user["subgroup"] not in ("", None):
        message += f" • {user['subgroup']} подгруппа"

    return message


async def show_main_menu(
        message: Message,
        state: FSMContext,
):
    log("main_menu", "Открытие главного меню", message.chat.id)

    data = await state.get_data()
    old_menu_message_id = data.get("menu_message_id")
    old_menu_chat_id = data.get("menu_chat_id")

    await state.clear()
    await state.set_state(MainMenu.main_menu)

    if old_menu_message_id and old_menu_chat_id:
        try:
            await message.bot.delete_message(
                old_menu_chat_id,
                old_menu_message_id,
            )
        except TelegramBadRequest:
            pass

    menu_message = await message.answer(
        await build_main_menu_text(message.chat.id),
        parse_mode="HTML",
        reply_markup=await build_main_menu_buttons(),
    )

    await state.update_data(
        menu_message_id=menu_message.message_id,
        menu_chat_id=menu_message.chat.id,
    )


async def return_to_main_menu(
        message: Message,
        state: FSMContext,
):
    """Возвращает в главное меню: удаляет сообщение подэкрана.
    Текстовое меню из /start остаётся носителем reply-кнопок,
    поэтому пересылать его не нужно."""
    await state.clear()
    await state.set_state(MainMenu.main_menu)

    try:
        await message.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    log("main_menu", "Назад в главное меню", callback.from_user.id)
    await return_to_main_menu(callback.message, state)


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

@router.message(
    MainMenu.main_menu,
    F.text.in_({MENU_TODAY, MENU_TOMORROW}),
)
async def schedule_button_handler(
        message: Message,
        state: FSMContext,
):
    action = "today" if message.text == MENU_TODAY else "tomorrow"
    user_id = message.from_user.id

    # Сегодня/завтра: сразу показываем загрузку и заменяем её
    # расписанием либо сообщением об ошибке.
    loading_message = await message.answer(
        text="<i>Загружаю расписание...</i>",
        parse_mode="HTML"
    )

    schedule, error_text = await get_schedule_for_user(message, action)

    if error_text is not None:
        await loading_message.edit_text(error_text)
        await delete_after(loading_message, 8)
        return

    if action == "today":
        today = date.today()
        schedule_date = get_schedule_for_date(
            schedule,
            today,
        )
        log("main_menu", f"Отправка расписания на {today}", user_id)

        await send_schedule(
            message,
            schedule_date or build_empty_day(today),
            edit_message=loading_message,
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
            message,
            schedule_date or build_empty_day(tomorrow),
            edit_message=loading_message,
        )
        return


@router.message(
    MainMenu.main_menu,
    F.text == MENU_BY_DATE,
)
async def schedule_by_date_handler(
        message: Message,
        state: FSMContext,
):
    await open_day_selection(message, state)


async def open_day_selection(
        message: Message,
        state: FSMContext,
):
    """Загружает расписание и открывает клавиатуру выбора дня."""
    user_id = message.from_user.id

    schedule, error_text = await get_schedule_for_user(message, "select")

    if error_text is not None:
        error_message = await message.answer(error_text)
        await delete_after(error_message, 8)
        return

    if not schedule:
        log(
            "main_menu",
            "Расписание пустое при выборе даты",
            user_id,
            level="WARNING",
        )
        error_message = await message.answer(
            "❌ Расписание отсутствует.\n\n"
            "💡 Возможно, оно ещё не опубликовано "
            "на сайте УлГТУ. Попробуйте позже."
        )
        await delete_after(error_message, 8)
        return

    # Сохраняем schedule в FSM, чтобы при переключении недель
    # не запрашивать его заново
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
    await message.answer(
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
            level="WARNING",
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
            level="WARNING",
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

    loading_message = await callback.message.answer(
        text="<i>Загружаю расписание...</i>",
        parse_mode="HTML"
    )

    await send_schedule(
        callback.message,
        day_schedule,
        edit_message=loading_message,
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

    # Воскресенье (или выходной) не входит в дни расписания —
    # ищем неделю по понедельнику недели target_date.
    target_monday = target_date - timedelta(
        days=target_date.weekday()
    )

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

        if start_date <= target_monday <= end_date:
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


@router.message(
    MainMenu.main_menu,
    F.text.in_({MENU_THIS_WEEK, MENU_NEXT_WEEK}),
)
async def schedule_week_image_handler(
        message: Message,
        state: FSMContext,
):
    action = "this" if message.text == MENU_THIS_WEEK else "next"
    user_id = message.from_user.id
    log("main_menu", f"Запрос картинки недели: {action}", user_id)

    schedule_message = await message.answer(
        text="<i>Загружаю расписание...</i>",
        parse_mode="HTML"
    )

    schedule, error_text = await get_schedule_for_user(message, f"week:{action}")

    if error_text is not None:
        await schedule_message.edit_text(error_text)
        await delete_after(schedule_message, 8)
        return

    if not schedule:
        log("main_menu", "Расписание пустое при запросе недели", user_id, level="WARNING")
        await schedule_message.edit_text(
            "❌ Расписание отсутствует.\n\n"
            "💡 Возможно, оно ещё не опубликовано "
            "на сайте УлГТУ. Попробуйте позже."
        )
        await delete_after(schedule_message, 8)
        return

    # Находим текущую неделю
    current_week_index = get_week_index_for_date(
        schedule,
        date.today(),
    )

    if current_week_index is None:
        await schedule_message.edit_text(
            "Не удалось определить текущую неделю "
            "в расписании."
        )
        await delete_after(
            schedule_message,
            delay=8
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
            await schedule_message.edit_text(
                "Следующей недели в расписании нет.\n"
                "Попробуйте позже."
            )
            await delete_after(schedule_message, 8)

        return


    week = schedule[week_index]
    date_range = week.get("date_range") or ()
    start_date = date_range[0] if len(date_range) > 0 else ""
    end_date = date_range[1] if len(date_range) > 1 else ""

    # Получаем подгруппу пользователя
    user = await get_user(
        message.from_user.id
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
    # await waiting_message.delete()
    # await callback.message.answer_photo(
    #     photo=photo,
    #     caption=caption,
    #     parse_mode="HTML",
    #     reply_markup=build_delete_button(),
    # )
    await schedule_message.edit_media(
        media=InputMediaPhoto(
            media=photo,
            caption=caption,
            parse_mode="HTML"
        ),
        reply_markup=build_delete_button()
    )


async def get_schedule_for_user(
        message: Message,
        action: str,
) -> tuple[list[dict] | None, str | None]:
    """Загружает расписание; возвращает (расписание, текст_ошибки).

    При успехе — (schedule, None), при ошибке — (None, error_text),
    где error_text уже готов к показу пользователю.
    """
    user_id = message.from_user.id
    log("main_menu", f"Запрос расписания: {action}", user_id)

    try:
        schedule = await get_schedule(user_id)
    except Exception as error:
        log(
            "main_menu",
            f"Ошибка получения расписания ({action}): {error}",
            user_id,
            level="ERROR",
        )
        return None, format_schedule_error(error)

    return schedule, None
