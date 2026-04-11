"""
Bridge between Telegram and Claude Code via Agent SDK.
Manages persistent sessions per chat and per project, with concurrency safety.
"""

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass

from claude_agent_sdk import query as sdk_query, ClaudeAgentOptions, AssistantMessage, ResultMessage

from bot.config import (
    GENERAL_WORKSPACE, ALLOWED_TOOLS, PERMISSION_MODE,
    GENERAL_SESSION_KEY, NO_OUTPUT_MESSAGE,
    DEFAULT_MODEL, DEFAULT_EFFORT, DEFAULT_MAX_TURNS,
    get_runtime,
)
from bot.prompts import BASE_PROMPT, PROJECT_PROMPT_SUFFIX

log = logging.getLogger("claudio.bridge")

MAX_RETRIES = 2
RETRY_BASE_DELAY = 2.0
TOOL_OUTPUT_PREVIEW_LENGTH = 500


def _format_tool_input(tool: str, input_data: dict) -> str:
    """Format tool input for human-readable display."""
    if tool == "Read":
        path = input_data.get("file_path", "")
        limit = input_data.get("limit", "")
        return f"{path}" + (f" (righe {limit})" if limit else "")
    if tool == "Write":
        return input_data.get("file_path", "")
    if tool == "Edit":
        path = input_data.get("file_path", "")
        old = str(input_data.get("old_string", ""))[:80]
        return f"{path} — \"{old}...\""
    if tool == "Bash":
        return input_data.get("command", "")[:200]
    if tool in ("Glob", "Grep"):
        pattern = input_data.get("pattern", "")
        path = input_data.get("path", "")
        return f"{pattern}" + (f" in {path}" if path else "")
    if tool == "WebSearch":
        return input_data.get("query", "")
    if tool == "WebFetch":
        return input_data.get("url", "")
    return str(input_data)[:200]


def _format_tool_output(tool: str | None, content: str | list | None) -> str:
    """Format tool result output for human-readable display."""
    if content is None:
        return ""
    if isinstance(content, list):
        texts = [c.get("text", "") if isinstance(c, dict) else str(c) for c in content]
        content = "\n".join(texts)
    text = str(content)
    if len(text) > TOOL_OUTPUT_PREVIEW_LENGTH:
        return text[:TOOL_OUTPUT_PREVIEW_LENGTH] + "..."
    return text


@dataclass
class SessionInfo:
    session_id: str | None = None
    message_count: int = 0


class ClaudeBridge:
    def __init__(self) -> None:
        self._sessions: dict[tuple[int, str], SessionInfo] = {}
        self._previous_sessions: dict[tuple[int, str], SessionInfo] = {}
        self._locks: dict[tuple[int, str], asyncio.Lock] = {}

    def _session_key(self, chat_id: int, project_name: str | None) -> tuple[int, str]:
        return (chat_id, project_name or GENERAL_SESSION_KEY)

    def _get_lock(self, key: tuple[int, str]) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def get_session_id(self, chat_id: int, project_name: str | None = None) -> str | None:
        key = self._session_key(chat_id, project_name)
        session = self._sessions.get(key)
        return session.session_id if session else None

    def reset_session(self, chat_id: int, project_name: str | None = None) -> None:
        key = self._session_key(chat_id, project_name)
        current = self._sessions.get(key)
        if current and current.session_id:
            self._previous_sessions[key] = current
        self._sessions.pop(key, None)
        log.info(f"Session reset: chat={chat_id}, project={project_name or 'general'}")

    def resume_previous(self, chat_id: int, project_name: str | None = None) -> str | None:
        key = self._session_key(chat_id, project_name)
        previous = self._previous_sessions.get(key)
        if previous:
            self._sessions[key] = previous
            self._previous_sessions.pop(key, None)
            log.info(f"Session resumed: chat={chat_id}, session={previous.session_id}")
            return previous.session_id
        return None

    def _build_system_prompt(self, project_name: str | None, project_path: str | None) -> str:
        prompt = BASE_PROMPT
        if project_name and project_path:
            prompt += PROJECT_PROMPT_SUFFIX.format(
                project_name=project_name,
                project_path=project_path,
            )
        return prompt

    async def query(
        self,
        chat_id: int,
        prompt: str,
        project_name: str | None = None,
        project_path: str | None = None,
    ) -> str:
        key = self._session_key(chat_id, project_name)
        lock = self._get_lock(key)

        if lock.locked():
            return "Sto ancora elaborando il messaggio precedente. Attendi..."

        async with lock:
            return await self._execute_query(key, prompt, project_name, project_path)

    async def _execute_query(
        self,
        key: tuple[int, str],
        prompt: str,
        project_name: str | None,
        project_path: str | None,
    ) -> str:
        session = self._sessions.get(key, SessionInfo())
        model = get_runtime("CLAUDE_MODEL", DEFAULT_MODEL)
        effort = get_runtime("CLAUDE_EFFORT", DEFAULT_EFFORT)
        max_turns = int(get_runtime("CLAUDE_MAX_TURNS", str(DEFAULT_MAX_TURNS)))

        cwd = project_path or str(GENERAL_WORKSPACE)
        system_prompt = self._build_system_prompt(project_name, project_path)

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            permission_mode=PERMISSION_MODE,
            allowed_tools=ALLOWED_TOOLS,
            model=model,
            cwd=cwd,
            max_turns=max_turns,
            effort=effort,
        )

        if session.session_id:
            options.resume = session.session_id

        from bot.monitor import emit
        await emit("query_start", {
            "project": project_name or "general",
            "model": model,
            "effort": effort,
        })
        query_start_time = time.monotonic()

        for attempt in range(MAX_RETRIES + 1):
            try:
                response_parts, new_session_id = await self._call_sdk(prompt, options, project_name)
                break
            except Exception as e:
                error_str = str(e).lower()

                # Non-retriable errors
                if "authentication" in error_str or "invalid" in error_str:
                    raise

                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
                    log.warning(f"Retry {attempt + 1}/{MAX_RETRIES} after {delay:.1f}s: {e}")
                    await asyncio.sleep(delay)

                    # If session error, try fresh
                    if session.session_id:
                        options.resume = None
                        self._sessions.pop(key, None)
                else:
                    raise

        duration = time.monotonic() - query_start_time

        if new_session_id:
            session.session_id = new_session_id
            session.message_count += 1
            self._sessions[key] = session
            log.info(
                f"Chat {key[0]}, project={project_name or 'general'}: "
                f"session={new_session_id}, messages={session.message_count}"
            )

        await emit("query_end", {
            "project": project_name or "general",
            "duration_s": round(duration, 1),
            "session_id": new_session_id,
            "message_count": session.message_count,
        })

        # Emit git changes for the Changes tab
        if project_path:
            try:
                from bot.git_ops import get_project_diff
                from bot.config import CHANGES_EVENT
                diff = await get_project_diff(project_path)
                if diff:
                    await emit(CHANGES_EVENT, diff)
            except Exception as e:
                log.warning(f"Git diff failed: {e}")

        result = "\n".join(response_parts).strip()
        return result or NO_OUTPUT_MESSAGE

    async def _call_sdk(
        self, prompt: str, options: ClaudeAgentOptions, project_name: str | None = None
    ) -> tuple[list[str], str | None]:
        from bot.monitor import emit

        project_label = project_name or "general"
        response_parts: list[str] = []
        new_session_id: str | None = None

        last_tool_name: str | None = None

        async for message in sdk_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text"):
                        response_parts.append(block.text)
                    elif hasattr(block, "name"):
                        # ToolUseBlock
                        last_tool_name = block.name
                        tool_input = getattr(block, "input", {})
                        asyncio.create_task(emit("tool_use", {
                            "project": project_label,
                            "tool": block.name,
                            "input": _format_tool_input(block.name, tool_input),
                        }))
                    elif hasattr(block, "tool_use_id"):
                        # ToolResultBlock
                        content = getattr(block, "content", "")
                        is_error = getattr(block, "is_error", False)
                        asyncio.create_task(emit("tool_result", {
                            "project": project_label,
                            "tool": last_tool_name or "unknown",
                            "output": _format_tool_output(last_tool_name, content),
                            "is_error": is_error,
                        }))
            elif isinstance(message, ResultMessage):
                if hasattr(message, "session_id"):
                    new_session_id = message.session_id
                if message.total_cost_usd:
                    log.info(f"Cost: ${message.total_cost_usd:.4f}")
                    asyncio.create_task(emit("cost", {
                        "project": project_label,
                        "cost_usd": message.total_cost_usd,
                    }))

        return response_parts, new_session_id
