"""
Core commands: /start, /status, /new, /resume, /compact
"""

import os

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.auth import is_allowed_user
from bot.config import DEFAULT_MODEL, DEFAULT_EFFORT, DEFAULT_MAX_TURNS
from bot.handlers._state import bridge, get_project_for_message, get_thread_id, plan_mode, voice_requested

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    await message.reply(
        "Ciao! Sono Claudio, il tuo assistente personale.\n\n"
        "Comandi:\n"
        "/projects — lista progetti disponibili\n"
        "/link <nome> — collega questo topic a un progetto\n"
        "/unlink — scollega questo topic\n"
        "/new — nuova conversazione\n"
        "/resume — ripristina sessione precedente\n"
        "/status — stato del sistema\n"
        "/model <nome> — cambia modello\n"
        "/opus /sonnet /haiku — shortcut modello\n"
        "/effort <low|medium|high> — livello ragionamento\n"
        "/turns <n> — max step per risposta\n"
        "/plan — prossimo messaggio in planning mode\n"
        "/compact — forza compattazione contesto\n"
        "/voice — forza risposta vocale\n"
        "/text — mostra testo ultima risposta vocale"
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    project_name, project_path = get_project_for_message(message)
    session_id = bridge.get_session_id(message.chat.id, project_name)
    model = os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)
    effort = os.getenv("CLAUDE_EFFORT", DEFAULT_EFFORT)
    max_turns = os.getenv("CLAUDE_MAX_TURNS", str(DEFAULT_MAX_TURNS))
    plan_key = (message.chat.id, get_thread_id(message))

    lines = [
        "Stato: attivo",
        f"Modello: {model}",
        f"Effort: {effort}",
        f"Max turns: {max_turns}",
        f"Plan mode: {'si' if plan_key in plan_mode else 'no'}",
        f"Sessione: {session_id or 'nessuna'}",
    ]
    if project_name:
        lines.append(f"Progetto: **{project_name}**")
        lines.append(f"Directory: `{project_path}`")
    else:
        lines.append("Progetto: nessuno (workspace generico)")

    await message.reply("\n".join(lines))


@router.message(Command("new"))
async def cmd_new(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    project_name, _ = get_project_for_message(message)
    bridge.reset_session(message.chat.id, project_name)
    ctx = f"per **{project_name}**" if project_name else "(generale)"
    await message.reply(f"Nuova conversazione iniziata {ctx}.\nUsa /resume per tornare alla sessione precedente.")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    project_name, _ = get_project_for_message(message)
    session_id = bridge.resume_previous(message.chat.id, project_name)
    if session_id:
        ctx = f"**{project_name}**" if project_name else "generale"
        await message.reply(f"Sessione precedente ripristinata ({ctx}).")
    else:
        await message.reply("Nessuna sessione precedente disponibile.")


@router.message(Command("compact"))
async def cmd_compact(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    project_name, _ = get_project_for_message(message)
    bridge.reset_session(message.chat.id, project_name)
    ctx = f"**{project_name}**" if project_name else "generale"
    await message.reply(f"Contesto compattato (sessione {ctx} resettata).")
