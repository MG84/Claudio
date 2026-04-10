"""
Shared state across handlers.
Singleton instances of bridge, topic_map, and per-chat flags.
"""

from aiogram.types import Message

from bot.claude_bridge import ClaudeBridge
from bot.projects import TopicMap, resolve_project

# Singletons
bridge = ClaudeBridge()
topic_map = TopicMap()

# Per-chat flags: set of (chat_id, thread_id)
plan_mode: set[tuple[int, int | None]] = set()
voice_requested: set[tuple[int, int | None]] = set()
last_response: dict[tuple[int, int | None], str] = {}


def get_thread_id(message: Message) -> int | None:
    return message.message_thread_id


def get_project_for_message(message: Message) -> tuple[str | None, str | None]:
    """Returns (project_name, project_path) for the current message context."""
    thread_id = get_thread_id(message)
    project_name = topic_map.get_project(message.chat.id, thread_id)
    if project_name:
        projects = resolve_project(project_name)
        if projects:
            return projects[0].name, projects[0].path
    return None, None
