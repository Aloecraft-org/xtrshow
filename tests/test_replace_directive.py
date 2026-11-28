# ./tests/test_replace_directive.py
# License: Apache-2.0 (disclaimer at bottom of file)
"""`! REPLACE old => new`: a literal, whole-word rename across one file."""
import os
import sys

import pytest

from xtrshow import repatch
from xtrshow.repatch import apply_changes, parse_multi_file_patch, revert_file


@pytest.fixture
def proj(tmp_path, monkeypatch):
    d = tmp_path / "proj"
    d.mkdir()
    monkeypatch.chdir(d)
    return d


def apply(patch):
    return apply_changes(parse_multi_file_patch(patch))


def statuses(results):
    return [i["status"] for r in results for i in r["items"]]


def rename(proj, before, old, new, name="m.py"):
    """Write `before`, run one directive on it, return (text after, results)."""
    (proj / name).write_bytes(before.encode("utf-8"))
    results = apply(f"--- a/{name}\n! REPLACE {old} => {new}\n")
    return (proj / name).read_bytes().decode("utf-8"), results


# --- parsing -------------------------------------------------------------


def test_parser_records_the_directive():
    changes = parse_multi_file_patch(
        "--- a/m.py\n@ Rename the counter\n! REPLACE old_name => new_name\n"
    )
    assert changes["m.py"] == [
        {
            "patch_line": 3,
            "op": "replace",
            "old": "old_name",
            "new": "new_name",
            "raw": "! REPLACE old_name => new_name",
            "annotation": "Rename the counter",
        }
    ]


@pytest.mark.parametrize(
    "line",
    [
        "! REPLACE a => b",
        "!REPLACE a => b",
        "! replace a => b",
        "!   Replace   a   =>   b   ",
        "    ! REPLACE a => b",
    ],
)
def test_parser_is_relaxed_about_case_and_spacing(line):
    op = parse_multi_file_patch(f"--- a/m.py\n{line}\n")["m.py"][0]
    assert (op["old"], op["new"]) == ("a", "b")


def test_parser_keeps_spaces_inside_old_and_new():
    op = parse_multi_file_patch("--- a/m.py\n! REPLACE unsigned int => size_t\n")[
        "m.py"
    ][0]
    assert (op["old"], op["new"]) == ("unsigned int", "size_t")


def test_the_first_arrow_separates_old_from_new():
    op = parse_multi_file_patch("--- a/m.js\n! REPLACE cb => (x) => x\n")["m.js"][0]
    assert (op["old"], op["new"]) == ("cb", "(x) => x")


@pytest.mark.parametrize(
    "line",
    ["! REPLACE", "! REPLACE a", "! REPLACE a b", "! REPLACE a =>", "! REPLACE => b",
     "! REPLACE a=>b"],
)
def test_malformed_directive_is_kept_so_it_can_fail_loudly(proj, line, capsys):
    (proj / "m.py").write_text("a = 1\n")
    op = parse_multi_file_patch(f"--- a/m.py\n{line}\n")["m.py"][0]
    assert op["op"] == "replace" and op["old"] is None

    results = apply(f"--- a/m.py\n{line}\n")
    assert statuses(results) == ["FAILED"]
    assert "expected `! REPLACE old => new`" in capsys.readouterr().out
    assert (proj / "m.py").read_text() == "a = 1\n"


def test_directive_before_any_file_header_is_ignored():
    assert parse_multi_file_patch("! REPLACE a => b\n") == {}


def test_directive_text_inside_a_block_is_content(proj):
    """A patch may add the directive as text, to documentation for instance."""
    (proj / "doc.md").write_text("intro\n")
    results = apply(
        "--- a/doc.md\n<<<<\nintro\n====\nintro\n! REPLACE intro => outro\n>>>>\n"
    )
    assert statuses(results) == ["APPLIED"]
    assert (proj / "doc.md").read_text() == "intro\n! REPLACE intro => outro\n"


# --- matching ------------------------------------------------------------


def test_whole_words_only(proj):
    before = (
        "count = 1\n"
        "discount = count + 1\n"
        "count_total = count\n"
        "recount(count)\n"
        "x.count, count.y, [count], 'count'\n"
        "Count = COUNT\n"
        "count2 = _count\n"
    )
    after, results = rename(proj, before, "count", "n")
    assert after == (
        "n = 1\n"
        "discount = n + 1\n"
        "count_total = n\n"
        "recount(n)\n"
        "x.n, n.y, [n], 'n'\n"
        "Count = COUNT\n"
        "count2 = _count\n"
    )
    assert statuses(results) == ["APPLIED"]


def test_reports_how_many_places(proj, capsys):
    rename(proj, "a a a\n", "a", "b")
    assert "REPLACE a => b (3 places)" in capsys.readouterr().out
    rename(proj, "a\n", "a", "b")
    assert "REPLACE a => b (1 place)" in capsys.readouterr().out


def test_old_is_literal_not_a_pattern(proj):
    after, _ = rename(proj, "a.b = axb\n", "a.b", "c")
    assert after == "c = axb\n"

    after, _ = rename(proj, "f(x)* f(x)\n", "f(x)*", "g")
    assert after == "g f(x)\n"


def test_new_is_literal_too(proj):
    after, _ = rename(proj, "sep = x\n", "x", r"'\1\n\g<0>'")
    assert after == "sep = '\\1\\n\\g<0>'\n"


def test_no_word_edge_is_demanded_where_old_has_none(proj):
    after, _ = rename(proj, "p->next = q->next;\n", "->", ".")
    assert after == "p.next = q.next;\n"

    # Leading dot: no edge on the left, a word edge on the right.
    after, _ = rename(proj, "a.old b.older c.old\n", ".old", ".new")
    assert after == "a.new b.older c.new\n"


def test_dotted_and_hyphenated_names(proj):
    after, _ = rename(proj, "os.path.join(x); myos.path.join(y)\n", "os.path.join", "join")
    assert after == "join(x); myos.path.join(y)\n"

    after, _ = rename(proj, "get-user get-users\n", "get-user", "fetch-user")
    assert after == "fetch-user get-users\n"


def test_phrase_with_a_space(proj):
    after, _ = rename(proj, "unsigned int n; unsigned integer;\n", "unsigned int", "size_t")
    assert after == "size_t n; unsigned integer;\n"


def test_unicode_identifiers(proj):
    after, _ = rename(proj, "größe = 1\ngrößer = größe\n", "größe", "size")
    assert after == "size = 1\ngrößer = size\n"


def test_case_sensitive(proj):
    after, results = rename(proj, "Foo foo FOO\n", "foo", "bar")
    assert after == "Foo bar FOO\n"


def test_line_endings_are_left_alone(proj):
    after, _ = rename(proj, "a = 1\r\nb = a\r\n", "a", "z")
    assert after == "z = 1\r\nb = z\r\n"

    after, _ = rename(proj, "a = 1\nb = a", "a", "z")
    assert after == "z = 1\nb = z"  # no newline invented at the end


# --- failures and re-runs --------------------------------------------------


def test_no_match_is_a_failure(proj, capsys):
    after, results = rename(proj, "discount = 1\n", "count", "n")
    assert after == "discount = 1\n"
    assert statuses(results) == ["FAILED"]
    out = capsys.readouterr().out
    assert "REPLACE count => n FAILED: no whole-word match" in out
    assert (proj / ".xtr" / "backup" / "m.py.rpterr").exists()


def test_rerun_is_already_applied(proj, capsys):
    (proj / "m.py").write_text("count = 1\n")
    patch = "--- a/m.py\n! REPLACE count => n\n"
    apply(patch)
    capsys.readouterr()
    results = apply(patch)
    assert statuses(results) == ["SKIPPED"]
    assert "[Already Applied]" in capsys.readouterr().out
    assert (proj / "m.py").read_text() == "n = 1\n"


def test_same_old_and_new_is_a_failure(proj, capsys):
    after, results = rename(proj, "a = 1\n", "a", "a")
    assert statuses(results) == ["FAILED"]
    assert "old and new are the same" in capsys.readouterr().out


def test_missing_file_is_a_failure(proj, capsys):
    results = apply("--- a/nope.py\n! REPLACE a => b\n")
    assert statuses(results) == ["FAILED"]
    assert "file does not exist" in capsys.readouterr().out
    assert not (proj / "nope.py").exists()


def test_binary_file_is_a_failure_and_untouched(proj):
    raw = b"\xff\xfe\x00count\x00\x80"
    (proj / "blob.bin").write_bytes(raw)
    results = apply("--- a/blob.bin\n! REPLACE count => n\n")
    assert statuses(results) == ["FAILED"]
    assert (proj / "blob.bin").read_bytes() == raw


def test_one_failing_directive_does_not_stop_the_others(proj):
    (proj / "m.py").write_text("a = b\n")
    results = apply("--- a/m.py\n! REPLACE a => x\n! REPLACE zzz => y\n! REPLACE b => z\n")
    assert statuses(results) == ["APPLIED", "FAILED", "APPLIED"]
    assert (proj / "m.py").read_text() == "x = z\n"


# --- ordering ----------------------------------------------------------------


def test_directives_run_in_order(proj):
    (proj / "m.py").write_text("a b\n")
    apply("--- a/m.py\n! REPLACE a => b\n! REPLACE b => c\n")
    assert (proj / "m.py").read_text() == "c c\n"


def test_runs_after_the_files_hunks(proj):
    """
    Hunks are written against the file as the model saw it, old names and
    all. The rename then sweeps the result, including what the hunks added.
    """
    (proj / "m.py").write_text("def fetch(url):\n    return get(url)\n\nfetch('a')\n")
    results = apply(
        "--- a/m.py\n"
        "! REPLACE fetch => download\n"  # written first, still runs last
        "--- a/m.py\n"
        "@ Add retries\n"
        "<<<<\n"
        "def fetch(url):\n"
        "====\n"
        "def fetch(url, retries=3):\n"
        ">>>>\n"
        "--- a/m.py\n"
        "<<<<\n"
        "fetch('a')\n"
        "====\n"
        "fetch('a')\n"
        "fetch('b')\n"
        ">>>>\n"
    )
    assert (proj / "m.py").read_text() == (
        "def download(url, retries=3):\n    return get(url)\n\n"
        "download('a')\ndownload('b')\n"
    )
    # Results follow execution order: hunks, then the directive.
    assert statuses(results) == ["APPLIED", "APPLIED", "APPLIED"]
    assert results[0]["items"][-1]["label"] == "REPLACE fetch => download"


def test_rename_in_a_file_the_patch_creates(proj):
    apply("--- a/new.py\n<<<<\n====\nold = 1\nprint(old)\n>>>>\n! REPLACE old => fresh\n")
    assert (proj / "new.py").read_text() == "fresh = 1\nprint(fresh)\n"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_rename_then_chmod(proj):
    (proj / "run.sh").write_text("#!/bin/sh\necho old\n")
    results = apply("--- a/run.sh\n! CHMOD +x\n! REPLACE old => new\n")
    assert (proj / "run.sh").read_text() == "#!/bin/sh\necho new\n"
    assert os.access(proj / "run.sh", os.X_OK)
    assert [i["label"] for i in results[0]["items"]] == ["REPLACE old => new", "CHMOD +x"]


def test_each_file_needs_its_own_directive(proj):
    (proj / "a.py").write_text("old\n")
    (proj / "b.py").write_text("old\n")
    apply("--- a/a.py\n! REPLACE old => new\n")
    assert (proj / "a.py").read_text() == "new\n"
    assert (proj / "b.py").read_text() == "old\n"


# --- backups, revert, checksums ------------------------------------------------


def test_backup_and_revert(proj):
    (proj / "m.py").write_text("count = 1\n")
    apply("--- a/m.py\n! REPLACE count => n\n")
    assert (proj / ".xtr" / "backup" / "m.py.orig").read_text() == "count = 1\n"
    revert_file("m.py")
    assert (proj / "m.py").read_text() == "count = 1\n"


def test_hunks_and_rename_share_one_backup(proj):
    (proj / "m.py").write_text("count = 1\n")
    apply("--- a/m.py\n<<<<\ncount = 1\n====\ncount = 2\n>>>>\n! REPLACE count => n\n")
    backups = sorted(p.name for p in (proj / ".xtr" / "backup").glob("m.py*.orig"))
    assert backups == ["m.py.orig"]
    revert_file("m.py")
    assert (proj / "m.py").read_text() == "count = 1\n"


def test_no_external_edit_warning_after_a_rename(proj, capsys):
    """The recorded checksum must describe the file as the rename left it."""
    (proj / "m.py").write_text("count = 1\nx = 0\n")
    apply("--- a/m.py\n<<<<\nx = 0\n====\nx = 1\n>>>>\n! REPLACE count => n\n")
    capsys.readouterr()
    apply("--- a/m.py\n<<<<\nx = 1\n====\nx = 2\n>>>>\n")
    assert "modified externally" not in capsys.readouterr().out

    apply("--- a/m.py\n! REPLACE n => total\n")
    capsys.readouterr()
    apply("--- a/m.py\n! REPLACE total => grand\n")
    assert "modified externally" not in capsys.readouterr().out


def test_external_edit_is_still_noticed_before_a_rename(proj, capsys):
    (proj / "m.py").write_text("count = 1\n")
    apply("--- a/m.py\n! REPLACE count => n\n")
    (proj / "m.py").write_text("n = 1\n# hand edit\n")
    capsys.readouterr()
    apply("--- a/m.py\n! REPLACE n => total\n")
    assert "modified externally" in capsys.readouterr().out


# --- results and the command line ----------------------------------------------


def test_result_labels(proj):
    (proj / "m.py").write_text("a b\n")
    results = apply("--- a/m.py\n@ Rename a\n! REPLACE a => x\n! REPLACE b => y\n")
    assert results[0]["items"] == [
        {"label": "Rename a", "auto": False, "status": "APPLIED"},
        {"label": "REPLACE b => y", "auto": True, "status": "APPLIED"},
    ]


def test_command_line(proj, monkeypatch, capsys):
    (proj / "m.py").write_text("count = 1\n")
    (proj / "p.patch").write_text("--- a/m.py\n! REPLACE count => n\n")
    monkeypatch.setattr(sys, "argv", ["xtrpatch", "p.patch"])
    with pytest.raises(SystemExit) as done:
        repatch.main()
    assert done.value.code in (0, None)
    assert (proj / "m.py").read_text() == "n = 1\n"
    assert (proj / ".xtr" / "backup" / "m.py.patch").exists()


def test_revert_from_the_patch_file(proj, monkeypatch):
    (proj / "m.py").write_text("count = 1\n")
    (proj / "p.patch").write_text("--- a/m.py\n! REPLACE count => n\n")
    for argv in (["xtrpatch", "p.patch"], ["xtrpatch", "--revert", "p.patch"]):
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit):
            repatch.main()
    assert (proj / "m.py").read_text() == "count = 1\n"


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
