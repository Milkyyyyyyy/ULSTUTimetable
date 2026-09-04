import json
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from console_log import log
from database import get_user, update_user
from encryption.encryption import decrypt_password
from validator.group import normalize_group

LOGIN_URL = "https://lk.ulstu.ru/timetable/"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(
    total=30,
    connect=10,
    sock_read=20,
)

SCHEDULE_URLS = {
    1: (
        "https://lk.ulstu.ru/timetable/shared/schedule/"
        "Часть 1 - МФ, РТФ, ЭФ (очная, очно-заочная формы обучения), "
        "ИФМИ, группы искусственного интеллекта (магистр)/raspisan.html"
    ),
    2: (
        "https://lk.ulstu.ru/timetable/shared/schedule/"
        "Часть 2 – ФИСТ, ГФ/raspisan.html"
    ),
    3: (
        "https://lk.ulstu.ru/timetable/shared/schedule/"
        "Часть 3 – ИАТУ, ИЭФ (очная, очно-заочная, заочная формы обучения), "
        "ЗВФ ИННО (очно-заочная, заочная формы обучения)/raspisan.html"
    ),
    4: (
        "https://lk.ulstu.ru/timetable/shared/schedule/"
        "Часть 4 – КЭИ/raspisan.html"
    ),
    5: (
        "https://lk.ulstu.ru/timetable/shared/schedule/"
        "Часть 5 – СФ/raspisan.html"
    ),
}


def load_cookies(cookies_json: str | None) -> dict:
    if not cookies_json:
        return {}

    try:
        cookies = json.loads(cookies_json)

        if not isinstance(cookies, dict):
            return {}

        return cookies

    except json.JSONDecodeError:
        return {}


def serialize_cookies(session: aiohttp.ClientSession) -> str:
    cookies = {
        cookie.key: cookie.value
        for cookie in session.cookie_jar
    }

    return json.dumps(cookies, ensure_ascii=False)


async def login(
        session: aiohttp.ClientSession,
        login_data: str,
        password: str,
        telegram_id: int | None = None,
) -> bool:
    log("ulstu.client", f"Авторизация логином {login_data}", telegram_id)

    response = await session.get(LOGIN_URL)
    response.raise_for_status()

    login_url = str(response.url)

    response = await session.post(
        login_url,
        data={
            "login": login_data,
            "password": password,
        },
        allow_redirects=True
    )

    response.raise_for_status()

    success = "auth/login" not in str(response.url)

    if success:
        log("ulstu.client", "Авторизация успешна", telegram_id)
    else:
        log("ulstu.client", "Авторизация не удалась", telegram_id)

    return success


async def get_schedule_page(
        session: aiohttp.ClientSession,
        schedule_url: str
) -> tuple[bool, str]:
    response = await session.get(schedule_url)
    response.raise_for_status()

    current_url = str(response.url)

    if "auth/login" in current_url:
        return False, ""

    return True, await response.text()


def parse_groups(
        html: str,
        base_url: str
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    groups = []

    for link in soup.select("table a[href]"):
        group_name = link.get_text(strip=True)
        href = link.get("href")

        if not group_name or not href:
            continue

        groups.append({
            "group": group_name,
            "url": urljoin(base_url, href)
        })

    return groups


async def get_schedule_groups(
    telegram_id: int,
    override_schedule_part: int | None = None,
) -> list[dict]:

    user = await get_user(telegram_id)

    if user is None:
        raise ValueError("Пользователь не найден")

    schedule_part = (
        override_schedule_part
        if override_schedule_part is not None
        else user["schedule_part"]
    )

    if schedule_part not in SCHEDULE_URLS:
        raise ValueError(
            f"Неизвестная часть расписания: {schedule_part}"
        )

    schedule_url = SCHEDULE_URLS[schedule_part]

    log(
        "ulstu.client",
        f"Запрос списка групп, часть={schedule_part}",
        telegram_id,
    )

    session, schedule_html = (
        await get_authenticated_session(
            telegram_id,
            schedule_url,
        )
    )

    try:
        groups = parse_groups(
            schedule_html,
            schedule_url,
        )

        log(
            "ulstu.client",
            f"Получено групп: {len(groups)}",
            telegram_id,
        )

        return groups

    finally:
        await session.close()


async def get_group_schedule(
    telegram_id: int,
) -> str:

    user = await get_user(telegram_id)

    if user is None:
        raise ValueError("Пользователь не найден")

    group_name = normalize_group(
        user["group_name"]
    )

    schedule_part = user["schedule_part"]

    schedule_url = SCHEDULE_URLS[schedule_part]

    log(
        "ulstu.client",
        f"Запрос HTML расписания группы "
        f"{user['group_name']}",
        telegram_id,
    )

    session, schedule_html  = await get_authenticated_session(
        telegram_id,
        schedule_url,
    )

    try:
        groups = parse_groups(
            schedule_html ,
            schedule_url,
        )

        group_url = None

        for group in groups:
            if normalize_group(group["group"]) == group_name:
                group_url = group["url"]
                break

        if group_url is None:
            raise ValueError(
                f"Группа {user['group_name']} "
                "не найдена в расписании"
            )

        response = await session.get(group_url)
        response.raise_for_status()

        if "auth/login" in str(response.url):
            raise RuntimeError(
                "Сессия УлГТУ больше недействительна"
            )

        html = await response.text()

        log(
            "ulstu.client",
            f"HTML расписания получен "
            f"({len(html)} символов)",
            telegram_id,
        )

        return html

    finally:
        await session.close()

async def get_authenticated_session(
    telegram_id: int,
    schedule_url: str,
):
    user = await get_user(telegram_id)

    if user is None:
        raise ValueError("Пользователь не найден")

    login_data = user["ulstu_login"]

    password = decrypt_password(
        user["ulstu_password_encrypted"]
    )

    saved_cookies = load_cookies(
        user["session_cookies"]
    )

    session = aiohttp.ClientSession(
        cookies=saved_cookies,
        timeout=REQUEST_TIMEOUT,
    )

    try:
        log(
            "ulstu.client",
            "Пробуем использовать сохранённую сессию",
            telegram_id,
        )
        schedule_is_available, schedule_html = (
            await get_schedule_page(
                session,
                schedule_url,
            )
        )

        if schedule_is_available:
            return session, schedule_html

        log(
            "ulstu.client",
            "Сессия истекла, повторная авторизация",
            telegram_id,
        )

        session.cookie_jar.clear()

        auth_success = await login(
            session,
            login_data,
            password,
            telegram_id=telegram_id,
        )

        if not auth_success:
            raise RuntimeError(
                "Авторизация на УлГТУ не удалась"
            )

        cookies_json = serialize_cookies(session)

        await update_user(
            telegram_id,
            session_cookies=cookies_json,
        )

        schedule_is_available, schedule_html = (
            await get_schedule_page(
                session,
                schedule_url,
            )
        )

        if not schedule_is_available:
            raise RuntimeError(
                "Не удалось получить расписание "
                "после авторизации"
            )

        return session, schedule_html

    except Exception:
        await session.close()
        raise