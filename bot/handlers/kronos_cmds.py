"""
Kronos commands: /predict, /accuracy
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.auth import is_allowed_user
from bot.config import KRONOS_ENABLED

router = Router()


@router.message(Command("predict"))
async def cmd_predict(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    if not KRONOS_ENABLED:
        await message.reply("Kronos is disabled.")
        return

    from bot.kronos import is_ready, predict, format_prediction

    if not is_ready():
        await message.reply("Kronos model still loading, riprova tra qualche secondo...")
        return

    try:
        result = await predict()
        await message.reply(format_prediction(result))
    except Exception as e:
        await message.reply(f"Errore Kronos: {e}")


@router.message(Command("accuracy"))
async def cmd_accuracy(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    if not KRONOS_ENABLED:
        await message.reply("Kronos is disabled.")
        return

    from bot.kronos import get_accuracy_stats, format_accuracy

    stats = get_accuracy_stats()
    if stats["total"] == 0:
        await message.reply("Nessuna previsione ancora. Usa /predict per iniziare.")
        return

    await message.reply(format_accuracy(stats))
