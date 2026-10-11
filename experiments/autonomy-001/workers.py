"""OPENLINE-AUTONOMY-001 workers: model-neutral adapter interface + scripted workers.

The adapter interface is deliberately small so that real coding-agent CLIs
(Airlock provider dicts: {command, pass_env, timeout_seconds}) can satisfy
it without modification. Phase 1 demonstrates the controller loop with
deterministic scripted workers; the interface is what makes workers
replaceable, and the worker-swap test proves the controller does not
depend on which worker built a change.

Authority boundary (enforced here, first layer): a worker may only modify
files inside its assigned workdir AND inside the task's declared scope.
Anything else — path traversal, absolute paths, or targets outside scope —
is refused BEFORE any file is touched, and attempts against governing
paths are flagged RULE_MODIFICATION_ATTEMPT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class BuildResult:
    ok: bool
    worker_id: str
    task_id: str
    files_changed: list = field(default_factory=list)
    lines_changed: int = 0
    notes: str = ""
    violation: str | None = None  # None | "OUT_OF_SCOPE" | "RULE_MODIFICATION_ATTEMPT"


class WorkerAdapter(Protocol):
    worker_id: str

    def build(self, task: dict, workdir: Path) -> BuildResult:
        """Apply the task's change inside workdir. Never evaluate."""
        ...


def _resolve_in_scope(workdir: Path, scope_paths: list[str],
                      rel: str) -> Path | None:
    """Resolve rel inside workdir; return None if it escapes."""
    if rel.startswith("/") or ".." in Path(rel).parts:
        return None
    target = (workdir / rel).resolve()
    try:
        target.relative_to(workdir.resolve())
    except ValueError:
        return None
    # Must also fall under one of the task's scope paths.
    if not any(str(target.relative_to(workdir.resolve())).startswith(s)
               for s in scope_paths):
        return None
    return target


def _looks_like_governing_path(rel: str, protected_paths: list[str]) -> bool:
    """Does this out-of-worktree path name a governing file?

    The worker's relative path cannot name the coordinator's absolute
    location, so this is intent-based: any path that already escaped the
    work area AND names a protected file/dir is treated as an attempt on
    the governing rules. Basenames are derived from the mission's own
    protected list so the check tracks it.
    """
    n = rel.replace("\\", "/").lower()
    basenames = {p.strip("/").split("/")[-1].lower() or
                 p.strip("/").split("/")[-2].lower()
                 for p in protected_paths}
    return any(b and b in n for b in basenames)


class ScriptedWorker:
    """Deterministic worker: applies the task's declared patch list.

    Stands in for an agent worker. The controller loop, evaluation, and
    decisions are identical regardless of which worker built the change —
    that is what the worker-replacement test establishes.
    """

    def __init__(self, worker_id: str):
        self.worker_id = worker_id

    def build(self, task: dict, workdir: Path,
              scope_paths: list[str], protected_paths: list[str]) -> BuildResult:
        changed, lines = [], 0
        for edit in task.get("patch", []):
            rel = edit["file"]
            target = _resolve_in_scope(workdir, scope_paths, rel)
            if target is None:
                violation = ("RULE_MODIFICATION_ATTEMPT"
                             if _looks_like_governing_path(
                                 rel, protected_paths)
                             else "OUT_OF_SCOPE")
                return BuildResult(
                    ok=False, worker_id=self.worker_id, task_id=task["id"],
                    notes=f"refused: {rel} escapes the assigned work area",
                    violation=violation)
            if not target.exists():
                return BuildResult(
                    ok=False, worker_id=self.worker_id, task_id=task["id"],
                    notes=f"refused: {rel} does not exist in work area",
                    violation="OUT_OF_SCOPE")
            text = target.read_text()
            if text.count(edit["old"]) != 1:
                return BuildResult(
                    ok=False, worker_id=self.worker_id, task_id=task["id"],
                    notes=f"refused: anchor not found exactly once in {rel}",
                    violation="OUT_OF_SCOPE")
            target.write_text(text.replace(edit["old"], edit["new"]))
            changed.append(rel)
            lines += edit["new"].count("\n") - edit["old"].count("\n")
        return BuildResult(ok=True, worker_id=self.worker_id,
                           task_id=task["id"], files_changed=changed,
                           lines_changed=abs(lines),
                           notes=f"applied {len(changed)} edit(s)")
