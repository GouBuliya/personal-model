from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-push"
BOOTSTRAP = ROOT / "scripts" / "bootstrap_compound_engineering.py"
SKILL = ROOT / ".claude" / "skills" / "deliver" / "SKILL.md"


def _run(
    *command: str,
    cwd: Path,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _git(repo: Path, *args: str) -> str:
    result = _run("git", "-c", "commit.gpgsign=false", *args, cwd=repo)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _init_repo(path: Path) -> str:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Synthetic Developer")
    _git(path, "config", "user.email", "developer@example.com")
    (path / "README.md").write_text("# Fixture\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "-c", "core.hooksPath=/dev/null", "commit", "-m", "initial")
    return _git(path, "rev-parse", "HEAD")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _valid_goal(*, result: str = "PASS", lane: str = "01-core") -> str:
    return textwrap.dedent(
        f"""\
        # Goal: Example

        Goal: example
        Status: ACTIVE
        Started: 2026-01-01T00:00:00Z
        Updated: 2026-01-01T00:05:00Z
        Current PR: not-opened
        Current lane: {lane}
        Next action: Open the pull request.
        Auto-merge: authorized

        ## Prompt record

        Add a synthetic feature.

        ## Definition of done

        The fixture passes.

        ## Acceptance criteria

        - [x] Fixture passes.

        ## Scope

        - Synthetic fixture only.

        ## Constraints

        - No external services.

        ## Repository map impact

        - Test fixture.

        ## PR dependency DAG

        1. Core fixture.

        ## Worktree lanes

        - Lane: {lane}

        ## Decision log

        - Keep the fixture small.

        ## Friction ledger

        - Classification: covered

        ## Compound engineering delta

        - Outcome: No shared change because the existing fixture covers this path.

        ## Verification receipts

        - Lane: {lane}
        - Command: make check
        - Result: {result}
        - Timestamp: 2026-01-01T00:05:00Z
        - Evidence: synthetic fixture

        ## Metrics

        - CI reruns: 0
        - Rework cycles: 0
        - Review-fix cycles: 0
        - Retained infrastructure improvements: 0

        ## Delivery record

        Active.
        """
    )


def _check_range(repo: Path, base: str, head: str, branch: str) -> subprocess.CompletedProcess[str]:
    return _run(str(HOOK), "--check-range", base, head, branch, cwd=repo)


def test_pre_push_blocks_direct_default_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    head = _init_repo(repo)
    result = _check_range(repo, head, head, "main")
    assert result.returncode != 0
    assert "direct pushes to main are blocked" in result.stderr


def test_pre_push_requires_current_goal_document(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = _init_repo(repo)
    _git(repo, "checkout", "-b", "deliver/example/01-core")
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    head = _commit(repo, "add feature")

    missing = _check_range(repo, base, head, "deliver/example/01-core")
    assert missing.returncode != 0
    assert "must contain docs/evolutions/example.md" in missing.stderr

    goal = repo / "docs" / "evolutions" / "example.md"
    goal.parent.mkdir(parents=True)
    goal.write_text(_valid_goal(), encoding="utf-8")
    valid_head = _commit(repo, "add delivery goal")
    valid = _check_range(repo, base, valid_head, "deliver/example/01-core")
    assert valid.returncode == 0, valid.stderr

    (repo / "feature.txt").write_text("feature changed\n", encoding="utf-8")
    stale_head = _commit(repo, "change feature without checkpoint")
    stale = _check_range(repo, valid_head, stale_head, "deliver/example/01-core")
    assert stale.returncode != 0
    assert "must change in every delivery push" in stale.stderr


def test_pre_push_rejects_failed_verification_receipt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = _init_repo(repo)
    _git(repo, "checkout", "-b", "deliver/example/01-core")
    goal = repo / "docs" / "evolutions" / "example.md"
    goal.parent.mkdir(parents=True)
    goal.write_text(_valid_goal(result="FAIL"), encoding="utf-8")
    head = _commit(repo, "add unverified goal")

    result = _check_range(repo, base, head, "deliver/example/01-core")
    assert result.returncode != 0
    assert "passing verification receipt" in result.stderr


def test_bootstrap_is_idempotent_and_preserves_customization(tmp_path: Path) -> None:
    target = tmp_path / "portable-project"
    _init_repo(target)
    command = (
        sys.executable,
        str(BOOTSTRAP),
        str(target),
        "--project-name",
        "Portable Project",
        "--default-branch",
        "main",
        "--check-command",
        "python -m unittest",
        "--apply",
    )

    first = _run(*command, cwd=ROOT)
    assert first.returncode == 0, first.stderr
    assert (target / "docs" / "ai-delivery-sop.md").is_file()
    assert (target / ".claude" / "skills" / "deliver" / "SKILL.md").is_file()
    hook = target / ".githooks" / "pre-push"
    assert stat.S_IMODE(hook.stat().st_mode) == 0o755

    second = _run(*command, cwd=ROOT)
    assert second.returncode == 0, second.stderr
    assert "unchanged" in second.stdout

    sop = target / "docs" / "ai-delivery-sop.md"
    customized = sop.read_text(encoding="utf-8") + "\nLocal policy note.\n"
    sop.write_text(customized, encoding="utf-8")
    third = _run(*command, cwd=ROOT)
    assert third.returncode == 0, third.stderr
    assert "customized" in third.stdout
    assert sop.read_text(encoding="utf-8") == customized


def test_bootstrap_previews_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "preview-project"
    _init_repo(target)
    result = _run(
        sys.executable,
        str(BOOTSTRAP),
        str(target),
        "--project-name",
        "Preview Project",
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "Preview only" in result.stdout
    assert not (target / "docs" / "ai-delivery-sop.md").exists()


def test_bootstrap_supports_non_python_repository(tmp_path: Path) -> None:
    target = tmp_path / "frontend-project"
    _init_repo(target)
    (target / "package.json").write_text('{"scripts":{"test":"node --test"}}\n', encoding="utf-8")
    _commit(target, "add frontend manifest")

    result = _run(
        sys.executable,
        str(BOOTSTRAP),
        str(target),
        "--project-name",
        "Frontend Project",
        "--check-command",
        "npm test",
        "--apply",
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    makefile = (target / "Makefile").read_text(encoding="utf-8")
    assert "CHECK_COMMAND = npm test" in makefile


def test_delivery_skill_is_manual_and_single_session() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "name: deliver" in text
    assert "disable-model-invocation: true" in text
    assert "only code writer" in text
    assert "make check" in text
    assert os.fspath(Path("docs/evolutions")) in text
