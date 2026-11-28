# ./xtrshow/gitcommit.py
# License: Apache-2.0 (disclaimer at bottom of file)
"""
Git support for `xtrpatch --git-commit`.

Imported lazily by repatch.main, and only when a git flag is given, so
xtrpatch without those flags never looks at git and repatch.py still runs
where this module is absent (the web demo vendors repatch.py on its own).

The shape of a run:

    1. prepare()  every check that can fail, before one file is written
    2. the patch (or revert) runs
    3. the files it changed, and only those, are staged and committed
    4. anything stashed in step 1 comes back

Step 1 is where the user's uncommitted work is protected. A file the patch
touches that already has changes cannot be committed "just the patch": git
would take the whole file. So the run stops unless the user allows that
(--git-allow-dirty) or agrees to have those changes stashed around the
commit.
"""
import os
import shutil
import subprocess
import sys

DEFAULT_PREFIX = "[xtrpatch] "
ON_ERROR_CHOICES = ("ask", "commit", "skip")

# What a block's status has to be to count, mirrored from repatch so this
# module does not import it (repatch imports us).
_APPLIED = "APPLIED"
_FAILURES = frozenset({"FAILED", "BLOCKED", "CONFLICT", "EMPTY_SEARCH"})

# Files git leaves in its directory while an operation is half done.
_IN_PROGRESS = (
    ("MERGE_HEAD", "merge"),
    ("CHERRY_PICK_HEAD", "cherry-pick"),
    ("REVERT_HEAD", "revert"),
    ("rebase-merge", "rebase"),
    ("rebase-apply", "rebase"),
)


class GitError(Exception):
    """A reason not to start. Raised only before anything is written."""


def is_interactive():
    """Whether there is someone to answer a prompt."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def confirm(question):
    """Ask a yes/no question. Anything but y/yes, including EOF, is no."""
    try:
        answer = input(f"{question} [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in ("y", "yes")


def _first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _one_line(text):
    return " ".join(str(text).split())


def build_message(prefix, committed, not_applied, revert=False):
    """
    Build the commit message.

    `committed` and `not_applied` are lists of (display_path, items), items
    being the per-block results from apply_changes / revert_file.

        [xtrpatch] Add timeout to foo (+2 more)

        a.py
          - Add timeout to foo
          - Default msg param on bar
        b.py
          - Set x to 2

    The subject is the first comment the patch author wrote, with a count of
    the rest. Labels xtrpatch made up ("Delete file", "CHMOD +x") are listed
    under their file but never used as the subject: "[xtrpatch] Delete file"
    says less than "[xtrpatch] Patch old.py". Blocks that failed are listed
    separately so a partial commit does not claim work it did not do.
    """
    comments = [
        _one_line(item["label"])
        for _, items in committed
        for item in items
        if item["status"] == _APPLIED and item["label"] and not item["auto"]
    ]
    verb = "Revert" if revert else "Patch"
    if comments:
        subject = comments[0]
        if len(comments) > 1:
            subject += f" (+{len(comments) - 1} more)"
        if revert:
            subject = f"Revert: {subject}"
    elif len(committed) == 1:
        subject = f"{verb} {committed[0][0]}"
    else:
        subject = f"{verb} {len(committed)} files"

    lines = [f"{prefix}{subject}", ""]
    for path, items in committed:
        lines.append(path)
        for item in items:
            if item["status"] == _APPLIED and item["label"]:
                lines.append(f"  - {_one_line(item['label'])}")

    failed = [
        (path, [i for i in items if i["status"] in _FAILURES])
        for path, items in not_applied
    ]
    failed = [(path, items) for path, items in failed if items]
    if failed:
        lines += ["", "Not reverted:" if revert else "Not applied:"]
        for path, items in failed:
            lines.append(path)
            for item in items:
                if item["label"]:
                    lines.append(f"  - {_one_line(item['label'])}")
    return "\n".join(lines) + "\n"


class GitCommit:
    """One `--git-commit` run. Use run(); the rest is its steps."""

    def __init__(self, prefix=None, allow_dirty=False, on_error=None):
        self.prefix = DEFAULT_PREFIX if prefix is None else prefix
        self.allow_dirty = allow_dirty
        self.on_error = on_error or "ask"
        self.top = None
        self._stash = None  # commit id of the stash entry we made
        self._stashed = []  # root-relative paths in it
        self._staged = False  # True once the commit step staged anything

    # --- plumbing --------------------------------------------------------

    def _git(self, *args, literal=True, **kwargs):
        env = dict(os.environ)
        if literal:
            # Paths come from a patch file. Never let git read `[ab].py` or
            # `*.py` in one as a pattern.
            env["GIT_LITERAL_PATHSPECS"] = "1"
        return subprocess.run(
            ["git"] + list(args),
            cwd=self.top,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )

    def _rel(self, path):
        """
        `path` relative to the repository root, '/'-separated, or None when
        it lies outside. Only the directory part is resolved, so a symlink
        is treated as the link git tracks rather than as its target.
        """
        full = os.path.abspath(path)
        full = os.path.join(
            os.path.realpath(os.path.dirname(full)), os.path.basename(full)
        )
        try:
            rel = os.path.relpath(full, self.top)
        except ValueError:  # another drive on Windows
            return None
        if rel == os.pardir or rel.startswith(os.pardir + os.sep) or rel == ".":
            return None
        return rel.replace(os.sep, "/")

    # --- step 1: checks --------------------------------------------------

    def prepare(self, paths):
        """
        Run every check that should stop the run before a file is written.
        Raises GitError with the reason. May stash, if the user agrees to.
        """
        if shutil.which("git") is None:
            raise GitError("git is not installed, or not on PATH.")

        inside = self._git("rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            raise GitError("not inside a git repository.")
        top = self._git("rev-parse", "--show-toplevel")
        if top.returncode != 0 or not top.stdout.strip():
            raise GitError("could not find the root of this git repository.")
        self.top = os.path.realpath(top.stdout.strip())

        for name, what in _IN_PROGRESS:
            marker = self._git("rev-parse", "--git-path", name).stdout.strip()
            if marker and os.path.exists(os.path.join(self.top, marker)):
                raise GitError(f"a {what} is in progress. Finish or abort it first.")
        if self._git("ls-files", "--unmerged").stdout.strip():
            raise GitError("there are unresolved merge conflicts. Resolve them first.")

        for who in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
            ident = self._git("var", who)
            if ident.returncode != 0:
                raise GitError(
                    "git does not know who you are, so it could not commit. "
                    "Set user.name and user.email first."
                    + (f"\n  {_first_line(ident.stderr)}" if ident.stderr else "")
                )

        if self.allow_dirty:
            return
        rels = [r for r in (self._rel(p) for p in paths) if r]
        dirty = self._dirty(rels)
        if not dirty:
            return

        print("Found uncommitted changes:")
        for rel, untracked in dirty:
            print(f"  {rel}" + (" (untracked)" if untracked else ""))
        print()

        if any(untracked for _, untracked in dirty):
            raise GitError(
                "untracked files cannot be stashed and then patched. Commit "
                "them first, or pass --git-allow-dirty to commit them whole."
            )
        if self._git("diff", "--cached", "--quiet").returncode != 0:
            raise GitError(
                "there are staged changes already, so stashing is not safe. "
                "Commit or unstage them, or pass --git-allow-dirty."
            )
        if not is_interactive():
            raise GitError(
                "no terminal to ask on. Commit or stash those changes, or "
                "pass --git-allow-dirty to commit them along with the patch."
            )
        if not confirm("Stash and commit?"):
            raise GitError("stopped at your request.")
        self._stash_push([rel for rel, _ in dirty])

    def _dirty(self, rels):
        """[(path, is_untracked)] for the given paths that differ from HEAD."""
        if not rels:
            return []
        status = self._git(
            "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *rels
        )
        if status.returncode != 0:
            raise GitError(f"git status failed: {_first_line(status.stderr)}")
        wanted = set(rels)
        found = {}
        fields = status.stdout.split("\0")
        i = 0
        while i < len(fields):
            entry = fields[i]
            i += 1
            if len(entry) < 4:
                continue
            code, name = entry[:2], entry[3:]
            names = [name]
            if code[0] in "RC" or code[1] in "RC":
                # Renames and copies carry their source as the next field.
                if i < len(fields):
                    names.append(fields[i])
                i += 1
            for n in names:
                if n in wanted:
                    found[n] = code == "??"
        return [(rel, found[rel]) for rel in rels if rel in found]

    def _stash_ref(self):
        ref = self._git("rev-parse", "-q", "--verify", "refs/stash")
        return ref.stdout.strip() if ref.returncode == 0 else None

    def _stash_push(self, rels):
        before = self._stash_ref()
        push = self._git(
            "stash", "push", "-q", "-m", "xtrpatch --git-commit", "--", *rels
        )
        after = self._stash_ref()
        if push.returncode != 0 or after is None or after == before:
            raise GitError(
                "git stash did not save those changes: "
                + (_first_line(push.stderr) or "nothing was stashed")
            )
        self._stash, self._stashed = after, list(rels)
        print("Stashed.")

    # --- step 3: commit --------------------------------------------------

    def _commit(self, results, revert):
        """Stage and commit what changed. Returns True unless it went wrong."""
        failed = any(
            item["status"] in _FAILURES for r in results for item in r["items"]
        )
        candidates = []
        for result in results:
            if not any(i["status"] == _APPLIED for i in result["items"]):
                continue
            rel = self._rel(result["path"])
            if rel is None:
                print(
                    f"  ⚠️  {result['path']} is outside this repository. "
                    "Not committed."
                )
                continue
            candidates.append((rel, result))

        if not candidates:
            print("Nothing to commit.")
            return not failed

        if failed and not self._commit_despite_errors(revert):
            return False

        staged = []
        for rel, result in candidates:
            add = self._git("add", "-A", "--", rel)
            if add.returncode == 0:
                staged.append((rel, result))
                continue
            # check-ignore takes plain paths and rejects the literal setting.
            ignored = self._git("check-ignore", "-q", "--", rel, literal=False)
            if ignored.returncode == 0:
                reason = "is ignored by git"
            elif "did not match" in add.stderr:
                reason = "is not tracked by git"
            else:
                reason = f"could not be staged ({_first_line(add.stderr)})"
            print(f"  ⚠️  {rel} {reason}. Not committed.")
        self._staged = bool(staged)

        changed = set()
        if staged:
            diff = self._git(
                "diff", "--cached", "--name-only", "--no-renames", "-z", "--",
                *[rel for rel, _ in staged]
            )
            changed = set(n for n in diff.stdout.split("\0") if n)
        staged = [(rel, result) for rel, result in staged if rel in changed]
        if not staged:
            print("Nothing to commit.")
            return not failed

        message = build_message(
            self.prefix,
            [(rel, result["items"]) for rel, result in staged],
            [(self._rel(r["path"]) or r["path"], r["items"]) for r in results],
            revert=revert,
        )
        commit = self._git(
            "commit", "-q", "-F", "-", "--", *[rel for rel, _ in staged],
            input=message,
        )
        if commit.returncode != 0:
            output = (commit.stdout + commit.stderr).strip()
            if output:
                print(output)
            print(
                "❌ git commit failed. The changes are applied and staged, "
                "but not committed."
            )
            return False

        sha = self._git("rev-parse", "--short", "HEAD").stdout.strip()
        branch = self._git("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
        where = f"on {branch}" if branch else "on a detached HEAD"
        print(f"📦 Committed {sha} {where}: {message.splitlines()[0]}")
        return True

    def _commit_despite_errors(self, revert):
        what = "Some files could not be reverted" if revert else "Some changes failed to apply"
        if self.on_error == "commit":
            return True
        if self.on_error == "skip":
            print(f"{what}. Not committing (--git-on-error skip).")
            return False
        if not is_interactive():
            print(
                f"{what}, and there is no terminal to ask on. Not committing. "
                "Pass --git-on-error commit to commit anyway."
            )
            return False
        if confirm(f"{what}. Commit the rest?"):
            return True
        print("Not committing.")
        return False

    # --- step 4: give the stash back -------------------------------------

    def _restore(self):
        """Pop the stash made in prepare(). Returns True unless it went wrong."""
        if not self._stash:
            return True
        stash, self._stash = self._stash, None

        # Pop merges onto the index and refuses if the working tree differs
        # from it. After a commit the two agree. Without one (the user said
        # no, a hunk failed, the patch raised) the patched files are still
        # unstaged, so stage them for the pop and unstage them after. That
        # is safe to undo: prepare() refused to stash over a non-empty index.
        staged_here = not self._staged
        if staged_here:
            self._git("add", "-A", "--", *self._stashed)

        listing = self._git("stash", "list", "--format=%H").stdout.split()
        if stash not in listing:
            print(
                "  ⚠️  The stash xtrpatch made is gone. Look for your "
                f"uncommitted changes with: git stash list (commit {stash[:12]})"
            )
            return False
        pop = self._git("stash", "pop", "-q", f"stash@{{{listing.index(stash)}}}")
        if pop.returncode != 0:
            output = (pop.stdout + pop.stderr).strip()
            if output:
                print(output)
            print(
                "  ⚠️  Your uncommitted changes could not be put back cleanly. "
                "They are still in the stash: fix any conflict markers, then "
                "run `git stash drop`."
            )
            return False
        if staged_here:
            self._git("reset", "-q", "--", *self._stashed)
        print("Uncommitted changes restored.")
        return True

    # --- the whole run ---------------------------------------------------

    def run(self, paths, action, revert=False):
        """
        Check, run `action` (which patches or reverts and returns results),
        commit, and restore. Returns the process exit code.

        GitError from the checks propagates: nothing was written. Past that
        point the stash is restored whatever happens, including when
        `action` raises.
        """
        self.prepare(paths)
        ok = False
        try:
            results = action()
            ok = self._commit(results, revert)
        finally:
            restored = self._restore()
        return 0 if ok and restored else 1


# Copyright Michael Godfrey 2026 | aloecraft.org <michael@aloecraft.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
