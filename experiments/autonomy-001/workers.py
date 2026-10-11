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

    def build(self, task: dict, workdir: Path,
              scope_paths: list[str], protected_paths: list[str]) -> BuildResult:
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
    if not any((target.relative_to(workdir.resolve()).as_posix() == s.rstrip("/") or
                target.relative_to(workdir.resolve()).as_posix().startswith(s.rstrip("/") + "/"))
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
            protected = any(rel == p.rstrip('/') or
                            rel.startswith(p.rstrip('/') + '/') for p in protected_paths)
            if protected:
                return BuildResult(False, self.worker_id, task['id'],
                    notes=f'refused: {rel} is a governing path',
                    violation='RULE_MODIFICATION_ATTEMPT')
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


class AirlockWorker:
    """Use existing Airlock provider argv behind its secretless Docker runner.

    Only offline commands installed in the pinned image can work. Ambient
    credentials, host CLI state, network access and paid API routes are absent.
    No implicit host execution when a provider is unavailable in the image.
    """
    def __init__(self, worker_id, provider):
        self.worker_id = worker_id
        self.provider = provider
        if provider.get('pass_env'):
            raise ValueError('credential forwarding is not authorized')

    def build(self, task, workdir, scope_paths, protected_paths):
        import io
        import subprocess
        import tarfile
        import tempfile
        import integrations as IN
        from airlock.util import expand
        with tempfile.TemporaryDirectory(prefix='autonomy-worker-') as temp:
            root = Path(temp)
            raw = subprocess.run(['git', 'archive', 'HEAD', *scope_paths],
                cwd=workdir, capture_output=True, check=True).stdout
            with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
                archive.extractall(root, filter='data')
            # Remove governing files and protected tests from worker visibility.
            import shutil
            for rel in protected_paths:
                path = root / rel
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.exists():
                    path.unlink()
            before = {p.relative_to(root).as_posix(): p.read_bytes()
                      for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
            argv = expand(self.provider['command'], {'prompt': task['description']})
            result = IN.isolated_run(root, argv, timeout=120)
            if result['exit_code'] or result['timed_out']:
                return BuildResult(False, self.worker_id, task['id'],
                    notes='isolated provider failed: ' + result['stderr_tail'])
            paths = {p.relative_to(root).as_posix(): p for p in root.rglob('*')
                     if p.is_file() or p.is_symlink()}
            if set(paths) != set(before) or any(p.is_symlink() for p in paths.values()):
                return BuildResult(False, self.worker_id, task['id'],
                    notes='new/deleted/symlink files require owner review', violation='OUT_OF_SCOPE')
            changes = {rel: p.read_bytes() for rel, p in paths.items()
                       if p.read_bytes() != before[rel]}
            # Validate the entire output before any host copy.
            if any(_resolve_in_scope(workdir, scope_paths, rel) is None or
                   any(rel == x.rstrip('/') or rel.startswith(x.rstrip('/') + '/')
                       for x in protected_paths) for rel in changes):
                return BuildResult(False, self.worker_id, task['id'],
                    notes='protected output refused', violation='RULE_MODIFICATION_ATTEMPT')
            for rel, data in changes.items():
                (workdir / rel).write_bytes(data)
            return BuildResult(True, self.worker_id, task['id'], list(changes),
                               notes='isolated Airlock provider output; improvement unknown')
