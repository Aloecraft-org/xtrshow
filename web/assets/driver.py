"""
Browser driver for the xtrshow live demo.

Thin adapter only: every patching decision is made by the real, unmodified
``xtrshow.repatch`` module vendored under /vendor. This file just prepares a
working directory in Pyodide's in-memory filesystem, captures stdout, and hands
results back to JavaScript as JSON.
"""

import contextlib
import io
import json
import os
import shutil
from pathlib import Path

import xtrshow.repatch as rp
from xtrshow import get_version

ROOT = Path("/demo")


def _workdir(scenario):
    return ROOT / scenario


def reset(scenario, files_json):
    """Wipe and rebuild a scenario's working directory from its seed files."""
    files = json.loads(files_json)
    wd = _workdir(scenario)
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = wd / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return json.dumps({"ok": True})


def _tree(wd):
    """Render the .xtrpatch backup tree, so the safety net is visible."""
    xp = wd / ".xtrpatch"
    if not xp.exists():
        return "(no backups yet — .xtrpatch/ is created on first apply)"
    rows = []
    for p in sorted(xp.rglob("*")):
        if p.is_file():
            rel = p.relative_to(wd)
            size = p.stat().st_size
            rows.append(f"{str(rel):<46} {size:>7} B")
    return "\n".join(rows) if rows else "(empty)"


def _snapshot(wd):
    """Current on-disk state of every non-backup file in the workdir."""
    out = {}
    for p in sorted(wd.rglob("*")):
        if p.is_file() and ".xtrpatch" not in p.parts:
            try:
                out[str(p.relative_to(wd))] = p.read_text()
            except UnicodeDecodeError:
                pass
    return out


def apply_patch(scenario, src_name, src_text, patch_text):
    """
    Write the editor's current buffer to disk, then run the real apply_changes.

    The patch is written to disk too, so xtrpatch archives it next to the
    backup exactly as the CLI does.
    """
    wd = _workdir(scenario)
    wd.mkdir(parents=True, exist_ok=True)

    target = wd / src_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(src_text)

    patch_path = wd / "changes.txt"
    patch_path.write_text(patch_text)

    cwd = os.getcwd()
    buf = io.StringIO()
    error = None
    try:
        os.chdir(wd)
        changes = rp.parse_multi_file_patch(patch_text)
        if not changes:
            return json.dumps(
                {
                    "report": "No valid blocks found in patch file.",
                    "files": _snapshot(wd),
                    "tree": _tree(wd),
                }
            )
        with contextlib.redirect_stdout(buf):
            rp.apply_changes(changes, patch_source_path="changes.txt")
    except Exception as exc:  # surfaced in the terminal pane, never swallowed
        error = f"{type(exc).__name__}: {exc}"
    finally:
        os.chdir(cwd)

    report = buf.getvalue().rstrip()
    if error:
        report = (report + "\n" if report else "") + f"! Demo driver error: {error}"

    return json.dumps(
        {
            "report": report or "(no output)",
            "files": _snapshot(wd),
            "tree": _tree(wd),
        }
    )


def revert(scenario, src_name):
    """Run the real revert_file() against the scenario's backups."""
    wd = _workdir(scenario)
    cwd = os.getcwd()
    buf = io.StringIO()
    try:
        os.chdir(wd)
        with contextlib.redirect_stdout(buf):
            rp.revert_file(src_name)
    finally:
        os.chdir(cwd)

    return json.dumps(
        {
            "report": buf.getvalue().rstrip() or "(no output)",
            "files": _snapshot(wd),
            "tree": _tree(wd),
        }
    )


def version():
    return get_version()
