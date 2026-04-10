"""
Voice commands: /voice, /text
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.auth import is_allowed_user
from bot.text_cleaner import split_message
from bot.handlers._state import get_thread_id, voice_requested, last_response

router = Router()


@router.message(Command("voice"))
async def cmd_voice(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    key = (message.chat.id, get_thread_id(message))
    voice_requested.add(key)
    await message.reply("Il prossimo messaggio includerà una risposta vocale.")


@router.message(Command("text"))
async def cmd_text(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    key = (message.chat.id, get_thread_id(message))
    last = last_response.get(key)
    if last:
        for chunk in split_message(last):
            await message.reply(chunk)
    else:
        await message.reply("Nessuna risposta vocale recente da mostrare.")
