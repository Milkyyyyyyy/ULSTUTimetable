"""
Фоновый воркер: ежедневно рассылает пользователям расписание на завтра
в указанное время (notification_time).
"""

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta

from aiogram import Bot

from console_log import log
from database import get_users_for_notification, update_user
from ulstu.schedule import (
    format_day_schedule,
    get_schedule,
    get_schedule_for_date,
)
from validator.group import normalize_group

from .utils import build_delete_button

# Жёсткий потолок: не больше N запросов в секунду
MAX_REQUESTS_PER_SECOND = 10

# Если получателей не больше этого числа — отправляем без пауз
MIN_USERS_WITHOUT_THROTTLE = 10

# Рассылка должна укладываться примерно в это число секунд
TARGET_DURATION_SECONDS = 30


class RateLimiter:
    """Ограничивает частоту запросов: не больше max_per_second в секунду."""

    def __init__(self, max_per_second: float):
        self._interval = 1.0 / max_per_second
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def __aenter__(self):
        while True:
            now = asyncio.get_running_loop().time()

            async with self._lock:
                if now >= self._next_at:
                    self._next_at = now + self._interval
                    return

                wait = self._next_at - now

            await asyncio.sleep(wait)

    async def __aexit__(self, *args):
        return False


def make_rate_limiter(user_count: int) -> RateLimiter:
    """Считает допустимую частоту запросов из числа получателей."""
    if user_count <= MIN_USERS_WITHOUT_THROTTLE:
        max_per_second = MAX_REQUESTS_PER_SECOND
    else:
        # Растягиваем рассылку на ~30 секунд, но не быстрее потолка
        max_per_second = min(
            user_count / TARGET_DURATION_SECONDS,
            MAX_REQUESTS_PER_SECOND,
        )

    log("notifications", f"Лимит рассылки: {max_per_second:.1f} запросов/сек")

    return RateLimiter(max_per_second)


def group_users_by_part_group(users) -> dict:
    """Группирует пользователей по (часть расписания, нормализованная группа).

    Это тот же ключ, что использует кэш расписания: один запрос на группу
    заполняет кэш, и он же обслуживает всех пользователей группы.
    """
    groups = defaultdict(list)

    for user in users:
        key = (
            user["schedule_part"],
            normalize_group(user["group_name"]),
        )
        groups[key].append(user)

    return dict(groups)


async def notification_worker(bot: Bot):
    """Бесконечный цикл: раз в минуту проверяет, комему отправить расписание."""
    log("notifications", "Воркер уведомлений стартовал")

    while True:
        now = datetime.now().astimezone()

        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")

        users = await get_users_for_notification(
            current_time,
            current_date,
        )

        if users:
            await send_batch(bot, users, current_date)

        delay = 60 - now.second - now.microsecond / 1_000_000

        await asyncio.sleep(delay)


async def send_batch(bot: Bot, users: list, current_date: str):
    """Сначала синхронно получает расписание по одному разу на каждую группу,
    затем параллельно рассылает его всем пользователям из кэша."""
    limiter = make_rate_limiter(len(users))

    tasks = []

    for group_users in group_users_by_part_group(users).values():
        # Один запрос на группу: аккаунт первого пользователя группы
        # обновляет общий кэш расписания для всех из этой группы
        representative = group_users[0]

        try:
            schedule = await get_schedule(representative["telegram_id"])
        except Exception as e:
            log(
                "notifications",
                f"Ошибка получения расписания для группы "
                f"{representative['group_name']}: "
                f"{type(e).__name__}: {e}",
                representative["telegram_id"],
            )
            continue

        if not schedule:
            for user in group_users:
                log(
                    "notifications",
                    "Расписание пустое — пропуск",
                    user["telegram_id"],
                )
            continue

        for user in group_users:
            tasks.append(
                send_tomorrow_schedule(
                    bot,
                    user,
                    current_date,
                    schedule,
                    limiter,
                )
            )

    if tasks:
        await asyncio.gather(*tasks)


async def send_tomorrow_schedule(
    bot: Bot,
    user: dict,
    current_date: str,
    schedule: list,
    limiter: RateLimiter,
):
    """Формирует расписание на завтра (из уже полученного кэша) и отправляет
    пользователю с кнопкой «Удалить»."""
    telegram_id = user["telegram_id"]

    try:
        log("notifications", "Отправка расписания на завтра", telegram_id)

        tomorrow = date.today() + timedelta(days=1)

        tomorrow_schedule = get_schedule_for_date(
            schedule,
            tomorrow,
        )

        # Создаём пустой день, если на завтра занятий нет
        if tomorrow_schedule is None:
            tomorrow_schedule = {
                "day": tomorrow.strftime("%d.%m.%Y"),
                "date": tomorrow.strftime("%d.%m.%Y"),
                "lessons": [],
            }

        message_text = await format_day_schedule(
            tomorrow_schedule,
            telegram_id,
        )

        # Единственный сетевой запрос «на пользователя» — отправка в Telegram,
        # его и ограничиваем по частоте (расписание берём из общего кэша).
        async with limiter:
            await bot.send_message(
                chat_id=telegram_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=build_delete_button(),
            )

        await update_user(
            telegram_id,
            notification_last_sent=current_date,
        )

        log(
            "notifications",
            f"Оповещение отправлено "
            f"(scheduled={user['notification_time']})",
            telegram_id,
        )

    except Exception as e:
        log(
            "notifications",
            f"Ошибка отправки: "
            f"{type(e).__name__}: {e}",
            telegram_id,
        )
