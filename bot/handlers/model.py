"""
Model commands: /model, /opus, /sonnet, /haiku, /effort, /turns, /plan
"""

import os

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.auth import is_allowed_user
from bot.config import (
    MODEL_OPUS, MODEL_SONNET, MODEL_HAIKU,
    DEFAULT_EFFORT, DEFAULT_MAX_TURNS,
    MIN_TURNS, MAX_TURNS_LIMIT,
    EFFORT_LEVELS, EFFORT_LABELS,
)
from bot.handlers._state import get_thread_id, plan_mode

router = Router()


@router.message(Command("model"))
async def cmd_model(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(
            "Uso: /model <nome>\n"
            f"Esempi: {MODEL_SONNET}, {MODEL_OPUS}, {MODEL_HAIKU}"
        )
        return
    os.environ["CLAUDE_MODEL"] = args[1]
    await message.reply(f"Modello cambiato a: {args[1]}")


@router.message(Command("opus"))
async def cmd_opus(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    os.environ["CLAUDE_MODEL"] = MODEL_OPUS
    await message.reply(f"Modello: {MODEL_OPUS}")


@router.message(Command("sonnet"))
async def cmd_sonnet(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    os.environ["CLAUDE_MODEL"] = MODEL_SONNET
    await message.reply(f"Modello: {MODEL_SONNET}")


@router.message(Command("haiku"))
async def cmd_haiku(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    os.environ["CLAUDE_MODEL"] = MODEL_HAIKU
    await message.reply(f"Modello: {MODEL_HAIKU}")


@router.message(Command("effort"))
async def cmd_effort(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or args[1].lower() not in EFFORT_LEVELS:
        current = os.getenv("CLAUDE_EFFORT", DEFAULT_EFFORT)
        await message.reply(f"Uso: /effort <low|medium|high>\nAttuale: {current}")
        return

    level = args[1].lower()
    os.environ["CLAUDE_EFFORT"] = level
    await message.reply(f"Effort: {level} — {EFFORT_LABELS[level]}")


@router.message(Command("turns"))
async def cmd_turns(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].isdigit():
        current = os.getenv("CLAUDE_MAX_TURNS", str(DEFAULT_MAX_TURNS))
        await message.reply(f"Uso: /turns <numero>\nAttuale: {current}")
        return

    n = int(args[1])
    if n < MIN_TURNS or n > MAX_TURNS_LIMIT:
        await message.reply(f"Il valore deve essere tra {MIN_TURNS} e {MAX_TURNS_LIMIT}.")
        return

    os.environ["CLAUDE_MAX_TURNS"] = str(n)
    await message.reply(f"Max turns: {n}")


@router.message(Command("plan"))
async def cmd_plan(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    key = (message.chat.id, get_thread_id(message))
    if key in plan_mode:
        plan_mode.discard(key)
        await message.reply("Planning mode disattivato.")
    else:
        plan_mode.add(key)
        await message.reply(
            "Planning mode attivato per il prossimo messaggio.\n"
            "Claude ragionerà e proporrà un piano senza eseguire nulla."
        )
