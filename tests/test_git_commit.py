# ./tests/test_git_commit.py
# License: Apache-2.0 (disclaimer at bottom of file)
"""
`xtrpatch --git-commit`, exercised against real repositories.

Nothing here mocks git. Each test builds a throwaway repository, runs
xtrpatch's real entry point in it, and then asks git what happened. The only
things faked are the terminal (is there one, and what was typed) and, for a
few tests, a failure injected at one step.
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from xtrshow import gitcommit, repatch
from xtrshow.gitcommit import build_message
from xtrshow.repatch import apply_changes, parse_multi_file_patch, revert_file

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

REPO_ROOT = Path(__file__).resolve().parent.parent

A_PY = "def foo():\n    pass\n\n\ndef bar(msg):\n    return msg\n\n\nx = 1\n"

PATCH_FOO = """--- a/a.py
@ Add timeout to foo
<<<<
def foo():
====
def foo(timeout=30):
>>>>
"""

PATCH_X = """--- a/a.py
@ Set x to 2
<<<<
x = 1
====
x = 2
>>>>
"""

# One hunk that applies and one that cannot.
PATCH_PARTIAL = PATCH_FOO + """
--- a/a.py
@ Rename handler
<<<<
def handler():
====
def handle():
>>>>
"""


# --- fixtures and helpers ------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_git(tmp_path_factory, monkeypatch):
    """Keep the developer's and the CI runner's git configuration out."""
    home = tmp_path_factory.mktemp("home")
    empty = home / "gitconfig"
    empty.write_text("")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in list(os.environ):
        if var.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_")) or var == "EMAIL":
            monkeypatch.delenv(var)
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)


def git(*args, cwd=None, check=True):
    done = subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
    )
    if check and done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed:\n{done.stdout}")
    return done.stdout


def init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", "main", cwd=path)
    git("config", "user.name", "Test User", cwd=path)
    git("config", "user.email", "test@example.com", cwd=path)
    git("config", "commit.gpgsign", "false", cwd=path)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repository with a.py committed, and the cwd inside it."""
    d = tmp_path / "repo"
    init_repo(d)
    (d / "a.py").write_text(A_PY)
    git("add", "a.py", cwd=d)
    git("commit", "-qm", "init", cwd=d)
    monkeypatch.chdir(d)
    return d


@pytest.fixture
def tty(monkeypatch):
    """
    Pretend a terminal is attached and script what gets typed at it.

        tty("y")          one prompt, answered yes
        tty("y", "n")     two prompts
        tty()             a terminal where any prompt is a test failure

    Returns the list of prompts shown.
    """

    def install(*answers):
        pending = list(answers)
        asked = []

        def fake_input(prompt=""):
            asked.append(prompt)
            if not pending:
                raise AssertionError(f"unexpected prompt: {prompt!r}")
            return pending.pop(0)

        monkeypatch.setattr(gitcommit, "is_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", fake_input)
        return asked

    return install


@pytest.fixture(autouse=True)
def no_tty(monkeypatch):
    """By default there is no terminal, and prompting is a failure."""

    def refuse(prompt=""):
        raise AssertionError(f"prompted without a terminal: {prompt!r}")

    monkeypatch.setattr(gitcommit, "is_interactive", lambda: False)
    monkeypatch.setattr("builtins.input", refuse)


def xtrpatch(monkeypatch, capsys, *argv):
    """Run xtrpatch's main(). Returns (exit code, everything it printed)."""
    monkeypatch.setattr(sys, "argv", ["xtrpatch"] + [str(a) for a in argv])
    capsys.readouterr()
    with pytest.raises(SystemExit) as exit_info:
        repatch.main()
    captured = capsys.readouterr()
    code = exit_info.value.code
    return (0 if code is None else code), captured.out + captured.err


@pytest.fixture
def run(monkeypatch, capsys):
    def _run(*argv):
        return xtrpatch(monkeypatch, capsys, *argv)

    return _run


def write_patch(text, name="p.patch"):
    Path(name).write_text(text)
    return name


def commit_count(cwd=None):
    out = git("rev-list", "--count", "HEAD", cwd=cwd, check=False)
    return int(out) if out.strip().isdigit() else 0


def last_message(cwd=None):
    return git("log", "-1", "--format=%B", cwd=cwd).rstrip("\n")


def last_files(cwd=None):
    """Paths in the last commit, as 'STATUS path' lines."""
    out = git(
        "show", "--no-renames", "--name-status", "--format=", "HEAD", cwd=cwd
    )
    return sorted(" ".join(line.split("\t")) for line in out.splitlines() if line)


def status(cwd=None):
    """Porcelain status lines, minus xtrpatch's own state and patch files."""
    out = git("status", "--porcelain", "--untracked-files=all", cwd=cwd)
    return [
        line
        for line in out.splitlines()
        if ".xtr/" not in line and not line.endswith(".patch")
    ]


def stash_list(cwd=None):
    return git("stash", "list", cwd=cwd).splitlines()


def staged(cwd=None):
    return git("diff", "--cached", "--name-only", cwd=cwd).split()


# --- flags ---------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        ["-gmp", "[x] "],
        ["--git-msg-prefix", "[x] "],
        ["--git-allow-dirty"],
        ["--git-on-error", "commit"],
    ],
)
def test_git_flags_need_git_commit(repo, run, extra):
    code, out = run(write_patch(PATCH_FOO), *extra)
    assert code == 2
    assert "needs -gc/--git-commit" in out
    assert (repo / "a.py").read_text() == A_PY


def test_git_on_error_rejects_unknown_choice(repo, run):
    code, out = run("-gc", "--git-on-error", "maybe", write_patch(PATCH_FOO))
    assert code == 2
    assert (repo / "a.py").read_text() == A_PY


@pytest.mark.parametrize("flag", ["-gc", "--git-commit"])
@pytest.mark.parametrize("flag_first", [True, False])
def test_flag_spellings_and_position(repo, run, flag, flag_first):
    patch = write_patch(PATCH_FOO)
    code, out = run(*([flag, patch] if flag_first else [patch, flag]))
    assert code == 0, out
    assert commit_count() == 2


def test_without_the_flag_git_is_never_run(tmp_path, monkeypatch, run):
    """Plain xtrpatch must not start caring whether git exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text(A_PY)

    def explode(*a, **k):
        raise AssertionError("git was run without --git-commit")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(shutil, "which", explode)
    code, out = run(write_patch(PATCH_FOO))
    assert code == 0
    assert "timeout=30" in (tmp_path / "a.py").read_text()


def test_without_the_flag_nothing_is_committed(repo, run):
    code, _ = run(write_patch(PATCH_FOO))
    assert code == 0
    assert commit_count() == 1
    assert status() == [" M a.py"]


def test_without_the_flag_failed_hunks_still_exit_zero(repo, run):
    """The exit code only changes meaning when a commit was asked for."""
    code, _ = run(write_patch(PATCH_PARTIAL))
    assert code == 0


# --- checks that run before anything is written ---------------------------


def test_not_a_repository(tmp_path, monkeypatch, run):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text(A_PY)
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert "not inside a git repository" in out
    assert "Nothing was applied." in out
    assert (tmp_path / "a.py").read_text() == A_PY
    assert not (tmp_path / ".xtr").exists()


def test_git_not_installed(repo, run, monkeypatch):
    monkeypatch.setattr(gitcommit.shutil, "which", lambda name: None)
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert "git is not installed" in out
    assert (repo / "a.py").read_text() == A_PY


def test_inside_the_git_directory_is_not_a_work_tree(repo, run, monkeypatch):
    monkeypatch.chdir(repo / ".git")
    Path("a.py").write_text(A_PY)
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert "not inside a git repository" in out
    assert Path("a.py").read_text() == A_PY


def test_no_commit_identity(repo, run):
    git("config", "--unset", "user.name")
    git("config", "--unset", "user.email")
    git("config", "user.useConfigOnly", "true")
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert "does not know who you are" in out
    assert "Nothing was applied." in out
    assert (repo / "a.py").read_text() == A_PY


def test_merge_in_progress(repo, run):
    git("checkout", "-qb", "other")
    (repo / "a.py").write_text(A_PY.replace("x = 1", "x = 100"))
    git("commit", "-qam", "other")
    git("checkout", "-q", "main")
    (repo / "a.py").write_text(A_PY.replace("x = 1", "x = 200"))
    git("commit", "-qam", "main")
    git("merge", "other", check=False)
    before = (repo / "a.py").read_text()
    assert "<<<<<<<" in before

    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert "merge is in progress" in out
    assert (repo / "a.py").read_text() == before


@pytest.mark.parametrize(
    "marker,is_dir,what",
    [
        ("CHERRY_PICK_HEAD", False, "cherry-pick"),
        ("REVERT_HEAD", False, "revert"),
        ("rebase-merge", True, "rebase"),
        ("rebase-apply", True, "rebase"),
    ],
)
def test_other_operations_in_progress(repo, run, marker, is_dir, what):
    path = repo / ".git" / marker
    if is_dir:
        path.mkdir()
    else:
        path.write_text(git("rev-parse", "HEAD"))
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert f"a {what} is in progress" in out
    assert (repo / "a.py").read_text() == A_PY


def test_in_progress_check_works_from_a_subdirectory(repo, run, monkeypatch):
    (repo / ".git" / "rebase-merge").mkdir()
    sub = repo / "sub"
    sub.mkdir()
    (sub / "s.py").write_text("x = 1\n")
    git("add", "sub/s.py")
    git("commit", "-qm", "sub")
    monkeypatch.chdir(sub)
    code, out = run("-gc", write_patch("--- a/s.py\n<<<<\nx = 1\n====\nx = 2\n>>>>\n"))
    assert code == 1
    assert "rebase is in progress" in out
    assert (sub / "s.py").read_text() == "x = 1\n"


def test_missing_patch_file_is_reported_before_git(tmp_path, monkeypatch, run):
    monkeypatch.chdir(tmp_path)
    code, out = run("-gc", "nope.patch")
    assert code == 1
    assert "not found" in out


# --- the commit ----------------------------------------------------------


def test_clean_commit(repo, run):
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 0, out
    assert commit_count() == 2
    assert last_message() == "[xtrpatch] Add timeout to foo\n\na.py\n  - Add timeout to foo"
    assert last_files() == ["M a.py"]
    assert "Committed" in out and "on main" in out
    assert status() == []
    assert "timeout=30" in git("show", "HEAD:a.py")


def test_state_and_patch_file_stay_out_of_the_commit(repo, run):
    """This repository has no .gitignore, so nothing hides .xtr/ for us."""
    run("-gc", write_patch(PATCH_FOO))
    tracked = git("ls-files").split()
    assert tracked == ["a.py"]
    assert (repo / ".xtr" / "backup" / "a.py.orig").exists()
    untracked = git("status", "--porcelain", "--untracked-files=all")
    assert "?? p.patch" in untracked
    assert "?? .xtr/" in untracked


def test_message_lists_every_file_and_comment(repo, run):
    (repo / "b.py").write_text("y = 1\n")
    (repo / "old.py").write_text("gone\n")
    git("add", ".")
    git("commit", "-qm", "more")
    patch = """--- a/a.py
@ Add timeout to foo
<<<<
def foo():
====
def foo(timeout=30):
>>>>

--- a/a.py
@ Default msg param on bar
<<<<
def bar(msg):
====
def bar(msg=None):
>>>>

--- a/b.py
@ Set y to 2
<<<<
y = 1
====
y = 2
>>>>

--- a/old.py
! DELETE FILE
"""
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert last_message() == (
        "[xtrpatch] Add timeout to foo (+2 more)\n"
        "\n"
        "a.py\n"
        "  - Add timeout to foo\n"
        "  - Default msg param on bar\n"
        "b.py\n"
        "  - Set y to 2\n"
        "old.py\n"
        "  - Delete file"
    )
    assert last_files() == ["D old.py", "M a.py", "M b.py"]


def test_message_without_comments_names_the_file(repo, run):
    code, _ = run("-gc", write_patch("--- a/a.py\n<<<<\nx = 1\n====\nx = 2\n>>>>\n"))
    assert code == 0
    assert last_message() == "[xtrpatch] Patch a.py\n\na.py"


def test_message_without_comments_counts_the_files(repo, run):
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "more")
    patch = (
        "--- a/a.py\n<<<<\nx = 1\n====\nx = 2\n>>>>\n"
        "--- a/b.py\n<<<<\ny = 1\n====\ny = 2\n>>>>\n"
    )
    code, _ = run("-gc", write_patch(patch))
    assert code == 0
    assert last_message() == "[xtrpatch] Patch 2 files\n\na.py\nb.py"


def test_uncommented_hunks_are_left_out_of_the_body(repo, run):
    patch = PATCH_FOO + "--- a/a.py\n<<<<\nx = 1\n====\nx = 2\n>>>>\n"
    run("-gc", write_patch(patch))
    assert last_message() == "[xtrpatch] Add timeout to foo\n\na.py\n  - Add timeout to foo"


def test_a_made_up_label_is_never_the_subject(repo, run):
    """'[xtrpatch] Delete file' would say less than naming the file."""
    code, _ = run("-gc", write_patch("--- a/a.py\n! DELETE FILE\n"))
    assert code == 0
    assert last_message() == "[xtrpatch] Patch a.py\n\na.py\n  - Delete file"
    assert last_files() == ["D a.py"]


def test_a_comment_on_a_delete_is_used(repo, run):
    run("-gc", write_patch("--- a/a.py\n@ Drop the legacy module\n! DELETE FILE\n"))
    assert last_message() == (
        "[xtrpatch] Drop the legacy module\n\na.py\n  - Drop the legacy module"
    )


@pytest.mark.parametrize(
    "flag,prefix,expected",
    [
        ("-gmp", "[bot] ", "[bot] Add timeout to foo"),
        ("--git-msg-prefix", "fix: ", "fix: Add timeout to foo"),
        ("-gmp", "", "Add timeout to foo"),
        ("-gmp", "no-space", "no-spaceAdd timeout to foo"),
    ],
)
def test_message_prefix(repo, run, flag, prefix, expected):
    code, out = run("-gc", flag, prefix, write_patch(PATCH_FOO))
    assert code == 0, out
    assert last_message().splitlines()[0] == expected


def test_prefix_can_start_with_a_dash(repo, run):
    code, out = run("-gc", "-gmp=- ", write_patch(PATCH_FOO))
    assert code == 0, out
    assert last_message().splitlines()[0] == "- Add timeout to foo"


def test_hash_lines_in_a_comment_survive(repo, run):
    """git strips '#' lines from an edited message. Ours is not edited."""
    patch = PATCH_FOO.replace("@ Add timeout to foo", "@ #123 add timeout")
    run("-gc", "-gmp", "", write_patch(patch))
    assert last_message() == "#123 add timeout\n\na.py\n  - #123 add timeout"


def test_create_file(repo, run):
    patch = "--- a/pkg/new.py\n@ Add the new module\n<<<<\n====\nprint(1)\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert last_files() == ["A pkg/new.py"]
    assert last_message() == (
        "[xtrpatch] Add the new module\n\npkg/new.py\n  - Add the new module"
    )


def test_create_file_without_a_comment(repo, run):
    run("-gc", write_patch("--- a/new.py\n<<<<\n====\nprint(1)\n>>>>\n"))
    assert last_message() == "[xtrpatch] Patch new.py\n\nnew.py\n  - Create file"


def test_rewrite_file(repo, run):
    patch = "--- a/a.py\n! DELETE FILE\n@ Start over\n<<<<\n====\nprint('new')\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert last_files() == ["M a.py"]
    assert git("show", "HEAD:a.py") == "print('new')\n"
    assert last_message() == "[xtrpatch] Start over\n\na.py\n  - Start over"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_chmod_is_committed(repo, run):
    code, out = run("-gc", write_patch("--- a/a.py\n! CHMOD +x\n"))
    assert code == 0, out
    assert git("ls-files", "-s", "a.py").startswith("100755")
    assert last_message() == "[xtrpatch] Patch a.py\n\na.py\n  - CHMOD +x"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_a_mode_change_git_cannot_see_is_nothing_to_commit(repo, run):
    """git records only the executable bit, so 600 is invisible to it."""
    code, out = run("-gc", write_patch("--- a/a.py\n! CHMOD 600\n"))
    assert code == 0, out
    assert "Nothing to commit." in out
    assert commit_count() == 1
    assert staged() == []


def test_reapplying_a_patch_commits_nothing(repo, run):
    patch = write_patch(PATCH_FOO)
    run("-gc", patch)
    code, out = run("-gc", patch)
    assert code == 0
    assert "Nothing to commit." in out
    assert commit_count() == 2


def test_target_override_form(repo, run):
    patch = write_patch("@ Set x to 2\n<<<<\nx = 1\n====\nx = 2\n>>>>\n")
    code, out = run("-gc", "a.py", patch)
    assert code == 0, out
    assert last_message() == "[xtrpatch] Set x to 2\n\na.py\n  - Set x to 2"


def test_from_a_subdirectory_paths_are_repository_relative(repo, run, monkeypatch):
    sub = repo / "pkg" / "inner"
    sub.mkdir(parents=True)
    (sub / "m.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-qm", "sub")
    monkeypatch.chdir(sub)
    patch = "--- a/m.py\n@ Bump x\n<<<<\nx = 1\n====\nx = 2\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert last_files() == ["M pkg/inner/m.py"]
    assert last_message() == "[xtrpatch] Bump x\n\npkg/inner/m.py\n  - Bump x"


def test_parent_relative_path(repo, run, monkeypatch):
    sub = repo / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)
    code, out = run("-gc", write_patch(PATCH_FOO.replace("a/a.py", "a/../a.py")))
    assert code == 0, out
    assert last_files() == ["M a.py"]


def test_absolute_path_inside_the_repository(repo, run):
    patch = f"--- {repo / 'a.py'}\n@ Set x to 2\n<<<<\nx = 1\n====\nx = 2\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert last_files() == ["M a.py"]
    assert last_message().splitlines()[2] == "a.py"


def test_target_outside_the_repository_is_skipped(repo, run, tmp_path):
    outside = tmp_path / "elsewhere.py"
    outside.write_text("z = 1\n")
    patch = PATCH_FOO + f"--- {outside}\n@ Bump z\n<<<<\nz = 1\n====\nz = 2\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert outside.read_text() == "z = 2\n"
    assert "outside this repository" in out
    assert last_files() == ["M a.py"]
    assert "Bump z" not in last_message()


def test_only_targets_outside_the_repository(repo, run, tmp_path):
    outside = tmp_path / "elsewhere.py"
    outside.write_text("z = 1\n")
    code, out = run("-gc", write_patch(f"--- {outside}\n<<<<\nz = 1\n====\nz = 2\n>>>>\n"))
    assert code == 0, out
    assert "Nothing to commit." in out
    assert commit_count() == 1


def test_ignored_target_is_skipped(repo, run):
    (repo / ".gitignore").write_text("secret.py\n")
    git("add", ".gitignore")
    git("commit", "-qm", "ignore")
    (repo / "secret.py").write_text("k = 1\n")
    patch = PATCH_FOO + "--- a/secret.py\n@ Rotate k\n<<<<\nk = 1\n====\nk = 2\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert (repo / "secret.py").read_text() == "k = 2\n"
    assert "secret.py is ignored by git" in out
    assert last_files() == ["M a.py"]
    assert "secret.py" not in git("ls-files")


def test_deleting_a_file_git_never_tracked(repo, run):
    (repo / ".gitignore").write_text("scratch.txt\n")
    git("add", ".gitignore")
    git("commit", "-qm", "ignore")
    (repo / "scratch.txt").write_text("tmp\n")
    code, out = run("-gc", write_patch("--- a/scratch.txt\n! DELETE FILE\n"))
    assert code == 0, out
    assert not (repo / "scratch.txt").exists()
    assert "Nothing to commit." in out
    assert commit_count() == 2


def test_unrelated_changes_are_left_alone(repo, run):
    (repo / "b.py").write_text("y = 1\n")
    (repo / "c.py").write_text("c = 1\n")
    git("add", ".")
    git("commit", "-qm", "more")
    (repo / "b.py").write_text("y = 99\n")  # unstaged edit
    (repo / "c.py").write_text("c = 99\n")
    git("add", "c.py")  # staged edit
    (repo / "notes.txt").write_text("mine\n")  # untracked

    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 0, out
    assert last_files() == ["M a.py"]
    assert status() == [" M b.py", "M  c.py", "?? notes.txt"]
    assert staged() == ["c.py"]
    assert git("show", "HEAD:c.py") == "c = 1\n"


def test_glob_characters_in_a_path_are_literal(repo, run):
    """`[ab].py` must not sweep a.py and b.py into the commit."""
    (repo / "[ab].py").write_text("g = 1\n")
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "more")
    (repo / "b.py").write_text("y = 99\n")
    patch = "--- a/[ab].py\n@ Bump g\n<<<<\ng = 1\n====\ng = 2\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert last_files() == ["M [ab].py"]
    assert status() == [" M b.py"]


def test_glob_characters_survive_the_stash_round_trip(repo, run, tty):
    (repo / "[ab].py").write_text("g = 1\nh = 1\n")
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "more")
    (repo / "[ab].py").write_text("g = 1\nh = 1\n# wip\n")
    (repo / "b.py").write_text("y = 99\n")
    tty("y")
    patch = "--- a/[ab].py\n@ Bump g\n<<<<\ng = 1\n====\ng = 2\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert git("show", "HEAD:[ab].py") == "g = 2\nh = 1\n"
    assert (repo / "[ab].py").read_text() == "g = 2\nh = 1\n# wip\n"
    assert (repo / "b.py").read_text() == "y = 99\n"
    assert status() == [" M [ab].py", " M b.py"]
    assert stash_list() == []


def test_ignored_glob_path_is_reported_as_ignored(repo, run):
    (repo / ".gitignore").write_text("\\[x\\].py\n")
    git("add", ".gitignore")
    git("commit", "-qm", "ignore")
    (repo / "[x].py").write_text("k = 1\n")
    code, out = run("-gc", "--git-allow-dirty", write_patch("--- a/[x].py\n<<<<\nk = 1\n====\nk = 2\n>>>>\n"))
    assert code == 0, out
    assert "[x].py is ignored by git" in out


def test_spaces_and_unicode_in_a_path(repo, run):
    name = "my módulo.py"
    (repo / name).write_text("u = 1\n")
    git("add", ".")
    git("commit", "-qm", "more")
    patch = f"--- a/{name}\n@ Bump ü\n<<<<\nu = 1\n====\nu = 2\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert last_message() == f"[xtrpatch] Bump ü\n\n{name}\n  - Bump ü"
    assert git("show", f"HEAD:{name}") == "u = 2\n"


def test_detached_head(repo, run):
    git("checkout", "-q", "--detach")
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 0, out
    assert "on a detached HEAD" in out
    assert commit_count() == 2


def test_first_commit_in_an_empty_repository(tmp_path, monkeypatch, run):
    d = tmp_path / "fresh"
    init_repo(d)
    monkeypatch.chdir(d)
    code, out = run("-gc", write_patch("--- a/new.py\n@ First file\n<<<<\n====\nprint(1)\n>>>>\n"))
    assert code == 0, out
    assert commit_count() == 1
    assert git("ls-files").split() == ["new.py"]
    assert last_message().splitlines()[0] == "[xtrpatch] First file"


def test_commit_lands_on_the_current_branch(repo, run):
    git("checkout", "-qb", "feature")
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 0, out
    assert "on feature" in out
    assert git("rev-list", "--count", "main").strip() == "1"
    assert git("rev-list", "--count", "feature").strip() == "2"


def test_failing_pre_commit_hook(repo, run):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\necho 'lint says no'\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)

    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert "lint says no" in out
    assert "git commit failed" in out
    assert commit_count() == 1
    assert "timeout=30" in (repo / "a.py").read_text()
    assert staged() == ["a.py"]


def test_commit_msg_hook_can_rewrite_the_message(repo, run):
    """Hooks run as they would for any commit. --no-verify is never passed."""
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text('#!/bin/sh\necho "Signed-off-by: hook" >> "$1"\n')
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 0, out
    assert last_message().endswith("Signed-off-by: hook")


# --- some hunks fail ------------------------------------------------------


def test_partial_failure_without_a_terminal_does_not_commit(repo, run):
    code, out = run("-gc", write_patch(PATCH_PARTIAL))
    assert code == 1
    assert "no terminal to ask on" in out
    assert commit_count() == 1
    # The patch itself behaves as it always has: what applied stays applied.
    assert "timeout=30" in (repo / "a.py").read_text()
    assert staged() == []


def test_partial_failure_skip(repo, run, tty):
    asked = tty()
    code, out = run("-gc", "--git-on-error", "skip", write_patch(PATCH_PARTIAL))
    assert code == 1
    assert asked == []
    assert "--git-on-error skip" in out
    assert commit_count() == 1
    assert staged() == []


def test_partial_failure_commit(repo, run):
    code, out = run("-gc", "--git-on-error", "commit", write_patch(PATCH_PARTIAL))
    assert code == 0, out
    assert commit_count() == 2
    assert last_message() == (
        "[xtrpatch] Add timeout to foo\n"
        "\n"
        "a.py\n"
        "  - Add timeout to foo\n"
        "\n"
        "Not applied:\n"
        "a.py\n"
        "  - Rename handler"
    )


def test_partial_failure_ask_yes(repo, run, tty):
    asked = tty("y")
    code, out = run("-gc", write_patch(PATCH_PARTIAL))
    assert code == 0, out
    assert asked == ["Some changes failed to apply. Commit the rest? [y/N] "]
    assert commit_count() == 2
    assert "Not applied:" in last_message()


@pytest.mark.parametrize("answer", ["n", "", "no", "maybe", "yy"])
def test_partial_failure_ask_no(repo, run, tty, answer):
    tty(answer)
    code, out = run("-gc", write_patch(PATCH_PARTIAL))
    assert code == 1
    assert "Not committing." in out
    assert commit_count() == 1
    assert staged() == []


@pytest.mark.parametrize("answer", ["y", "Y", "yes", " YES "])
def test_yes_is_recognised_in_its_usual_spellings(repo, run, tty, answer):
    tty(answer)
    code, _ = run("-gc", write_patch(PATCH_PARTIAL))
    assert code == 0
    assert commit_count() == 2


def test_explicit_ask_is_the_default(repo, run, tty):
    asked = tty("n")
    run("-gc", "--git-on-error", "ask", write_patch(PATCH_PARTIAL))
    assert len(asked) == 1


def test_closed_stdin_at_the_prompt_means_no(repo, run, monkeypatch):
    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr(gitcommit, "is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", eof)
    code, _ = run("-gc", write_patch(PATCH_PARTIAL))
    assert code == 1
    assert commit_count() == 1


def test_everything_failed_is_not_worth_asking_about(repo, run, tty):
    asked = tty()
    patch = "--- a/a.py\n@ Rename handler\n<<<<\ndef handler():\n====\ndef handle():\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 1
    assert asked == []
    assert "Nothing to commit." in out
    assert commit_count() == 1


def test_failure_in_another_file_is_reported_in_the_message(repo, run):
    patch = PATCH_FOO + "--- a/missing.py\n@ Fix the thing\n<<<<\na\n====\nb\n>>>>\n"
    code, out = run("-gc", "--git-on-error", "commit", write_patch(patch))
    assert code == 0, out
    assert last_files() == ["M a.py"]
    assert last_message().endswith("Not applied:\nmissing.py\n  - Fix the thing")


def test_conflicting_hunks_count_as_failure(repo, run):
    patch = PATCH_X + "--- a/a.py\n@ Set x to 3\n<<<<\nx = 1\n====\nx = 3\n>>>>\n"
    code, out = run("-gc", "--git-on-error", "skip", write_patch(patch))
    assert code == 1
    assert commit_count() == 1


def test_already_applied_hunks_are_not_failures(repo, run, tty):
    asked = tty()
    run("-gc", write_patch(PATCH_FOO, "one.patch"))
    code, out = run("-gc", write_patch(PATCH_FOO + PATCH_X, "two.patch"))
    assert code == 0, out
    assert asked == []
    assert last_message() == "[xtrpatch] Set x to 2\n\na.py\n  - Set x to 2"


# --- target files that already have uncommitted changes -------------------

DIRTY = A_PY + "# my work in progress\n"


def test_dirty_target_without_a_terminal_stops_before_applying(repo, run):
    (repo / "a.py").write_text(DIRTY)
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert "Found uncommitted changes:\n  a.py\n" in out
    assert "no terminal to ask on" in out
    assert "Nothing was applied." in out
    assert (repo / "a.py").read_text() == DIRTY
    assert commit_count() == 1
    assert stash_list() == []
    assert not (repo / ".xtr").exists()


def test_dirty_target_declined(repo, run, tty):
    (repo / "a.py").write_text(DIRTY)
    asked = tty("n")
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert asked == ["Stash and commit? [y/N] "]
    assert "Nothing was applied." in out
    assert (repo / "a.py").read_text() == DIRTY
    assert stash_list() == []


def test_the_prompt_reads_as_asked_for(repo, run, tty):
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "more")
    (repo / "a.py").write_text(DIRTY)
    (repo / "b.py").write_text("y = 5\n")
    tty("n")
    patch = PATCH_FOO + "--- a/b.py\n<<<<\ny = 5\n====\ny = 6\n>>>>\n"
    _, out = run("-gc", write_patch(patch))
    assert "Found uncommitted changes:\n  a.py\n  b.py\n\n" in out


def test_stash_and_commit(repo, run, tty):
    (repo / "a.py").write_text(DIRTY)
    tty("y")
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 0, out
    assert commit_count() == 2
    # The commit holds the patch and nothing else.
    assert git("show", "HEAD:a.py") == A_PY.replace("def foo():", "def foo(timeout=30):")
    # The working tree holds the patch and the earlier work.
    assert (repo / "a.py").read_text() == DIRTY.replace(
        "def foo():", "def foo(timeout=30):"
    )
    assert status() == [" M a.py"]
    assert staged() == []
    assert stash_list() == []


def test_stash_takes_only_the_files_the_patch_touches(repo, run, tty):
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "more")
    (repo / "a.py").write_text(DIRTY)
    (repo / "b.py").write_text("y = 99\n")
    (repo / "notes.txt").write_text("mine\n")

    seen = {}
    real_apply = repatch.apply_changes

    def spy(*args, **kwargs):
        seen["a"] = (repo / "a.py").read_text()
        seen["b"] = (repo / "b.py").read_text()
        seen["notes"] = (repo / "notes.txt").exists()
        return real_apply(*args, **kwargs)

    repatch.apply_changes, original = spy, repatch.apply_changes
    try:
        tty("y")
        code, out = run("-gc", write_patch(PATCH_FOO))
    finally:
        repatch.apply_changes = original

    assert code == 0, out
    # While the patch ran, a.py was back to its committed text and the
    # unrelated work had not moved.
    assert seen == {"a": A_PY, "b": "y = 99\n", "notes": True}
    assert status() == [" M a.py", " M b.py", "?? notes.txt"]
    assert stash_list() == []


def test_stash_leaves_an_earlier_stash_alone(repo, run, tty):
    (repo / "a.py").write_text(A_PY + "# stashed long ago\n")
    git("stash", "push", "-qm", "mine")
    (repo / "a.py").write_text(DIRTY)
    tty("y")
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 0, out
    entries = stash_list()
    assert len(entries) == 1 and "mine" in entries[0]
    assert "# my work in progress" in (repo / "a.py").read_text()


def test_stash_refused_when_something_is_already_staged(repo, run, tty):
    (repo / "b.py").write_text("y = 1\n")
    git("add", "b.py")
    (repo / "a.py").write_text(DIRTY)
    asked = tty()
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert asked == []
    assert "staged changes already" in out
    assert "Nothing was applied." in out
    assert (repo / "a.py").read_text() == DIRTY
    assert staged() == ["b.py"]
    assert stash_list() == []


def test_stash_refused_when_the_target_itself_is_staged(repo, run, tty):
    (repo / "a.py").write_text(DIRTY)
    git("add", "a.py")
    asked = tty()
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert asked == []
    assert "staged changes already" in out
    assert (repo / "a.py").read_text() == DIRTY
    assert staged() == ["a.py"]


def test_staged_changes_elsewhere_are_fine_when_no_stash_is_needed(repo, run):
    (repo / "b.py").write_text("y = 1\n")
    git("add", "b.py")
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 0, out
    assert last_files() == ["M a.py"]
    assert staged() == ["b.py"]


def test_untracked_target_is_refused(repo, run, tty):
    (repo / "wip.py").write_text("w = 1\n")
    asked = tty()
    patch = "--- a/wip.py\n@ Bump w\n<<<<\nw = 1\n====\nw = 2\n>>>>\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 1
    assert asked == []
    assert "  wip.py (untracked)" in out
    assert "untracked files cannot be stashed" in out
    assert (repo / "wip.py").read_text() == "w = 1\n"


def test_untracked_target_with_allow_dirty_is_committed_whole(repo, run):
    (repo / "wip.py").write_text("w = 1\nkeep = True\n")
    patch = "--- a/wip.py\n@ Bump w\n<<<<\nw = 1\n====\nw = 2\n>>>>\n"
    code, out = run("-gc", "--git-allow-dirty", write_patch(patch))
    assert code == 0, out
    assert last_files() == ["A wip.py"]
    assert git("show", "HEAD:wip.py") == "w = 2\nkeep = True\n"


def test_allow_dirty_commits_the_earlier_changes_too(repo, run, tty):
    (repo / "a.py").write_text(DIRTY)
    asked = tty()
    code, out = run("-gc", "--git-allow-dirty", write_patch(PATCH_FOO))
    assert code == 0, out
    assert asked == []
    assert "Found uncommitted changes" not in out
    assert git("show", "HEAD:a.py") == DIRTY.replace(
        "def foo():", "def foo(timeout=30):"
    )
    assert status() == []
    assert stash_list() == []


def test_creating_a_file_is_never_dirty(repo, run, tty):
    asked = tty()
    code, out = run("-gc", write_patch("--- a/new.py\n<<<<\n====\nprint(1)\n>>>>\n"))
    assert code == 0, out
    assert asked == []


def test_stash_then_hunks_that_no_longer_match(repo, run, tty):
    """
    The patch was written against the uncommitted text. Once that is
    stashed the hunk has nothing to match, so nothing is committed and the
    work comes back exactly as it was.
    """
    (repo / "a.py").write_text(DIRTY)
    patch = "--- a/a.py\n@ Finish it\n<<<<\n# my work in progress\n====\n# done\n>>>>\n"
    tty("y")
    code, out = run("-gc", write_patch(patch))
    assert code == 1
    assert commit_count() == 1
    assert (repo / "a.py").read_text() == DIRTY
    assert status() == [" M a.py"]
    assert staged() == []
    assert stash_list() == []


def test_stash_then_partial_failure_declined(repo, run, tty):
    """No commit, but the hunk that applied stays, merged with the work."""
    (repo / "a.py").write_text(DIRTY)
    asked = tty("y", "n")
    code, out = run("-gc", write_patch(PATCH_PARTIAL))
    assert code == 1
    assert len(asked) == 2
    assert commit_count() == 1
    assert (repo / "a.py").read_text() == DIRTY.replace(
        "def foo():", "def foo(timeout=30):"
    )
    assert staged() == []
    assert stash_list() == []
    assert "Uncommitted changes restored." in out


def test_stash_then_partial_failure_accepted(repo, run, tty):
    (repo / "a.py").write_text(DIRTY)
    tty("y", "y")
    code, out = run("-gc", write_patch(PATCH_PARTIAL))
    assert code == 0, out
    assert commit_count() == 2
    assert "# my work in progress" not in git("show", "HEAD:a.py")
    assert "# my work in progress" in (repo / "a.py").read_text()
    assert stash_list() == []


def test_stash_then_conflict_when_restoring(repo, run, tty):
    """The patch and the earlier work both changed the same line."""
    (repo / "a.py").write_text(A_PY.replace("x = 1", "x = 111"))
    tty("y")
    code, out = run("-gc", "--git-on-error", "commit", write_patch(PATCH_X))
    assert code == 1
    # The patch applied to the committed text and was committed.
    assert commit_count() == 2
    assert "x = 2" in git("show", "HEAD:a.py")
    # The work is not lost: it is in the stash, and the conflict is marked.
    assert "could not be put back cleanly" in out
    assert len(stash_list()) == 1
    assert "x = 111" in git("show", "stash@{0}:a.py")
    assert "<<<<<<<" in (repo / "a.py").read_text()


def test_stash_is_restored_when_the_patch_raises(repo, run, tty, monkeypatch, capsys):
    (repo / "a.py").write_text(DIRTY)
    tty("y")

    def boom(*args, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(repatch, "apply_changes", boom)
    monkeypatch.setattr(sys, "argv", ["xtrpatch", "-gc", write_patch(PATCH_FOO)])
    with pytest.raises(RuntimeError):
        repatch.main()
    assert (repo / "a.py").read_text() == DIRTY
    assert staged() == []
    assert stash_list() == []


def test_stash_then_failing_hook(repo, run, tty):
    """The patch is left staged, the earlier work unstaged on top of it."""
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    (repo / "a.py").write_text(DIRTY)
    tty("y")
    code, out = run("-gc", write_patch(PATCH_FOO))
    assert code == 1
    assert commit_count() == 1
    assert stash_list() == []
    assert git("show", ":a.py") == A_PY.replace("def foo():", "def foo(timeout=30):")
    assert (repo / "a.py").read_text() == DIRTY.replace(
        "def foo():", "def foo(timeout=30):"
    )


def test_stash_when_the_patch_deletes_the_dirty_file(repo, run, tty):
    (repo / "a.py").write_text(DIRTY)
    tty("y")
    code, out = run("-gc", write_patch("--- a/a.py\n! DELETE FILE\n"))
    # Committed, but the earlier edits have no file to go back onto.
    assert commit_count() == 2
    assert last_files() == ["D a.py"]
    assert code == 1
    assert len(stash_list()) == 1
    assert "# my work in progress" in git("show", "stash@{0}:a.py")


def test_stash_from_a_subdirectory(repo, run, tty, monkeypatch):
    sub = repo / "pkg"
    sub.mkdir()
    (sub / "m.py").write_text("x = 1\ny = 1\n")
    git("add", ".")
    git("commit", "-qm", "sub")
    (sub / "m.py").write_text("x = 1\ny = 1\n# wip\n")
    monkeypatch.chdir(sub)
    tty("y")
    code, out = run("-gc", write_patch("--- a/m.py\n@ Bump x\n<<<<\nx = 1\n====\nx = 2\n>>>>\n"))
    assert code == 0, out
    assert "  pkg/m.py\n" in out
    assert git("show", "HEAD:pkg/m.py") == "x = 2\ny = 1\n"
    assert (sub / "m.py").read_text() == "x = 2\ny = 1\n# wip\n"
    assert stash_list() == []


# --- --revert -------------------------------------------------------------


def test_revert_commit_says_what_it_reverts(repo, run):
    patch = write_patch(PATCH_FOO)
    run("-gc", patch)
    code, out = run("--revert", "-gc", patch)
    assert code == 0, out
    assert commit_count() == 3
    assert (repo / "a.py").read_text() == A_PY
    assert git("show", "HEAD:a.py") == A_PY
    assert last_message() == (
        "[xtrpatch] Revert: Add timeout to foo\n\na.py\n  - Add timeout to foo"
    )
    assert status() == []


def test_revert_a_single_file(repo, run):
    run("-gc", write_patch(PATCH_FOO))
    code, out = run("-gc", "--revert", "a.py")
    assert code == 0, out
    assert last_message() == (
        "[xtrpatch] Revert: Add timeout to foo\n\na.py\n  - Add timeout to foo"
    )
    assert git("show", "HEAD:a.py") == A_PY


def test_revert_several_files(repo, run):
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "more")
    patch = write_patch(
        PATCH_FOO + PATCH_X + "--- a/b.py\n@ Set y to 2\n<<<<\ny = 1\n====\ny = 2\n>>>>\n"
    )
    run("-gc", patch)
    code, out = run("--revert", "-gc", patch)
    assert code == 0, out
    assert last_files() == ["M a.py", "M b.py"]
    assert last_message() == (
        "[xtrpatch] Revert: Add timeout to foo (+2 more)\n"
        "\n"
        "a.py\n"
        "  - Add timeout to foo\n"
        "  - Set x to 2\n"
        "b.py\n"
        "  - Set y to 2"
    )


def test_revert_describes_the_patch_that_made_the_backup(repo, run):
    """
    Revert restores each file's latest backup. If a later patch touched the
    file, that is the change being undone, whatever file was named.
    """
    first = write_patch(PATCH_FOO, "first.patch")
    run("-gc", first)
    run("-gc", write_patch(PATCH_X, "second.patch"))
    code, out = run("--revert", "-gc", first)
    assert code == 0, out
    assert last_message() == "[xtrpatch] Revert: Set x to 2\n\na.py\n  - Set x to 2"
    assert "x = 1" in (repo / "a.py").read_text()
    assert "timeout=30" in (repo / "a.py").read_text()


def test_revert_without_comments(repo, run):
    patch = write_patch("--- a/a.py\n<<<<\nx = 1\n====\nx = 2\n>>>>\n")
    run("-gc", patch)
    code, out = run("--revert", "-gc", patch)
    assert code == 0, out
    assert last_message() == "[xtrpatch] Revert a.py\n\na.py"


def test_revert_uses_the_prefix(repo, run):
    patch = write_patch(PATCH_FOO)
    run("-gc", patch)
    run("--revert", "-gc", "-gmp", "undo: ", patch)
    assert last_message().splitlines()[0] == "undo: Revert: Add timeout to foo"


def test_revert_brings_back_a_deleted_file(repo, run):
    patch = write_patch("--- a/a.py\n@ Drop it\n! DELETE FILE\n")
    run("-gc", patch)
    assert last_files() == ["D a.py"]
    code, out = run("--revert", "-gc", patch)
    assert code == 0, out
    assert last_files() == ["A a.py"]
    assert git("show", "HEAD:a.py") == A_PY
    assert last_message().splitlines()[0] == "[xtrpatch] Revert: Drop it"


def test_revert_with_nothing_to_restore(repo, run):
    code, out = run("--revert", "-gc", "a.py")
    assert code == 1
    assert "No backups found" in out
    assert "Nothing to commit." in out
    assert commit_count() == 1


def test_revert_when_one_file_has_no_backup(repo, run):
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "more")
    run("-gc", write_patch(PATCH_FOO, "first.patch"))
    both = write_patch(PATCH_FOO + "--- a/b.py\n<<<<\ny = 1\n====\ny = 2\n>>>>\n", "both.patch")

    code, out = run("--revert", "-gc", both)
    assert code == 1
    assert "Some files could not be reverted" in out
    assert commit_count() == 3
    # Revert itself did its part, as it does without the flag.
    assert (repo / "a.py").read_text() == A_PY

    git("checkout", "-q", "--", "a.py")
    code, out = run("--revert", "-gc", "--git-on-error", "commit", both)
    assert code == 0, out
    assert last_message() == (
        "[xtrpatch] Revert: Add timeout to foo\n"
        "\n"
        "a.py\n"
        "  - Add timeout to foo\n"
        "\n"
        "Not reverted:\n"
        "b.py"
    )


def test_revert_that_changes_nothing(repo, run):
    """Reverting twice restores the same backup: nothing new to commit."""
    patch = write_patch(PATCH_FOO)
    run("-gc", patch)
    run("--revert", "-gc", patch)
    code, out = run("--revert", "-gc", patch)
    assert code == 0, out
    assert "Nothing to commit." in out
    assert commit_count() == 3


def test_revert_of_an_uncommitted_patch_is_a_dirty_target(repo, run):
    """Same rule as applying: a file with uncommitted changes stops the run."""
    patch = write_patch(PATCH_FOO)
    run(patch)
    patched = (repo / "a.py").read_text()
    code, out = run("--revert", "-gc", patch)
    assert code == 1
    assert "Found uncommitted changes:\n  a.py\n" in out
    assert "Nothing was reverted." in out
    assert (repo / "a.py").read_text() == patched


def test_revert_stash_and_commit(repo, run, tty):
    patch = write_patch(PATCH_FOO)
    run("-gc", patch)
    (repo / "a.py").write_text((repo / "a.py").read_text() + "# later work\n")
    tty("y")
    code, out = run("--revert", "-gc", patch)
    assert code == 0, out
    assert git("show", "HEAD:a.py") == A_PY
    assert (repo / "a.py").read_text() == A_PY + "# later work\n"
    assert stash_list() == []


def test_revert_outside_a_repository(tmp_path, monkeypatch, run):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text(A_PY)
    patch = write_patch(PATCH_FOO)
    run(patch)
    patched = (tmp_path / "a.py").read_text()
    code, out = run("--revert", "-gc", patch)
    assert code == 1
    assert "not inside a git repository" in out
    assert "Nothing was reverted." in out
    assert (tmp_path / "a.py").read_text() == patched


def test_revert_without_the_flag_is_unchanged(repo, run):
    patch = write_patch(PATCH_FOO)
    run("-gc", patch)
    code, out = run("--revert", patch)
    assert code == 0
    assert commit_count() == 2
    assert status() == [" M a.py"]
    code, _ = run("--revert", "never-patched.py")
    assert code == 0


# --- the results the commit is built from ---------------------------------


def test_apply_changes_returns_one_result_per_file(repo):
    (repo / "old.py").write_text("gone\n")
    changes = parse_multi_file_patch(
        PATCH_PARTIAL
        + "--- a/old.py\n! DELETE FILE\n"
        + "--- a/new.py\n<<<<\n====\nprint(1)\n>>>>\n"
        + "--- a/missing.py\n@ Fix\n<<<<\na\n====\nb\n>>>>\n"
        + "--- a/absent.py\n! DELETE FILE\n"
    )
    results = apply_changes(changes)
    by_path = {r["path"]: r["items"] for r in results}
    assert [r["path"] for r in results] == list(changes)
    assert by_path["a.py"] == [
        {"label": "Add timeout to foo", "auto": False, "status": "APPLIED"},
        {"label": "Rename handler", "auto": False, "status": "FAILED"},
    ]
    assert by_path["old.py"] == [
        {"label": "Delete file", "auto": True, "status": "APPLIED"}
    ]
    assert by_path["new.py"] == [
        {"label": "Create file", "auto": True, "status": "APPLIED"}
    ]
    assert by_path["missing.py"] == [
        {"label": "Fix", "auto": False, "status": "FAILED"}
    ]
    assert by_path["absent.py"] == [
        {"label": "Delete file", "auto": True, "status": "SKIPPED"}
    ]
    assert repatch.result_failed(results[0]) and repatch.result_changed(results[0])
    assert not repatch.result_failed(results[1])
    assert not repatch.result_changed(results[4])


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_attribute_results(repo):
    changes = parse_multi_file_patch(
        "--- a/a.py\n! CHMOD +x\n! CHMOD +x\n@ lock it\n! CHMOD u+s\n! CHMOD bogus\n"
    )
    items = apply_changes(changes)[0]["items"]
    assert [(i["label"], i["auto"], i["status"]) for i in items] == [
        ("CHMOD +x", True, "APPLIED"),
        ("CHMOD +x", True, "SKIPPED"),
        ("lock it", False, "FAILED"),  # refused: setuid
        ("CHMOD bogus", True, "FAILED"),
    ]


def test_attribute_on_a_missing_file_is_a_failure(repo):
    results = apply_changes(parse_multi_file_patch("--- a/nope.sh\n! CHMOD +x\n"))
    assert results[0]["items"] == [
        {"label": "CHMOD +x", "auto": True, "status": "FAILED"}
    ]


def test_revert_file_returns_a_result(repo):
    assert revert_file("a.py")["items"] == [
        {"label": None, "auto": True, "status": "FAILED"}
    ]
    apply_changes(parse_multi_file_patch(PATCH_FOO))  # no patch file to archive
    assert revert_file("a.py") == {
        "path": "a.py",
        "items": [{"label": None, "auto": True, "status": "APPLIED"}],
    }


# --- the message builder --------------------------------------------------


def item(label, status="APPLIED", auto=False):
    return {"label": label, "auto": auto, "status": status}


def test_message_collapses_multiline_labels():
    msg = build_message("[p] ", [("a.py", [item("two\n  lines")])], [])
    assert msg == "[p] two lines\n\na.py\n  - two lines\n"


def test_message_counts_only_real_comments_in_the_subject():
    committed = [
        ("a.py", [item("One"), item(None, auto=True), item("Two", "SKIPPED")]),
        ("b.py", [item("Delete file", auto=True), item("Three")]),
    ]
    msg = build_message("", committed, [])
    assert msg.splitlines()[0] == "One (+1 more)"
    assert msg == "One (+1 more)\n\na.py\n  - One\nb.py\n  - Delete file\n  - Three\n"


def test_message_not_applied_lists_only_failures():
    results = [
        ("a.py", [item("Ok"), item("Bad", "FAILED"), item(None, "BLOCKED", auto=True)]),
        ("b.py", [item("Fine")]),
        ("c.py", [item("Clash", "CONFLICT"), item("Stray", "EMPTY_SEARCH")]),
    ]
    msg = build_message("", [("a.py", results[0][1])], results)
    assert msg.endswith("\nNot applied:\na.py\n  - Bad\nc.py\n  - Clash\n  - Stray\n")
    assert "b.py" not in msg


# --- ! REPLACE in a commit --------------------------------------------------


def test_rename_directive_is_committed(repo, run):
    patch = "--- a/a.py\n@ Rename bar to baz\n! REPLACE bar => baz\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 0, out
    assert "def baz(msg):" in git("show", "HEAD:a.py")
    assert last_message() == "[xtrpatch] Rename bar to baz\n\na.py\n  - Rename bar to baz"


def test_rename_directive_without_a_comment(repo, run):
    code, out = run("-gc", write_patch("--- a/a.py\n! REPLACE bar => baz\n"))
    assert code == 0, out
    assert last_message() == "[xtrpatch] Patch a.py\n\na.py\n  - REPLACE bar => baz"


def test_failed_rename_counts_as_a_failure(repo, run):
    patch = PATCH_FOO + "--- a/a.py\n@ Rename nothing\n! REPLACE nothing => something\n"
    code, out = run("-gc", write_patch(patch))
    assert code == 1
    assert commit_count() == 1

    git("checkout", "-q", "--", "a.py")
    code, out = run("-gc", "--git-on-error", "commit", write_patch(patch, "again.patch"))
    assert code == 0, out
    assert last_message().endswith("Not applied:\na.py\n  - Rename nothing")


def test_revert_of_a_rename_is_committed(repo, run):
    patch = write_patch("--- a/a.py\n@ Rename bar to baz\n! REPLACE bar => baz\n")
    run("-gc", patch)
    code, out = run("--revert", "-gc", patch)
    assert code == 0, out
    assert git("show", "HEAD:a.py") == A_PY
    assert last_message().splitlines()[0] == "[xtrpatch] Revert: Rename bar to baz"


# --- ! REQUIRES <commit> ----------------------------------------------------


def head(cwd=None, short=False):
    args = ["rev-parse"] + (["--short"] if short else []) + ["HEAD"]
    return git(*args, cwd=cwd).strip()


def requiring(commit, body=PATCH_FOO):
    return f"! REQUIRES {commit}\n\n{body}"


def test_parse_requires():
    parse = repatch.parse_requires
    assert parse(PATCH_FOO) == []
    assert parse("! REQUIRES abc1234\n" + PATCH_FOO) == ["abc1234"]
    assert parse("!requires abc1234\n  ! Requires   def5678  \n") == ["abc1234", "def5678"]
    assert parse("! REQUIRES abc1234\n! REQUIRES abc1234\n") == ["abc1234"]
    # Anywhere outside a block counts, under a file header included.
    assert parse(PATCH_FOO + "! REQUIRES abc1234\n") == ["abc1234"]
    assert parse("--- a/a.py\n! REQUIRES abc1234\n" + PATCH_FOO) == ["abc1234"]
    # Not a requirement: no commit, or trailing words.
    assert parse("! REQUIRES\n! REQUIRES abc1234 please\n") == []


def test_parse_requires_ignores_text_inside_blocks():
    patch = (
        "--- a/doc.md\n<<<<\n! REQUIRES aaaa111\n====\n! REQUIRES bbbb222\n"
        "====\n! REQUIRES cccc333\n>>>>\n! REQUIRES dddd444\n"
        "--- a/doc.md\n<< 3\n! REQUIRES eeee555\n====\n>>>>\n"
    )
    assert repatch.parse_requires(patch) == ["dddd444"]


def test_requires_line_does_not_disturb_the_patch(repo):
    changes = parse_multi_file_patch(requiring("abc1234"))
    assert list(changes) == ["a.py"] and len(changes["a.py"]) == 1


@pytest.mark.parametrize("short", [False, True])
def test_requires_head_itself(repo, run, short):
    code, out = run(write_patch(requiring(head(short=short))))
    assert code == 0, out
    assert "timeout=30" in (repo / "a.py").read_text()


def test_requires_an_ancestor(repo, run):
    first = head()
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "second")
    code, out = run(write_patch(requiring(first.upper())))
    assert code == 0, out
    assert "timeout=30" in (repo / "a.py").read_text()


def test_requires_a_commit_on_another_branch(repo, run):
    git("checkout", "-qb", "theirs")
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "their work")
    theirs = head()
    git("checkout", "-q", "main")

    code, out = run(write_patch(requiring(theirs)))
    assert code == 1
    assert f"needs commit {theirs}, which is not in your current branch" in out
    assert "Pass --ignore-requires to apply anyway." in out
    assert "Nothing was applied." in out
    assert (repo / "a.py").read_text() == A_PY
    assert not (repo / ".xtr").exists()

    git("merge", "-q", "theirs")
    code, out = run(write_patch(requiring(theirs)))
    assert code == 0, out


def test_requires_a_descendant_of_head_is_not_met(repo, run):
    """'On or after': being behind the commit is the case to catch."""
    (repo / "b.py").write_text("y = 1\n")
    git("add", ".")
    git("commit", "-qm", "second")
    newer = head()
    git("checkout", "-q", "--detach", "HEAD~1")
    code, out = run(write_patch(requiring(newer)))
    assert code == 1
    assert (repo / "a.py").read_text() == A_PY


def test_requires_before_and_after_a_pull(tmp_path, monkeypatch, run):
    """The reason this exists: applying a patch before `git pull`."""
    origin = tmp_path / "origin"
    init_repo(origin)
    (origin / "a.py").write_text(A_PY)
    git("add", ".", cwd=origin)
    git("commit", "-qm", "init", cwd=origin)
    mine = tmp_path / "mine"
    git("clone", "-q", str(origin), str(mine))
    git("config", "user.name", "Me", cwd=mine)
    git("config", "user.email", "me@example.com", cwd=mine)

    # Someone else pushes work the patch builds on.
    (origin / "a.py").write_text(A_PY + "\n\ndef helper():\n    pass\n")
    git("commit", "-qam", "add helper", cwd=origin)
    theirs = head(cwd=origin)
    patch = requiring(
        theirs,
        "--- a/a.py\n@ Use the helper\n<<<<\ndef helper():\n    pass\n====\n"
        "def helper():\n    return 1\n>>>>\n",
    )

    monkeypatch.chdir(mine)
    code, out = run(write_patch(patch))
    assert code == 1
    assert f"needs commit {theirs}, which this clone does not have" in out
    assert (mine / "a.py").read_text() == A_PY

    git("fetch", "-q", cwd=mine)
    code, out = run(write_patch(patch))
    assert code == 1
    assert "which is not in your current branch" in out

    git("pull", "-q", cwd=mine)
    code, out = run(write_patch(patch))
    assert code == 0, out
    assert "return 1" in (mine / "a.py").read_text()


def test_requires_an_unknown_commit(repo, run):
    code, out = run(write_patch(requiring("deadbeefdeadbeef")))
    assert code == 1
    assert "needs commit deadbeefdeadbeef, which this clone does not have" in out
    assert (repo / "a.py").read_text() == A_PY


@pytest.mark.parametrize("value", ["main", "HEAD", "--help", "v1.0", "abc", "-n1", "HEAD~1"])
def test_requires_takes_only_hashes(repo, run, value):
    code, out = run(write_patch(requiring(value)))
    assert code == 1
    assert f"`! REQUIRES {value}`, which is not a commit hash" in out
    assert (repo / "a.py").read_text() == A_PY


def test_requires_a_hash_that_names_a_tree_not_a_commit(repo, run):
    tree = git("rev-parse", "HEAD^{tree}").strip()
    code, out = run(write_patch(requiring(tree)))
    assert code == 1
    assert (repo / "a.py").read_text() == A_PY


def test_requires_several_reports_only_the_unmet(repo, run):
    patch = f"! REQUIRES {head()}\n! REQUIRES deadbeef\n" + PATCH_FOO
    code, out = run(write_patch(patch))
    assert code == 1
    assert "deadbeef" in out
    assert f"needs commit {head()}" not in out
    assert (repo / "a.py").read_text() == A_PY


def test_requires_outside_a_repository(tmp_path, monkeypatch, run):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text(A_PY)
    code, out = run(write_patch(requiring("abc1234")))
    assert code == 1
    assert "this is not a git repository, so that cannot be checked" in out
    assert (tmp_path / "a.py").read_text() == A_PY


def test_requires_without_git_installed(repo, run, monkeypatch):
    monkeypatch.setattr(gitcommit.shutil, "which", lambda name: None)
    code, out = run(write_patch(requiring(head())))
    assert code == 1
    assert "git is not installed, so that cannot be checked" in out
    assert (repo / "a.py").read_text() == A_PY


def test_requires_in_a_repository_with_no_commits(tmp_path, monkeypatch, run):
    d = tmp_path / "fresh"
    init_repo(d)
    monkeypatch.chdir(d)
    (d / "a.py").write_text(A_PY)
    code, out = run(write_patch(requiring("abc1234")))
    assert code == 1
    assert (d / "a.py").read_text() == A_PY


def test_ignore_requires(repo, run, monkeypatch):
    code, out = run("--ignore-requires", write_patch(requiring("deadbeef")))
    assert code == 0, out
    assert "--ignore-requires" in out
    assert "timeout=30" in (repo / "a.py").read_text()


def test_ignore_requires_never_runs_git(tmp_path, monkeypatch, run):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text(A_PY)

    def explode(*a, **k):
        raise AssertionError("git was run")

    monkeypatch.setattr(subprocess, "run", explode)
    code, out = run("--ignore-requires", write_patch(requiring("not-even-a-hash")))
    assert code == 0, out
    assert "timeout=30" in (tmp_path / "a.py").read_text()


def test_ignore_requires_does_not_need_git_commit(repo, run):
    code, out = run("--ignore-requires", write_patch(PATCH_FOO))
    assert code == 0, out


def test_requires_unmet_on_a_terminal_apply_anyway(repo, run, tty):
    asked = tty("y")
    code, out = run(write_patch(requiring("deadbeef")))
    assert code == 0, out
    assert asked == ["Apply anyway? [y/N] "]
    assert "timeout=30" in (repo / "a.py").read_text()


def test_requires_unmet_on_a_terminal_declined(repo, run, tty):
    asked = tty("n")
    code, out = run(write_patch(requiring("deadbeef")))
    assert code == 1
    assert len(asked) == 1
    assert "Nothing was applied." in out
    assert (repo / "a.py").read_text() == A_PY


def test_requires_met_asks_nothing(repo, run, tty):
    asked = tty()
    code, out = run(write_patch(requiring(head())))
    assert code == 0, out
    assert asked == []


def test_requires_is_checked_before_the_commit_checks(repo, run, tty):
    """Unmet requirement plus a dirty target: one refusal, no stash prompt."""
    (repo / "a.py").write_text(A_PY + "# wip\n")
    asked = tty("n")
    code, out = run("-gc", write_patch(requiring("deadbeef")))
    assert code == 1
    assert asked == ["Apply anyway? [y/N] "]
    assert "Found uncommitted changes" not in out
    assert stash_list() == []


def test_requires_met_then_commit(repo, run):
    code, out = run("-gc", write_patch(requiring(head())))
    assert code == 0, out
    assert commit_count() == 2
    assert "REQUIRES" not in last_message()


def test_requires_overridden_then_commit(repo, run, tty):
    tty("y")
    code, out = run("-gc", write_patch(requiring("deadbeef")))
    assert code == 0, out
    assert commit_count() == 2


def test_revert_does_not_check_requires(repo, run):
    patch = write_patch(requiring(head()))
    run(patch)
    Path(patch).write_text(requiring("deadbeef"))
    code, out = run("--revert", patch)
    assert code == 0, out
    assert (repo / "a.py").read_text() == A_PY


def test_requires_from_a_subdirectory(repo, run, monkeypatch):
    sub = repo / "sub"
    sub.mkdir()
    (sub / "s.py").write_text("x = 1\n")
    monkeypatch.chdir(sub)
    patch = requiring(head(), "--- a/s.py\n<<<<\nx = 1\n====\nx = 2\n>>>>\n")
    code, out = run(write_patch(patch))
    assert code == 0, out
    assert (sub / "s.py").read_text() == "x = 2\n"


# --- end to end, as a real process ----------------------------------------


def xtrpatch_process(args, cwd, **kwargs):
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "xtrshow.repatch"] + args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        **kwargs,
    )


def test_process_commits(repo):
    write_patch(PATCH_FOO)
    done = xtrpatch_process(["-gc", "p.patch"], repo, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stdout
    assert commit_count() == 2


def test_process_without_a_terminal_never_blocks_on_a_prompt(repo):
    """Real stdin, really not a terminal: must return, not wait for input."""
    (repo / "a.py").write_text(DIRTY)
    write_patch(PATCH_FOO)
    done = xtrpatch_process(
        ["-gc", "p.patch"], repo, stdin=subprocess.DEVNULL, timeout=60
    )
    assert done.returncode == 1
    assert "no terminal to ask on" in done.stdout
    assert (repo / "a.py").read_text() == DIRTY

    git("checkout", "-q", "--", "a.py")
    write_patch(PATCH_PARTIAL)
    done = xtrpatch_process(
        ["-gc", "p.patch"], repo, stdin=subprocess.DEVNULL, timeout=60
    )
    assert done.returncode == 1
    assert commit_count() == 1


@pytest.mark.skipif(os.name != "posix", reason="needs a pseudo-terminal")
def test_process_on_a_real_terminal_asks_and_obeys(repo):
    """The stash prompt and the partial-failure prompt, typed at a pty."""
    import pty

    (repo / "a.py").write_text(DIRTY)
    write_patch(PATCH_PARTIAL)

    master, slave = pty.openpty()
    try:
        os.write(master, b"y\ny\n")
        done = xtrpatch_process(["-gc", "p.patch"], repo, stdin=slave, timeout=60)
    finally:
        os.close(master)
        os.close(slave)

    assert done.returncode == 0, done.stdout
    assert "Stash and commit? [y/N]" in done.stdout
    assert "Commit the rest? [y/N]" in done.stdout
    assert commit_count() == 2
    assert "# my work in progress" not in git("show", "HEAD:a.py")
    assert "# my work in progress" in (repo / "a.py").read_text()
    assert stash_list() == []


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
