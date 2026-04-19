"""
Tests for bot.git_ops — diff parsing (pure) and git operations (mocked).
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from bot.git_ops import (
    parse_unified_diff,
    get_project_diff,
    get_all_projects_changes,
    stage_file,
    unstage_file,
    revert_file,
    revert_all,
    commit,
    validate_project_path,
    validate_file_path,
)


# ── Fixtures ─────────────────────────────────────────────────────────

SAMPLE_MODIFIED = """\
diff --git a/src/lib/use-narration.ts b/src/lib/use-narration.ts
index abc1234..def5678 100644
--- a/src/lib/use-narration.ts
+++ b/src/lib/use-narration.ts
@@ -45,7 +45,9 @@ export function useNarration() {
   const locale = useLocale();
-  import { old } from "legacy";
+  import { updated } from "modern";
+  import { extra } from "utils";
   const data = fetchData();
@@ -80,4 +82,4 @@ function helper() {
-  setNarration(text);
+  updateNarration(text);
   return result;
"""

SAMPLE_NEW_FILE = """\
diff --git a/src/new-file.ts b/src/new-file.ts
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/src/new-file.ts
@@ -0,0 +1,3 @@
+export const hello = "world";
+export const foo = "bar";
+export const baz = 42;
"""

SAMPLE_DELETED_FILE = """\
diff --git a/src/old-file.ts b/src/old-file.ts
deleted file mode 100644
index abc1234..0000000
--- a/src/old-file.ts
+++ /dev/null
@@ -1,2 +0,0 @@
-export const legacy = true;
-export const unused = false;
"""

SAMPLE_RENAMED_FILE = """\
diff --git a/src/old-name.ts b/src/new-name.ts
similarity index 95%
rename from src/old-name.ts
rename to src/new-name.ts
index abc1234..def5678 100644
--- a/src/old-name.ts
+++ b/src/new-name.ts
@@ -1,3 +1,3 @@
 export const value = 1;
-export const old = true;
+export const renamed = true;
 export const kept = false;
"""

SAMPLE_BINARY = """\
diff --git a/image.png b/image.png
index abc1234..def5678 100644
Binary files a/image.png and b/image.png differ
"""

SAMPLE_MULTIPLE_HUNKS = """\
diff --git a/src/index.ts b/src/index.ts
index abc1234..def5678 100644
--- a/src/index.ts
+++ b/src/index.ts
@@ -10,3 +10,4 @@ import { foo } from "bar";
 const a = 1;
 const b = 2;
+const c = 3;
 export default a;
@@ -50,3 +51,3 @@ function helper() {
 const x = true;
-const y = false;
+const y = true;
 return x;
"""


# ══════════════════════════════════════════════════════════════════════
# parse_unified_diff — Pure tests (no I/O, no mocks)
# ══════════════════════════════════════════════════════════════════════

class TestParseUnifiedDiff:
    def test_single_file_modified(self):
        files = parse_unified_diff(SAMPLE_MODIFIED)
        assert len(files) == 1
        f = files[0]
        assert f.path == "src/lib/use-narration.ts"
        assert f.status == "modified"
        assert f.staged is False
        assert f.insertions == 3
        assert f.deletions == 2
        assert len(f.hunks) == 2

    def test_new_file(self):
        files = parse_unified_diff(SAMPLE_NEW_FILE)
        assert len(files) == 1
        f = files[0]
        assert f.path == "src/new-file.ts"
        assert f.status == "added"
        assert f.insertions == 3
        assert f.deletions == 0

    def test_deleted_file(self):
        files = parse_unified_diff(SAMPLE_DELETED_FILE)
        assert len(files) == 1
        f = files[0]
        assert f.path == "src/old-file.ts"
        assert f.status == "deleted"
        assert f.insertions == 0
        assert f.deletions == 2

    def test_renamed_file(self):
        files = parse_unified_diff(SAMPLE_RENAMED_FILE)
        assert len(files) == 1
        f = files[0]
        assert f.path == "src/new-name.ts"
        assert f.status == "renamed"
        assert f.insertions == 1
        assert f.deletions == 1

    def test_multiple_hunks(self):
        files = parse_unified_diff(SAMPLE_MULTIPLE_HUNKS)
        assert len(files) == 1
        f = files[0]
        assert len(f.hunks) == 2
        # First hunk: 1 addition
        assert sum(1 for l in f.hunks[0].lines if l.type == "add") == 1
        # Second hunk: 1 add, 1 del
        assert sum(1 for l in f.hunks[1].lines if l.type == "add") == 1
        assert sum(1 for l in f.hunks[1].lines if l.type == "del") == 1

    def test_empty_returns_empty_list(self):
        assert parse_unified_diff("") == []
        assert parse_unified_diff("   \n  ") == []

    def test_binary_file_skipped(self):
        files = parse_unified_diff(SAMPLE_BINARY)
        assert len(files) == 0

    def test_large_diff_skipped(self):
        # Create a diff larger than GIT_MAX_DIFF_SIZE
        big_line = "+" + "x" * 1000 + "\n"
        big_diff = (
            "diff --git a/big.txt b/big.txt\n"
            "index abc..def 100644\n"
            "--- a/big.txt\n"
            "+++ b/big.txt\n"
            "@@ -1,1 +1,600 @@\n"
        )
        big_diff += big_line * 600  # ~600KB > 500KB limit
        files = parse_unified_diff(big_diff)
        assert len(files) == 0

    def test_staged_flag_propagated(self):
        files = parse_unified_diff(SAMPLE_MODIFIED, staged=True)
        assert len(files) == 1
        assert files[0].staged is True

    def test_context_lines_parsed(self):
        files = parse_unified_diff(SAMPLE_MODIFIED)
        f = files[0]
        ctx_lines = [l for h in f.hunks for l in h.lines if l.type == "ctx"]
        assert len(ctx_lines) > 0
        assert ctx_lines[0].content == "  const locale = useLocale();"


# ══════════════════════════════════════════════════════════════════════
# get_project_diff — Mocked subprocess
# ══════════════════════════════════════════════════════════════════════

def _make_proc_mock(stdout: str = "", stderr: str = "", rc: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(
        stdout.encode(), stderr.encode(),
    ))
    proc.returncode = rc
    return proc


class TestGetProjectDiff:
    @pytest.mark.asyncio
    async def test_clean_tree_returns_none(self):
        with patch("bot.git_ops._run_git", new_callable=AsyncMock) as mock_git:
            mock_git.return_value = ("", "", 0)
            result = await get_project_diff("/home/assistant/projects/test-proj")
            assert result is None

    @pytest.mark.asyncio
    async def test_with_unstaged_changes(self):
        async def fake_run_git(pp, *args):
            if "ls-files" in args:
                return ("", "", 0)
            if "--cached" not in args:
                return (SAMPLE_MODIFIED, "", 0)
            return ("", "", 0)

        with patch("bot.git_ops._run_git", side_effect=fake_run_git):
            result = await get_project_diff("/home/assistant/projects/test-proj")
            assert result is not None
            assert result["summary"]["files"] == 1
            assert result["summary"]["insertions"] == 3
            assert result["summary"]["deletions"] == 2
            assert result["files"][0]["staged"] is False

    @pytest.mark.asyncio
    async def test_with_staged_changes(self):
        async def fake_run_git(pp, *args):
            if "ls-files" in args:
                return ("", "", 0)
            if "--cached" in args:
                return (SAMPLE_NEW_FILE, "", 0)
            return ("", "", 0)

        with patch("bot.git_ops._run_git", side_effect=fake_run_git):
            result = await get_project_diff("/home/assistant/projects/test-proj")
            assert result is not None
            assert result["files"][0]["staged"] is True
            assert result["files"][0]["status"] == "added"

    @pytest.mark.asyncio
    async def test_mixed_staged_unstaged(self):
        async def fake_run_git(pp, *args):
            if "ls-files" in args:
                return ("", "", 0)
            if "--cached" in args:
                return (SAMPLE_NEW_FILE, "", 0)
            return (SAMPLE_MODIFIED, "", 0)

        with patch("bot.git_ops._run_git", side_effect=fake_run_git):
            result = await get_project_diff("/home/assistant/projects/test-proj")
            assert result is not None
            assert result["summary"]["files"] == 2
            unstaged = [f for f in result["files"] if not f["staged"]]
            staged = [f for f in result["files"] if f["staged"]]
            assert len(unstaged) == 1
            assert len(staged) == 1

    @pytest.mark.asyncio
    async def test_untracked_files(self):
        async def fake_run_git(pp, *args):
            if "ls-files" in args:
                return ("new-file.ts\nsrc/other.ts\n", "", 0)
            return ("", "", 0)

        with patch("bot.git_ops._run_git", side_effect=fake_run_git):
            result = await get_project_diff("/home/assistant/projects/test-proj")
            assert result is not None
            assert result["summary"]["files"] == 2
            for f in result["files"]:
                assert f["status"] == "untracked"
                assert f["staged"] is False
                assert f["hunks"] == []
                assert f["insertions"] == 0
                assert f["deletions"] == 0
            paths = [f["path"] for f in result["files"]]
            assert "new-file.ts" in paths
            assert "src/other.ts" in paths

    @pytest.mark.asyncio
    async def test_mixed_diff_and_untracked(self):
        async def fake_run_git(pp, *args):
            if "ls-files" in args:
                return ("brand-new.ts\n", "", 0)
            if "--cached" not in args:
                return (SAMPLE_MODIFIED, "", 0)
            return ("", "", 0)

        with patch("bot.git_ops._run_git", side_effect=fake_run_git):
            result = await get_project_diff("/home/assistant/projects/test-proj")
            assert result is not None
            assert result["summary"]["files"] == 2
            statuses = {f["status"] for f in result["files"]}
            assert "modified" in statuses
            assert "untracked" in statuses

    @pytest.mark.asyncio
    async def test_invalid_path_raises(self):
        with pytest.raises(ValueError, match="outside base"):
            await get_project_diff("/tmp/evil")


# ══════════════════════════════════════════════════════════════════════
# Git action functions — Mocked subprocess
# ══════════════════════════════════════════════════════════════════════

class TestStageFile:
    @pytest.mark.asyncio
    async def test_success(self):
        with patch("bot.git_ops._run_git", new_callable=AsyncMock) as mock:
            mock.return_value = ("", "", 0)
            result = await stage_file("/home/assistant/projects/test", "src/file.ts")
            assert result is True
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_path_rejected(self):
        with pytest.raises(ValueError, match="outside base"):
            await stage_file("/tmp/evil", "file.ts")

    @pytest.mark.asyncio
    async def test_path_traversal_rejected(self):
        with pytest.raises(ValueError, match="traversal"):
            await stage_file("/home/assistant/projects/test", "../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_absolute_file_path_rejected(self):
        with pytest.raises(ValueError, match="Absolute"):
            await stage_file("/home/assistant/projects/test", "/etc/passwd")


class TestRevertFile:
    @pytest.mark.asyncio
    async def test_success(self):
        with patch("bot.git_ops._run_git", new_callable=AsyncMock) as mock:
            mock.return_value = ("", "", 0)
            result = await revert_file("/home/assistant/projects/test", "src/file.ts")
            assert result is True
            # Should call reset + checkout
            assert mock.call_count == 2


class TestRevertAll:
    @pytest.mark.asyncio
    async def test_success(self):
        with patch("bot.git_ops._run_git", new_callable=AsyncMock) as mock:
            mock.return_value = ("", "", 0)
            result = await revert_all("/home/assistant/projects/test")
            assert result is True
            assert mock.call_count == 2


class TestCommit:
    @pytest.mark.asyncio
    async def test_success_returns_hash(self):
        async def fake_run_git(pp, *args):
            if "commit" in args:
                return ("", "", 0)
            if "rev-parse" in args:
                return ("abc1234", "", 0)
            return ("", "", 0)

        with patch("bot.git_ops._run_git", side_effect=fake_run_git):
            result = await commit("/home/assistant/projects/test", "fix: something")
            assert result == "abc1234"

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self):
        with pytest.raises(ValueError, match="empty"):
            await commit("/home/assistant/projects/test", "")

        with pytest.raises(ValueError, match="empty"):
            await commit("/home/assistant/projects/test", "   ")


# ══════════════════════════════════════════════════════════════════════
# Path validation
# ══════════════════════════════════════════════════════════════════════

class TestValidateProjectPath:
    def test_under_base(self):
        from bot.config import PROJECTS_BASE
        base_resolved = str(PROJECTS_BASE.resolve())
        p = validate_project_path("/home/assistant/projects/my-app")
        assert str(p).startswith(base_resolved)

    def test_rejects_outside(self):
        with pytest.raises(ValueError, match="outside base"):
            validate_project_path("/tmp/evil")

    def test_rejects_prefix_collision(self):
        with pytest.raises(ValueError, match="outside base"):
            validate_project_path("/home/assistant/projects-evil")

    def test_rejects_traversal(self):
        with pytest.raises(ValueError, match="outside base"):
            validate_project_path("/home/assistant/projects/../../etc")


class TestValidateFilePath:
    def test_rejects_dotdot(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_file_path("../../../etc/passwd")

    def test_rejects_absolute(self):
        with pytest.raises(ValueError, match="Absolute"):
            validate_file_path("/etc/passwd")

    def test_accepts_normal_path(self):
        assert validate_file_path("src/lib/file.ts") == "src/lib/file.ts"

    def test_accepts_nested_path(self):
        assert validate_file_path("a/b/c/d.txt") == "a/b/c/d.txt"


# ══════════════════════════════════════════════════════════════════════
# get_all_projects_changes — Mocked discover_projects + get_project_diff
# ══════════════════════════════════════════════════════════════════════

class TestGetAllProjectsChanges:
    @pytest.mark.asyncio
    async def test_returns_projects_with_changes(self):
        from bot.projects import ProjectInfo

        projects = [
            ProjectInfo(name="proj-a", path="/home/assistant/projects/proj-a", has_claude_md=True, has_git=True),
            ProjectInfo(name="proj-b", path="/home/assistant/projects/proj-b", has_claude_md=False, has_git=True),
        ]
        diff_a = {"project": "proj-a", "summary": {"files": 1, "insertions": 5, "deletions": 0}, "files": []}
        diff_b = {"project": "proj-b", "summary": {"files": 2, "insertions": 3, "deletions": 1}, "files": []}

        with patch("bot.projects.discover_projects", return_value=projects), \
             patch("bot.git_ops.get_project_diff", new_callable=AsyncMock) as mock_diff:
            mock_diff.side_effect = [diff_a, diff_b]
            results = await get_all_projects_changes()
            assert len(results) == 2
            assert results[0]["project"] == "proj-a"
            assert results[1]["project"] == "proj-b"

    @pytest.mark.asyncio
    async def test_skips_non_git_projects(self):
        from bot.projects import ProjectInfo

        projects = [
            ProjectInfo(name="no-git", path="/home/assistant/projects/no-git", has_claude_md=True, has_git=False),
            ProjectInfo(name="has-git", path="/home/assistant/projects/has-git", has_claude_md=True, has_git=True),
        ]
        diff = {"project": "has-git", "summary": {"files": 1, "insertions": 1, "deletions": 0}, "files": []}

        with patch("bot.projects.discover_projects", return_value=projects), \
             patch("bot.git_ops.get_project_diff", new_callable=AsyncMock, return_value=diff):
            results = await get_all_projects_changes()
            assert len(results) == 1
            assert results[0]["project"] == "has-git"

    @pytest.mark.asyncio
    async def test_skips_clean_projects(self):
        from bot.projects import ProjectInfo

        projects = [
            ProjectInfo(name="clean", path="/home/assistant/projects/clean", has_claude_md=True, has_git=True),
        ]

        with patch("bot.projects.discover_projects", return_value=projects), \
             patch("bot.git_ops.get_project_diff", new_callable=AsyncMock, return_value=None):
            results = await get_all_projects_changes()
            assert len(results) == 0

    @pytest.mark.asyncio
    async def test_skips_broken_projects(self):
        from bot.projects import ProjectInfo

        projects = [
            ProjectInfo(name="broken", path="/home/assistant/projects/broken", has_claude_md=True, has_git=True),
            ProjectInfo(name="ok", path="/home/assistant/projects/ok", has_claude_md=True, has_git=True),
        ]
        diff = {"project": "ok", "summary": {"files": 1, "insertions": 1, "deletions": 0}, "files": []}

        with patch("bot.projects.discover_projects", return_value=projects), \
             patch("bot.git_ops.get_project_diff", new_callable=AsyncMock, side_effect=[Exception("broken"), diff]):
            results = await get_all_projects_changes()
            assert len(results) == 1
            assert results[0]["project"] == "ok"
