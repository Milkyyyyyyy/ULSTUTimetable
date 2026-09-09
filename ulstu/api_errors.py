"""
Исключения для работы с JSON API расписания УлГТУ (time.ulstu.ru).
"""


class ULSTUAPIError(Exception):
	"""Базовое исключение API расписания."""


class ULSTUAuthenticationError(ULSTUAPIError):
	"""Сессия истекла, требуется повторная авторизация."""


class ULSTUResponseError(ULSTUAPIError):
	"""API вернул неожиданный формат ответа."""