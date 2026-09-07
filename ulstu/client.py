"""
Клиент для работы с расписанием УлГТУ: авторизация в кабинете,
сохранение сессии в виде cookies и загрузка HTML страниц расписания.
"""

import json
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from console_log import log
from database import get_user, update_user
from encryption.encryption import decrypt_data, encrypt_data
from validator.group import normalize_group
from ulstu.request_logger import log_request

LOGIN_URL = "https://lk.ulstu.ru/timetable/"
# Общий таймаут для всех запросов к сайту УлГТУ
REQUEST_TIMEOUT = aiohttp.ClientTimeout(
	total=30,
	connect=10,
	sock_read=20,
)

# Части расписания соответствуют меню на сайте lk.ulstu.ru
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


async def load_cookies(cookies_json: str | None) -> dict:
	"""Распаковывает JSON со cookies из БД в словарь."""
	if not cookies_json:
		return {}

	try:
		cookies = json.loads(cookies_json)

		if not isinstance(cookies, dict):
			return {}

		return cookies

	except json.JSONDecodeError:
		return {}


async def serialize_cookies(session: aiohttp.ClientSession) -> str:
	"""Сериализует cookies текущей сессии в JSON для хранения в БД."""
	cookies = {
		cookie.key: cookie.value
		for cookie in session.cookie_jar
	}

	return json.dumps(cookies, ensure_ascii=False)


async def _fetch_schedule_html(
	session: aiohttp.ClientSession,
	url: str,
) -> str:
	"""GET страницы; если сайт редиректит на auth/login — сессия истекла."""
	response = await session.get(url)
	response.raise_for_status()

	if "auth/login" in str(response.url):
		raise RuntimeError("Сессия УлГТУ больше недействительна")

	return await response.text()


async def _resolve_schedule_part(
	telegram_id: int,
	override_schedule_part: int | None = None,
) -> tuple[dict, int, str]:
	"""Возвращает (user, schedule_part, schedule_url) по ID телеграм-пользователя."""
	user = await get_user(telegram_id)

	if user is None:
		raise ValueError("Пользователь не найден")

	schedule_part = (
		override_schedule_part
		if override_schedule_part is not None
		else user["schedule_part"]
	)

	if schedule_part not in SCHEDULE_URLS:
		raise ValueError(f"Неизвестная часть расписания: {schedule_part}")

	return user, schedule_part, SCHEDULE_URLS[schedule_part]


async def login(
		session: aiohttp.ClientSession,
		login_data: str,
		password: str,
		telegram_id: int | None = None,
) -> bool:
	"""Авторизует сессию на сайте и возвращает признак успеха."""
	log("ulstu.client", f"Авторизация логином {login_data}", telegram_id)
	log_request(
		operation="login_page",
		telegram_id=telegram_id,
		url=LOGIN_URL,
	)

	response = await session.get(LOGIN_URL)
	response.raise_for_status()

	login_url = str(response.url)

	log_request(
		operation="login",
		telegram_id=telegram_id,
		url=login_url,
	)

	response = await session.post(
		login_url,
		data={
			"login": login_data,
			"password": password,
		},
		allow_redirects=True
	)

	response.raise_for_status()

	# Неудачный вход возвращает на страницу /auth/login
	success = "auth/login" not in str(response.url)

	if success:
		log("ulstu.client", "Авторизация успешна", telegram_id)
	else:
		log("ulstu.client", "Авторизация не удалась", telegram_id)

	return success


async def verify_ulstu_credentials(
		login_data: str,
		password: str,
		telegram_id: int,
) -> str:
	"""Проверяет логин/пароль: возвращает зашифрованные cookies или кидает исключение."""
	session = aiohttp.ClientSession(
		timeout=REQUEST_TIMEOUT,
	)

	try:
		success = await login(
			session,
			login_data,
			password,
			telegram_id=telegram_id,
		)

		if not success:
			raise RuntimeError("Авторизация на УлГТУ не удалась")

		cookies_json = await serialize_cookies(session)

		return await encrypt_data(cookies_json)

	finally:
		await session.close()


async def parse_groups(
		html: str,
		base_url: str
) -> list[dict]:
	"""Разбирает raspisan.html на список групп: [{group, url}, ...]."""
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


def find_group_url(
	groups: list[dict],
	group_name: str,
) -> str | None:
	"""Ищет группу в списке, сравнивая по нормализованному имени."""
	normalized_name = normalize_group(group_name)

	for group in groups:
		if normalize_group(group["group"]) == normalized_name:
			return group["url"]

	return None


async def get_schedule_groups(
	telegram_id: int,
	override_schedule_part: int | None = None,
) -> list[dict]:
	"""Возвращает список групп заданной части расписания."""
	_, schedule_part, schedule_url = await _resolve_schedule_part(
		telegram_id,
		override_schedule_part,
	)

	log(
		"ulstu.client",
		f"Запрос списка групп, часть={schedule_part}",
		telegram_id,
	)

	session = await get_authenticated_session(telegram_id)

	try:
		schedule_html = await _fetch_schedule_html(session, schedule_url)

		groups = await parse_groups(schedule_html, schedule_url)

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
	groups: list[dict] | None = None,
) -> str:
	"""Возвращает HTML страницы расписания конкретной группы.

	Если groups переданы (из кеша) — группа ищется в них, иначе
	сначала загружается raspisan.html для определяющей части.
	"""
	user, schedule_part, schedule_url = await _resolve_schedule_part(telegram_id)
	group_name = normalize_group(user["group_name"])

	log(
		"ulstu.client",
		f"Запрос HTML расписания группы {user['group_name']}",
		telegram_id,
	)

	group_url = find_group_url(groups, group_name) if groups is not None else None

	if group_url is not None:
		log(
			"ulstu.client",
			f"Группа найдена в переданном списке: {user['group_name']}",
			telegram_id,
		)

	session = await get_authenticated_session(telegram_id)

	try:
		if group_url is None:
			log(
				"ulstu.client",
				"Ссылка на группу не найдена в кеше. "
				"Получаем список групп с raspisan.html.",
				telegram_id,
			)

			schedule_html = await _fetch_schedule_html(session, schedule_url)

			parsed_groups = await parse_groups(schedule_html, schedule_url)
			group_url = find_group_url(parsed_groups, group_name)

		if group_url is None:
			raise ValueError(f"Группа {user['group_name']} не найдена в расписании")

		log_request(
			operation="group_schedule",
			telegram_id=telegram_id,
			schedule_part=schedule_part,
			url=group_url,
		)

		html = await _fetch_schedule_html(session, group_url)

		log(
			"ulstu.client",
			f"HTML расписания получен ({len(html)} символов)",
			telegram_id,
		)

		return html

	finally:
		await session.close()


async def get_authenticated_session(
	telegram_id: int,
) -> aiohttp.ClientSession:
	"""Возвращает сессию с cookies; при необходимости переавторизуется."""
	user = await get_user(telegram_id)

	if user is None:
		raise ValueError("Пользователь не найден")

	login_data = user["ulstu_login"]

	password = await decrypt_data(
		user["ulstu_password_encrypted"]
	)

	saved_cookies = {}

	if user["session_cookies"]:
		saved_cookies = await load_cookies(
			await decrypt_data(user["session_cookies"])
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

		# Проверяем сохранённую сессию без лишнего запроса
		# к raspisan.html: запрашиваем URL, доступный только
		# авторизованному пользователю, и смотрим на редирект.
		response = await session.get(LOGIN_URL)

		if "auth/login" not in str(response.url):
			log(
				"ulstu.client",
				"Сохранённая сессия действительна",
				telegram_id,
			)

			return session

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
			raise RuntimeError("Авторизация на УлГТУ не удалась")

		cookies_json = await serialize_cookies(session)
		encrypted_cookies = await encrypt_data(cookies_json)

		await update_user(
			telegram_id,
			session_cookies=encrypted_cookies,
		)

		log(
			"ulstu.client",
			"Новая сессия сохранена",
			telegram_id,
		)

		return session

	except Exception:
		await session.close()
		raise