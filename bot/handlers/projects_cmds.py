"""
Project commands: /projects, /link, /unlink
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.auth import is_allowed_user
from bot.projects import discover_projects, resolve_project
from bot.handlers._state import topic_map, get_thread_id

router = Router()


@router.message(Command("projects"))
async def cmd_projects(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    projects = discover_projects()
    if not projects:
        await message.reply("Nessun progetto trovato.")
        return

    linked = topic_map.get_all(message.chat.id)
    linked_projects = set(linked.values())

    lines = ["**Progetti disponibili:**\n"]
    for p in projects:
        tags = []
        if p.has_claude_md:
            tags.append("CLAUDE.md")
        if p.has_git:
            tags.append("git")
        tag_str = f" ({', '.join(tags)})" if tags else ""

        if p.name in linked_projects:
            lines.append(f"  🔗 **{p.name}**{tag_str}")
        else:
            lines.append(f"  ⚪ {p.name}{tag_str}")

    lines.append(f"\nTotale: {len(projects)} progetti")
    await message.reply("\n".join(lines))


@router.message(Command("link"))
async def cmd_link(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    thread_id = get_thread_id(message)
    if thread_id is None:
        await message.reply(
            "Questo comando funziona solo dentro un Forum Topic.\n"
            "Crea un gruppo con Forum Topics e usa /link lì."
        )
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Uso: /link <nome-progetto>\nEsempio: /link nutribot")
        return

    query = args[1].strip()
    matches = resolve_project(query)

    if not matches:
        await message.reply(f'Nessun progetto trovato per "{query}".\nUsa /projects per vedere la lista.')
        return

    if len(matches) > 1:
        names = "\n".join(f"  - {m.name}" for m in matches)
        await message.reply(f'Più progetti corrispondono a "{query}":\n{names}\n\nSpecifica il nome completo.')
        return

    project = matches[0]
    topic_map.link(message.chat.id, thread_id, project.name)
    await message.reply(
        f"🔗 Topic collegato a **{project.name}**\n"
        f"Directory: `{project.path}`\n"
        f"CLAUDE.md: {'si' if project.has_claude_md else 'no'}\n\n"
        f"Ora ogni messaggio qui verrà elaborato nel contesto di questo progetto."
    )


@router.message(Command("unlink"))
async def cmd_unlink(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    thread_id = get_thread_id(message)
    if thread_id is None:
        await message.reply("Questo comando funziona solo dentro un Forum Topic.")
        return

    removed = topic_map.unlink(message.chat.id, thread_id)
    if removed:
        await message.reply(f"Topic scollegato da **{removed}**.")
    else:
        await message.reply("Questo topic non era collegato a nessun progetto.")
