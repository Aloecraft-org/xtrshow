# ./tests/test_file_attributes.py
# License: Apache-2.0 (disclaimer at bottom of file)
import os
import stat

import pytest

from xtrshow.cli import format_file_meta
from xtrshow.repatch import (
    apply_changes,
    apply_chmod_spec,
    parse_chown_spec,
    parse_multi_file_patch,
    revert_file,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    d = tmp_path / "proj"
    d.mkdir()
    monkeypatch.chdir(d)
    return d


# --- parsing -------------------------------------------------------------


def test_parser_records_attribute_directives():
    changes = parse_multi_file_patch(
        "--- a/run.sh\n@ make it runnable\n! CHMOD +x\n!chown alice:staff\n"
    )
    ops = changes["run.sh"]
    assert [(o["op"], o["arg"]) for o in ops] == [("chmod", "+x"), ("chown", "alice:staff")]
    assert ops[0]["annotation"] == "make it runnable"


@pytest.mark.parametrize(
    "spec,start,expected",
    [
        ("755", 0o644, 0o755),
        ("0600", 0o644, 0o600),
        ("u+x", 0o644, 0o744),
        ("a+x", 0o644, 0o755),
        ("go-rwx", 0o755, 0o700),
        ("u=rw,go=r", 0o777, 0o644),
        ("u+x-w", 0o644, 0o544),
        ("a+X", 0o644, 0o644),
        ("a+X", 0o744, 0o755),
        ("u+s", 0o755, 0o4755),
    ],
)
def test_chmod_spec(spec, start, expected):
    assert apply_chmod_spec(spec, start) == expected


def test_chmod_without_who_respects_umask():
    assert apply_chmod_spec("+x", 0o644, umask=0o022) == 0o755
    assert apply_chmod_spec("+w", 0o444, umask=0o022) == 0o644


def test_capital_x_sets_execute_on_directories():
    assert apply_chmod_spec("a+X", 0o644, is_dir=True) == 0o755


@pytest.mark.parametrize("spec", ["+q", "999", "rwx", ""])
def test_chmod_spec_rejects_garbage(spec):
    with pytest.raises(ValueError):
        apply_chmod_spec(spec, 0o644)


@posix_only
def test_chown_spec_accepts_names_ids_and_group_only():
    assert parse_chown_spec("0:0") == (0, 0)
    assert parse_chown_spec(":0") == (-1, 0)
    assert parse_chown_spec("0") == (0, -1)
    assert parse_chown_spec("root") == (0, -1)
    with pytest.raises(ValueError):
        parse_chown_spec("no-such-user-xyz")
    with pytest.raises(ValueError):
        parse_chown_spec(":")


# --- applying ------------------------------------------------------------


@posix_only
def test_chmod_after_content_edit(proj, capsys):
    target = proj / "run.sh"
    target.write_text("echo hi\n")
    os.chmod(target, 0o644)

    patch = "--- a/run.sh\n<<<<\necho hi\n====\necho hello\n>>>>\n! CHMOD 755\n"
    apply_changes(parse_multi_file_patch(patch))

    assert target.read_text() == "echo hello\n"
    assert mode_of(target) == 0o755
    assert "MODE 0644 (rw-r--r--) → 0755 (rwxr-xr-x)" in capsys.readouterr().out


@posix_only
def test_create_file_and_make_it_executable(proj):
    patch = "--- a/new.sh\n<<<<\n====\n#!/bin/sh\necho new\n>>>>\n! CHMOD 0750\n"
    apply_changes(parse_multi_file_patch(patch))

    assert (proj / "new.sh").read_text() == "#!/bin/sh\necho new\n"
    assert mode_of(proj / "new.sh") == 0o750


@posix_only
def test_attribute_only_patch_backs_up_and_reverts(proj, capsys):
    target = proj / "tool.py"
    target.write_text("print(1)\n")
    os.chmod(target, 0o640)

    apply_changes(parse_multi_file_patch("--- a/tool.py\n! CHMOD a+x\n"))
    assert mode_of(target) == 0o751
    assert target.read_text() == "print(1)\n"
    assert (proj / ".xtr" / "backup" / "tool.py.orig.attrs").exists()

    revert_file("tool.py")
    assert mode_of(target) == 0o640


@posix_only
def test_revert_restores_mode_after_edit(proj):
    target = proj / "run.sh"
    target.write_text("echo hi\n")
    os.chmod(target, 0o700)

    patch = "--- a/run.sh\n<<<<\necho hi\n====\necho bye\n>>>>\n! CHMOD 644\n"
    apply_changes(parse_multi_file_patch(patch))
    assert mode_of(target) == 0o644

    revert_file("run.sh")
    assert target.read_text() == "echo hi\n"
    assert mode_of(target) == 0o700


@posix_only
def test_special_bits_refused_by_default(proj, capsys):
    target = proj / "bin"
    target.write_text("x\n")
    os.chmod(target, 0o755)

    apply_changes(parse_multi_file_patch("--- a/bin\n! CHMOD u+s\n"))
    assert mode_of(target) == 0o755
    assert "REFUSED" in capsys.readouterr().out

    apply_changes(
        parse_multi_file_patch("--- a/bin\n! CHMOD 4755\n"), allow_special_modes=True
    )
    assert mode_of(target) == 0o4755


@posix_only
def test_chmod_on_missing_file_fails_cleanly(proj, capsys):
    apply_changes(parse_multi_file_patch("--- a/ghost.sh\n! CHMOD +x\n"))
    out = capsys.readouterr().out
    assert "ghost.sh ... CHMOD +x FAILED: file does not exist" in out
    assert not (proj / "ghost.sh").exists()


@posix_only
def test_bad_mode_reports_and_other_files_still_apply(proj, capsys):
    (proj / "a.sh").write_text("a\n")
    (proj / "b.sh").write_text("b\n")
    os.chmod(proj / "b.sh", 0o644)

    apply_changes(
        parse_multi_file_patch("--- a/a.sh\n! CHMOD +q\n--- a/b.sh\n! CHMOD 700\n")
    )
    assert "CHMOD +q FAILED" in capsys.readouterr().out
    assert mode_of(proj / "b.sh") == 0o700


@posix_only
def test_chown_to_current_owner(proj, capsys):
    target = proj / "f.txt"
    target.write_text("x\n")
    st = os.stat(target)

    apply_changes(parse_multi_file_patch(f"--- a/f.txt\n! CHOWN {st.st_uid}:{st.st_gid}\n"))
    assert "OWNER" in capsys.readouterr().out
    assert (os.stat(target).st_uid, os.stat(target).st_gid) == (st.st_uid, st.st_gid)


@posix_only
@pytest.mark.skipif(os.name == "posix" and os.geteuid() == 0, reason="root can chown")
def test_chown_without_privilege_fails_per_file(proj, capsys):
    (proj / "f.txt").write_text("x\n")
    apply_changes(parse_multi_file_patch("--- a/f.txt\n! CHOWN 0:0\n"))
    assert "CHOWN 0:0 FAILED" in capsys.readouterr().out


def test_delete_then_chmod_does_not_resurrect(proj, capsys):
    (proj / "old.sh").write_text("x\n")
    apply_changes(parse_multi_file_patch("--- a/old.sh\n! DELETE FILE\n! CHMOD +x\n"))
    assert not (proj / "old.sh").exists()
    assert "file does not exist" in capsys.readouterr().out


# --- showing -------------------------------------------------------------


@posix_only
def test_meta_line_shows_mode_and_owner(proj):
    target = proj / "run.sh"
    target.write_text("x\n")
    os.chmod(target, 0o755)

    meta = format_file_meta(str(target), 1)
    assert "| mode 0755 (rwxr-xr-x) |" in meta
    assert "| owner " in meta
    assert meta.split(" | ")[-1].startswith("sha256 ")


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
