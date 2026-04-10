"""
Project discovery and Forum Topic mapping.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("claudio.projects")

PROJECTS_BASE = "/home/assistant/projects"
TOPIC_MAP_FILE = "/home/assistant/memory/topic_map.json"


@dataclass
class ProjectInfo:
    name: str
    path: str
    has_claude_md: bool
    has_git: bool


def discover_projects() -> list[ProjectInfo]:
    """Scan the projects directory for valid projects."""
    base = Path(PROJECTS_BASE)
    if not base.exists():
        log.warning(f"Projects directory not found: {PROJECTS_BASE}")
        return []

    projects = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        has_claude = (entry / "CLAUDE.md").exists()
        has_git = (entry / ".git").exists()
        if has_claude or has_git:
            projects.append(ProjectInfo(
                name=entry.name,
                path=str(entry),
                has_claude_md=has_claude,
                has_git=has_git,
            ))
        else:
            # Check one level deeper for nested projects (e.g., Catechesi/catechesi-website)
            for sub in sorted(entry.iterdir()):
                if not sub.is_dir() or sub.name.startswith("."):
                    continue
                has_claude = (sub / "CLAUDE.md").exists()
                has_git = (sub / ".git").exists()
                if has_claude or has_git:
                    projects.append(ProjectInfo(
                        name=f"{entry.name}/{sub.name}",
                        path=str(sub),
                        has_claude_md=has_claude,
                        has_git=has_git,
                    ))
    return projects


def resolve_project(query: str) -> list[ProjectInfo]:
    """Fuzzy match a project name. Returns matching projects."""
    projects = discover_projects()
    query_lower = query.lower().strip()

    # Exact match first
    for p in projects:
        if p.name.lower() == query_lower:
            return [p]

    # Substring match
    matches = [p for p in projects if query_lower in p.name.lower()]
    return matches


class TopicMap:
    """Persists the mapping of Telegram Forum Topic IDs to project names."""

    def __init__(self) -> None:
        self._map: dict[str, str] = {}  # "chat_id:thread_id" -> project_name
        self._load()

    def _key(self, chat_id: int, thread_id: int) -> str:
        return f"{chat_id}:{thread_id}"

    def _load(self) -> None:
        try:
            with open(TOPIC_MAP_FILE) as f:
                self._map = json.load(f)
            log.info(f"Loaded topic map: {len(self._map)} mappings")
        except (FileNotFoundError, json.JSONDecodeError):
            self._map = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(TOPIC_MAP_FILE), exist_ok=True)
        with open(TOPIC_MAP_FILE, "w") as f:
            json.dump(self._map, f, indent=2)

    def link(self, chat_id: int, thread_id: int, project_name: str) -> None:
        self._map[self._key(chat_id, thread_id)] = project_name
        self._save()
        log.info(f"Linked topic {thread_id} -> {project_name}")

    def unlink(self, chat_id: int, thread_id: int) -> str | None:
        key = self._key(chat_id, thread_id)
        removed = self._map.pop(key, None)
        if removed:
            self._save()
            log.info(f"Unlinked topic {thread_id} (was {removed})")
        return removed

    def get_project(self, chat_id: int, thread_id: int | None) -> str | None:
        if thread_id is None:
            return None
        return self._map.get(self._key(chat_id, thread_id))

    def get_all(self, chat_id: int) -> dict[int, str]:
        """Return all topic mappings for a chat."""
        prefix = f"{chat_id}:"
        result = {}
        for key, project in self._map.items():
            if key.startswith(prefix):
                thread_id = int(key.split(":")[1])
                result[thread_id] = project
        return result
