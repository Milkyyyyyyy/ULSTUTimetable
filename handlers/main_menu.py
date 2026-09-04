from aiogram import Router, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup

from database import get_user
from states.states import MainMenu, Settings, ScheduleSelection
from datetime import date, timedelta

from ulstu.schedule import get_schedule_for_date, get_schedule
from utils import safe_edit_text, delete_button_factory

router = Router()


# ---------------------------------------------------------------------------
# Главное меню
# ---------------------------------------------------------------------------

main_menu_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
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
        ],
        [
            InlineKeyboardButton(
                text="📅 Расписание на дату",
                callback_data="schedule:select",
                style="success",
            ),
        ],
        [
            InlineKeyboardButton(
                text="⚙ Настройки",
                callback_data="open_settings",
                style="primary",
            )
        ],
    ]
)


async def show_main_menu(
    message: Message,
    state: FSMContext,
    edit_previous_message: bool = False,
):
    await state.clear()
    await state.set_state(MainMenu.main_menu)

    message_text = "С возвращением!\n"

    if edit_previous_message:
        await safe_edit_text(
            message,
            message_text,
            main_menu_keyboard,
        )
    else:
        await message.answer(
            message_text,
            reply_markup=main_menu_keyboard,
        )

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await show_main_menu(callback.message, state, edit_previous_message=True)

# ---------------------------------------------------------------------------
# Клавиатура выбора недели и дня
# ---------------------------------------------------------------------------

def build_schedule_keyboard(
    schedule: list[dict],
    week_index: int,
) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора дня.
    """

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

    # --------------------------------------------------
    # Кнопки дней
    # --------------------------------------------------

    for row_index in range(3):
	    left_index = row_index
	    right_index = row_index + 3

	    builder.row(
		    InlineKeyboardButton(
			    text=days[left_index]["day"],
			    callback_data=f"schedule_day:{week_index}:{left_index}",
		    ),
		    InlineKeyboardButton(
			    text=days[right_index]["day"],
			    callback_data=f"schedule_day:{week_index}:{right_index}",
		    ),
	    )

    # Воскресенье отдельно
    if len(days) > 6:
	    day = days[6]

	    builder.row(
		    InlineKeyboardButton(
			    text=day["day"],
			    callback_data=f"schedule_day:{week_index}:6",
		    )
	    )

    # --------------------------------------------------
    # Навигация по неделям
    # --------------------------------------------------

    navigation_buttons = []

    if week_index > 0:
        navigation_buttons.append(
            InlineKeyboardButton(
                text="←",
                callback_data=f"schedule_week:{week_index - 1}",
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
                callback_data=f"schedule_week:{week_index + 1}",
            )
        )

    builder.row(*navigation_buttons)

    # --------------------------------------------------
    # Назад
    # --------------------------------------------------

    builder.row(
        InlineKeyboardButton(
            text="◀ Назад",
            callback_data="back_to_menu",
            style="primary",
        )
    )

    return builder.as_markup()


# ---------------------------------------------------------------------------
# Открытие расписания / Сегодня / Завтра
# ---------------------------------------------------------------------------

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

    # --------------------------------------------------
    # Получаем расписание только здесь
    # --------------------------------------------------

    schedule = await get_schedule(callback.from_user.id)

    # --------------------------------------------------
    # Сегодня
    # --------------------------------------------------

    if action == "today":
        schedule_date = get_schedule_for_date(
            schedule,
            date.today(),
        )

        if schedule_date is not None:
            await send_schedule(
                callback.message,
                state,
                schedule_date,
            )

        return

    # --------------------------------------------------
    # Завтра
    # --------------------------------------------------

    if action == "tomorrow":
        tomorrow = date.today() + timedelta(days=1)

        schedule_date = get_schedule_for_date(
            schedule,
            tomorrow,
        )

        if schedule_date is not None:
            await send_schedule(
                callback.message,
                state,
                schedule_date,
            )

        return

    # --------------------------------------------------
    # Выбор дня
    # --------------------------------------------------

    if action == "select":

        if not schedule:
            await callback.message.edit_text(
                "Расписание отсутствует."
            )
            return

        # Сохраняем весь schedule в FSM.
        # Благодаря этому при переключении недель
        # заново получать расписание не понадобится.
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

        await callback.message.edit_text(
            text="📅 <b>Выберите день:</b>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )


# ---------------------------------------------------------------------------
# Переключение недель
# ---------------------------------------------------------------------------

@router.callback_query(
    F.data.startswith("schedule_week:")
)
async def schedule_week_handler(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.answer()

    # Получаем сохранённый schedule
    data = await state.get_data()
    schedule = data.get("schedule")

    if not schedule:
        await callback.message.edit_text(
            "Не удалось получить расписание. Откройте выбор даты заново."
        )
        return

    # Получаем индекс недели
    week_index = int(
        callback.data.split(":", 1)[1]
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


# ---------------------------------------------------------------------------
# Нажатие на номер текущей недели
# ---------------------------------------------------------------------------

@router.callback_query(
    F.data.startswith("schedule_week_current:")
)
async def schedule_week_current_handler(
    callback: CallbackQuery,
):
    """
    Центральная кнопка 'Неделя N'.

    Ничего не делает — она просто показывает,
    на какой неделе сейчас находится пользователь.
    """

    await callback.answer()


# ---------------------------------------------------------------------------
# Выбор конкретного дня
# ---------------------------------------------------------------------------

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
        await callback.message.edit_text(
            "Не удалось получить расписание. Откройте выбор даты заново."
        )
        return

    # schedule_day:week_index:day_index
    _, week_index, day_index = callback.data.split(":")

    week_index = int(week_index)
    day_index = int(day_index)

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
        state,
        day_schedule,
    )


# ---------------------------------------------------------------------------
# Отправка расписания
# ---------------------------------------------------------------------------

async def send_schedule(
    message: Message,
    state: FSMContext,
    schedule: dict,
):
    message_text = await format_day_schedule(
        schedule,
        message.chat.id,
    )

    await message.answer(
        text=message_text,
        parse_mode="HTML",
        reply_markup=await delete_button_factory(message),
    )


# ---------------------------------------------------------------------------
# Форматирование расписания
# ---------------------------------------------------------------------------

async def format_day_schedule(
    day_schedule: dict,
    telegram_id: int | None = None,
) -> str:
    """
    Формирует готовое сообщение с расписанием на день.

    Если telegram_id передан:
        применяется фильтр по подгруппе пользователя.

    Если telegram_id не передан:
        показываются все занятия.
    """

    # --------------------------------------------------
    # Получаем подгруппу пользователя
    # --------------------------------------------------

    user_subgroup = None

    if telegram_id is not None:
        user = await get_user(telegram_id)

        if user is not None:
            user_subgroup = user["subgroup"]

    # --------------------------------------------------
    # Заголовок
    # --------------------------------------------------

    schedule_date = day_schedule["date"]

    message = (
        f"📅 <b>Расписание на {schedule_date}</b>\n\n"
    )

    # --------------------------------------------------
    # Обрабатываем пары
    # --------------------------------------------------

    visible_lessons_count = 0

    for lesson in day_schedule["lessons"]:

        visible_lessons = []

        for item in lesson["lessons"]:

            # Общее занятие
            if item["subgroup"] is None:
                visible_lessons.append(item)

            # Занятие нашей подгруппы
            elif (
                user_subgroup is None
                or item["subgroup"] == user_subgroup
            ):
                visible_lessons.append(item)

        # Если после фильтрации ничего не осталось —
        # не показываем эту пару.
        if not visible_lessons:
            continue

        visible_lessons_count += 1

        lesson_text = (
            f"<blockquote>"
            f"<b>{lesson['lesson_number']}-я пара "
            f"({lesson['time']})</b>\n\n"
        )

        for item in visible_lessons:
            lesson_text += (
                f"<b><u>{item['type']}</u>"
                f"{item['subject']}</b>\n"
            )

            if item["subgroup"] is not None:
                lesson_text += (
                    f"<b>Подгруппа:</b> "
                    f"{item['subgroup']}\n"
                )

            lesson_text += (
                f"\n{item['teacher']}\n"
                f"<b>Аудитория:</b> {item['room']}\n\n"
            )

        lesson_text += "</blockquote>\n"

        message += lesson_text

    # --------------------------------------------------
    # Если пар нет
    # --------------------------------------------------

    if visible_lessons_count == 0:
        message += "<i>Пар нет.</i>"

    return message