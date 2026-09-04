from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import get_user
from states.states import MainMenu, Settings
from datetime import date, timedelta

from ulstu.schedule import get_schedule_for_date, get_schedule
from utils import safe_edit_text, delete_button_factory

router = Router()

# ---------------------------------------------------------------------------

main_menu_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🗓Сегодня",
                callback_data="schedule:today",
                style="success"
            ),
            InlineKeyboardButton(
                text="🗓Завтра",
                callback_data="schedule:tomorrow",
                style="success"
            ),
        ],
        [
            InlineKeyboardButton(
                text="📅Расписание на дату",
                callback_data="schedule:select",
                style="success"
            ),
        ],
        [
            InlineKeyboardButton(
                text="⚙ Настройки",
                callback_data="open_settings",
                style="primary"
            )
        ]
    ]
)


async def show_main_menu(message: Message, state: FSMContext, edit_previous_message: bool = False):
    await state.clear()
    await state.set_state(MainMenu.main_menu)

    message_text = "С возвращением!\n"
    if edit_previous_message:
        await safe_edit_text(message, message_text, main_menu_keyboard)
    else:
        await message.answer(message_text, reply_markup=main_menu_keyboard)

@router.callback_query(
    MainMenu.main_menu,
    F.data.startswith("schedule:"),
)
async def schedule_button_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    day = callback.data.split(":")[1]
    schedule = await get_schedule(callback.from_user.id)
    schedule_date = None

    match day:
        case "today":
            schedule_date = get_schedule_for_date(schedule, date.today())
        case "tomorrow":
            schedule_date = get_schedule_for_date(schedule, (date.today() + timedelta(days=1)))
        case "select":
            # Вот тут должен запускаться выбор даты. Если надо, наверное надо создать ещё новый state
            pass

    if schedule_date is not None:
        await send_schedule(callback.message, state, schedule_date)


async def send_schedule(message: Message, state: FSMContext, schedule: dict):
    message_text = await format_day_schedule(
        schedule,
        message.chat.id
    )
    await message.answer(
        text=message_text,
        parse_mode="HTML",
        reply_markup= await delete_button_factory(message)
    )

async def format_day_schedule(
    day_schedule: dict,
    telegram_id: int | None = None
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
        print(user['subgroup'])
        if user is not None:
            user_subgroup = user["subgroup"]



    # --------------------------------------------------
    # Заголовок
    # --------------------------------------------------

    date = day_schedule["date"]

    message = (
        f"📅 <b>Расписание на {date}</b>\n\n"
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

        # Если после фильтрации в этой паре ничего
        # не осталось — не показываем саму пару.
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
                    f"<b>Подгруппа:</b> {item['subgroup']}\n"
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
