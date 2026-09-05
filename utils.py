import asyncio
import logging

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from console_log import log

router = Router()
logger = logging.getLogger(__name__)


async def delete_after(
		messages: Message | list[Message],
		delay: float
):
	async def delete():
		await asyncio.sleep(delay)

		if isinstance(messages, Message):
			messages_to_delete = [messages]
		else:
			messages_to_delete = messages

		for message in messages_to_delete:
			try:
				await message.delete()
			except TelegramBadRequest:
				pass
			except Exception:
				logger.exception(
					"Failed to delete message %s",
					message.message_id,
				)

	asyncio.create_task(delete())


async def safe_edit_text(message: Message, text: str, reply_markup: InlineKeyboardMarkup = None) -> None:
	try:
		await message.edit_text(text, reply_markup=reply_markup)
	except TelegramBadRequest as e:
		if "message is not modified" not in str(e):
			raise


async def safe_bot_edit_text(
		bot, chat_id: int, message_id: int, text: str,
		reply_markup: InlineKeyboardMarkup = None) -> None:
	try:
		await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup)
	except TelegramBadRequest as e:
		if "message is not modified" not in str(e):
			raise


async def build_delete_button(message: Message):
	return InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(
					text="Удалить",
					callback_data=f"botUtilsDelete:{message.message_id}"
				)
			]
		]
	)


@router.callback_query(
	F.data.startswith("botUtilsDelete:")
)
async def delete_on_button(callback: CallbackQuery):
	await callback.answer()
	log("utils", "Удаление сообщения по кнопке", callback.from_user.id)
	message = callback.message
	await message.delete()
