"""
Исключения для работы с сайтом и API расписания УлГТУ
(lk.ulstu.ru, time.ulstu.ru).
"""


class ULSTUAPIError(Exception):
	"""Базовое исключение API расписания."""


class ULSTUAuthenticationError(ULSTUAPIError):
	"""Сессия истекла, требуется повторная авторизация."""


class ULSTUResponseError(ULSTUAPIError):
	"""API вернул неожиданный формат ответа."""


class ULSTUNotFoundError(ULSTUAPIError):
	"""Запрошенная страница расписания не найдена (HTTP 404).

	Обычно означает, что УлГТУ изменил ссылки на части расписания.
	"""