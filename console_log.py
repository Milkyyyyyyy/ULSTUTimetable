from datetime import datetime


def log(
		place: str,
		message: str,
		user_id: int | None = None,
) -> None:
	"""
	Простой консольный лог:
	[время] [место] [кто] что произошло
	"""

	time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	who = f"user={user_id}" if user_id is not None else "system"
	print(f"[{time}] [{place}] [{who}] {message}")
