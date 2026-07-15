"""Preview or install the compound-engineering starter in another Git repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = REPOSITORY_ROOT / "templates" / "compound-engineering"
DESCRIPTOR_PATH = TEMPLATE_ROOT / ".template.json"
STATE_NAME = ".compound-engineering-bootstrap.json"
TOKENS = ("PROJECT_NAME", "DEFAULT_BRANCH", "CHECK_COMMAND")


@dataclass(frozen=True)
class PlannedFile:
    relative: Path
    content: bytes
    mode: int
    action: str
    installed_hash: str


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _descriptor() -> dict[str, Any]:
    value = _load_json(DESCRIPTOR_PATH)
    if value.get("schema_version") != 1 or not isinstance(value.get("files"), list):
        raise ValueError(f"unsupported template descriptor: {DESCRIPTOR_PATH}")
    return value


def _safe_relative(raw: str) -> Path:
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"unsafe template destination: {raw}")
    return relative


def _render(source: Path, values: dict[str, str]) -> bytes:
    text = source.read_text(encoding="utf-8")
    for token in TOKENS:
        text = text.replace("{{" + token + "}}", values[token])
    unresolved = [token for token in TOKENS if "{{" + token + "}}" in text]
    if unresolved:
        raise ValueError(f"unresolved tokens in {source}: {', '.join(unresolved)}")
    return text.encode()


def _load_state(target: Path) -> dict[str, Any]:
    state_path = target / STATE_NAME
    if not state_path.exists():
        return {"schema_version": 1, "files": {}}
    value = _load_json(state_path)
    if value.get("schema_version") != 1 or not isinstance(value.get("files"), dict):
        raise ValueError(f"unsupported bootstrap state: {state_path}")
    return value


def _plan(
    target: Path,
    descriptor: dict[str, Any],
    state: dict[str, Any],
    values: dict[str, str],
) -> tuple[list[PlannedFile], list[str]]:
    prior_files = state.get("files", {})
    planned: list[PlannedFile] = []
    conflicts: list[str] = []

    for item in descriptor["files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("each template file must declare a string path")
        relative = _safe_relative(item["path"])
        source = TEMPLATE_ROOT / relative
        if not source.is_file():
            raise ValueError(f"template file is missing: {source}")
        mode = int(str(item.get("mode", "0644")), 8)
        content = _render(source, values)
        desired_hash = _digest(content)
        destination = target / relative
        prior = prior_files.get(relative.as_posix(), {})
        old_hash = prior.get("installed_hash") if isinstance(prior, dict) else None

        if not destination.exists():
            action = "create"
            installed_hash = desired_hash
        elif not destination.is_file():
            conflicts.append(f"{relative}: destination is not a regular file")
            continue
        else:
            current_hash = _digest(destination.read_bytes())
            if current_hash == desired_hash:
                action = "unchanged"
                installed_hash = desired_hash
            elif old_hash and current_hash == old_hash:
                action = "update"
                installed_hash = desired_hash
            elif old_hash and desired_hash == old_hash:
                action = "customized"
                installed_hash = old_hash
            else:
                conflicts.append(f"{relative}: existing content is not owned by this template")
                continue

        planned.append(
            PlannedFile(
                relative=relative,
                content=content,
                mode=mode,
                action=action,
                installed_hash=installed_hash,
            )
        )

    return planned, conflicts


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _apply(
    target: Path,
    descriptor: dict[str, Any],
    planned: list[PlannedFile],
    values: dict[str, str],
) -> None:
    for item in planned:
        if item.action in {"create", "update"}:
            _atomic_write(target / item.relative, item.content, item.mode)
        elif item.action == "unchanged":
            current_mode = stat.S_IMODE((target / item.relative).stat().st_mode)
            if current_mode != item.mode:
                os.chmod(target / item.relative, item.mode)

    state = {
        "schema_version": 1,
        "template_version": descriptor.get("template_version", 1),
        "project_name": values["PROJECT_NAME"],
        "default_branch": values["DEFAULT_BRANCH"],
        "check_command": values["CHECK_COMMAND"],
        "files": {
            item.relative.as_posix(): {"installed_hash": item.installed_hash} for item in planned
        },
    }
    payload = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode()
    _atomic_write(target / STATE_NAME, payload, 0o644)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="existing Git repository to initialize")
    parser.add_argument("--project-name", help="project name used in generated documents")
    parser.add_argument("--default-branch", default="main")
    parser.add_argument(
        "--check-command",
        default="printf '%s\\n' 'Configure CHECK_COMMAND' >&2; exit 2",
        help="command used by the generated Makefile check target",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write safe changes; the default only previews them",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    target = args.target.expanduser().resolve()
    if not target.is_dir() or not (target / ".git").exists():
        print(f"Target is not an existing Git repository: {target}", file=sys.stderr)
        return 2

    values = {
        "PROJECT_NAME": args.project_name or target.name,
        "DEFAULT_BRANCH": args.default_branch,
        "CHECK_COMMAND": args.check_command,
    }

    try:
        descriptor = _descriptor()
        state = _load_state(target)
        planned, conflicts = _plan(target, descriptor, state, values)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for item in planned:
        print(f"{item.action:10} {item.relative}")
    for conflict in conflicts:
        print(f"conflict   {conflict}", file=sys.stderr)

    if conflicts:
        print("No files were written. Resolve conflicts and rerun.", file=sys.stderr)
        return 2
    if not args.apply:
        print("Preview only. Rerun with --apply to write these changes.")
        return 0

    _apply(target, descriptor, planned, values)
    print(f"Compound-engineering starter installed in {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
