"""
Git operations for the Changes tab: diff parsing, stage, revert, commit.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from bot.config import (
    PROJECTS_BASE,
    GIT_DIFF_CONTEXT_LINES,
    GIT_MAX_DIFF_SIZE,
)

log = logging.getLogger("claudio.git")


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class DiffLine:
    type: str   # "ctx" | "add" | "del"
    content: str


@dataclass
class DiffHunk:
    header: str
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class DiffFile:
    path: str
    status: str  # "modified" | "added" | "deleted" | "renamed"
    staged: bool
    insertions: int = 0
    deletions: int = 0
    hunks: list[DiffHunk] = field(default_factory=list)


# ── Path validation ──────────────────────────────────────────────────

def validate_project_path(project_path: str) -> Path:
    """Validate that project_path is under PROJECTS_BASE."""
    resolved = Path(project_path).resolve()
    base = PROJECTS_BASE.resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"Project path outside base: {project_path}")
    return resolved


def validate_file_path(file_path: str) -> str:
    """Validate a relative file path (no .., no absolute)."""
    if os.path.isabs(file_path):
        raise ValueError(f"Absolute file path not allowed: {file_path}")
    if ".." in file_path.split(os.sep):
        raise ValueError(f"Path traversal not allowed: {file_path}")
    return file_path


# ── Diff parsing (pure function — no I/O) ───────────────────────────

_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@(.*)$")


def parse_unified_diff(raw: str, staged: bool = False) -> list[DiffFile]:
    """Parse unified diff output into structured DiffFile objects."""
    if not raw or not raw.strip():
        return []

    files: list[DiffFile] = []
    current_file: DiffFile | None = None
    current_hunk: DiffHunk | None = None
    current_raw_size = 0

    for line in raw.split("\n"):
        # New file header
        header_match = _DIFF_HEADER_RE.match(line)
        if header_match:
            # Save previous file if valid
            if current_file and current_raw_size <= GIT_MAX_DIFF_SIZE:
                files.append(current_file)

            path_b = header_match.group(2)
            current_file = DiffFile(
                path=path_b, status="modified", staged=staged,
            )
            current_hunk = None
            current_raw_size = 0
            continue

        if current_file is None:
            continue

        current_raw_size += len(line.encode("utf-8", errors="replace"))

        # File status detection
        if line.startswith("new file mode"):
            current_file.status = "added"
            continue
        if line.startswith("deleted file mode"):
            current_file.status = "deleted"
            continue
        if line.startswith("rename from "):
            current_file.status = "renamed"
            continue
        if line.startswith("rename to "):
            continue
        if line.startswith("Binary files"):
            # Skip binary files entirely
            current_file = None
            continue

        # Index, --- , +++ lines — skip
        if line.startswith("index ") or line.startswith("--- ") or line.startswith("+++ "):
            continue

        # Hunk header
        hunk_match = _HUNK_HEADER_RE.match(line)
        if hunk_match:
            current_hunk = DiffHunk(header=line)
            current_file.hunks.append(current_hunk)
            continue

        if current_hunk is None:
            continue

        # Diff lines
        if line.startswith("+"):
            current_hunk.lines.append(DiffLine(type="add", content=line[1:]))
            current_file.insertions += 1
        elif line.startswith("-"):
            current_hunk.lines.append(DiffLine(type="del", content=line[1:]))
            current_file.deletions += 1
        elif line.startswith(" "):
            current_hunk.lines.append(DiffLine(type="ctx", content=line[1:]))
        elif line.startswith("\\"):
            # "\ No newline at end of file" — skip
            continue

    # Save last file
    if current_file and current_raw_size <= GIT_MAX_DIFF_SIZE:
        files.append(current_file)

    return files


# ── Git command helpers ──────────────────────────────────────────────

async def _run_git(project_path: str, *args: str) -> tuple[str, str, int]:
    """Run a git command and return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", project_path, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
        proc.returncode or 0,
    )


def _file_to_dict(f: DiffFile) -> dict:
    """Convert a DiffFile to a JSON-serializable dict."""
    return {
        "path": f.path,
        "status": f.status,
        "staged": f.staged,
        "insertions": f.insertions,
        "deletions": f.deletions,
        "hunks": [
            {
                "header": h.header,
                "lines": [{"type": l.type, "content": l.content} for l in h.lines],
            }
            for h in f.hunks
        ],
    }


# ── Public API ───────────────────────────────────────────────────────

async def get_project_diff(project_path: str) -> dict | None:
    """Get full diff (staged + unstaged) for a project. Returns None if clean."""
    p = validate_project_path(project_path)
    pp = str(p)

    # Unstaged changes
    unstaged_raw, _, _ = await _run_git(pp, "diff", f"--unified={GIT_DIFF_CONTEXT_LINES}")
    # Staged changes
    staged_raw, _, _ = await _run_git(pp, "diff", "--cached", f"--unified={GIT_DIFF_CONTEXT_LINES}")

    unstaged_files = parse_unified_diff(unstaged_raw, staged=False)
    staged_files = parse_unified_diff(staged_raw, staged=True)

    all_files = unstaged_files + staged_files

    if not all_files:
        return None

    # Get project name from path
    try:
        project_name = str(p.relative_to(PROJECTS_BASE.resolve()))
    except ValueError:
        project_name = p.name

    total_insertions = sum(f.insertions for f in all_files)
    total_deletions = sum(f.deletions for f in all_files)

    return {
        "project": project_name,
        "summary": {
            "files": len(all_files),
            "insertions": total_insertions,
            "deletions": total_deletions,
        },
        "files": [_file_to_dict(f) for f in all_files],
    }


async def stage_file(project_path: str, file_path: str) -> bool:
    """Stage a single file."""
    p = validate_project_path(project_path)
    validate_file_path(file_path)
    _, stderr, rc = await _run_git(str(p), "add", "--", file_path)
    if rc != 0:
        log.error(f"git add failed: {stderr}")
    return rc == 0


async def unstage_file(project_path: str, file_path: str) -> bool:
    """Unstage a single file."""
    p = validate_project_path(project_path)
    validate_file_path(file_path)
    _, stderr, rc = await _run_git(str(p), "reset", "HEAD", "--", file_path)
    if rc != 0:
        log.error(f"git reset failed: {stderr}")
    return rc == 0


async def revert_file(project_path: str, file_path: str) -> bool:
    """Revert a single file to HEAD (discard changes)."""
    p = validate_project_path(project_path)
    validate_file_path(file_path)
    # Unstage first, then checkout
    await _run_git(str(p), "reset", "HEAD", "--", file_path)
    _, stderr, rc = await _run_git(str(p), "checkout", "HEAD", "--", file_path)
    if rc != 0:
        log.error(f"git checkout failed: {stderr}")
    return rc == 0


async def revert_all(project_path: str) -> bool:
    """Revert all changes (staged and unstaged)."""
    p = validate_project_path(project_path)
    pp = str(p)
    await _run_git(pp, "reset", "HEAD")
    _, stderr, rc = await _run_git(pp, "checkout", ".")
    if rc != 0:
        log.error(f"git checkout . failed: {stderr}")
    return rc == 0


async def commit(project_path: str, message: str) -> str | None:
    """Commit staged changes. Returns commit hash or None on failure."""
    p = validate_project_path(project_path)
    if not message or not message.strip():
        raise ValueError("Commit message cannot be empty")

    stdout, stderr, rc = await _run_git(str(p), "commit", "-m", message.strip())
    if rc != 0:
        log.error(f"git commit failed: {stderr}")
        return None

    # Extract commit hash
    hash_out, _, _ = await _run_git(str(p), "rev-parse", "--short", "HEAD")
    return hash_out.strip() or None
