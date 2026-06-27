# ./tests/test_wildcard_match.py
# License: Apache-2.0 (disclaimer at bottom of file)
import pytest
from xtrshow.repatch import (
    find_match,
    parse_multi_file_patch,
    apply_changes,
    _parse_wildcard,
    _split_on_wildcards,
)


# ---------------------------------------------------------------------------
# Unit: _parse_wildcard
# ---------------------------------------------------------------------------

def test_parse_wildcard_bare():
    assert _parse_wildcard("~~~~") == (True, None, False)

def test_parse_wildcard_bounded():
    assert _parse_wildcard("~~~~4") == (True, 4, False)
    assert _parse_wildcard("  ~~~~10  ") == (True, 10, False)

def test_parse_wildcard_exact():
    assert _parse_wildcard("~~~~=3") == (True, 3, True)

def test_parse_wildcard_not_wildcard():
    assert _parse_wildcard("normal line")[0] is False
    assert _parse_wildcard("~~~~ some text")[0] is False  # has trailing non-numeric content


# ---------------------------------------------------------------------------
# Unit: _split_on_wildcards
# ---------------------------------------------------------------------------

def test_split_no_wildcards():
    segs = _split_on_wildcards(["a", "b", "c"])
    assert len(segs) == 1
    assert segs[0] == (["a", "b", "c"], None, None)

def test_split_one_wildcard():
    segs = _split_on_wildcards(["a", "~~~~", "b"])
    assert len(segs) == 2
    assert segs[0] == (["a"], None, False)
    assert segs[1] == (["b"], None, None)

def test_split_bounded_wildcard():
    segs = _split_on_wildcards(["a", "~~~~3", "b"])
    assert segs[0] == (["a"], 3, False)

def test_split_exact_wildcard():
    segs = _split_on_wildcards(["a", "~~~~=2", "b"])
    assert segs[0] == (["a"], 2, True)


# ---------------------------------------------------------------------------
# Integration: find_match with wildcards
# ---------------------------------------------------------------------------

FILE = [
    "def foo():\n",         # 0
    "    x = 1\n",          # 1
    "    y = 2\n",          # 2
    "    z = 3\n",          # 3
    "    return x\n",       # 4
    "\n",                   # 5
    "def bar():\n",         # 6
    "    a = 10\n",         # 7
    "    return a\n",       # 8
]

def test_unbounded_wildcard_matches():
    """~~~~ skips any number of lines between anchors."""
    search = ["def foo():", "~~~~", "return x"]
    match = find_match(FILE, search)
    assert match is not None
    assert match[0] == 0

def test_bounded_wildcard_within_limit():
    """~~~~3 succeeds when anchor is within 3 content lines."""
    # def foo(): -> x=1, y=2, z=3 -> return x  (3 lines skipped)
    search = ["def foo():", "~~~~3", "return x"]
    match = find_match(FILE, search)
    assert match is not None
    assert match[0] == 0

def test_bounded_wildcard_at_limit():
    """~~~~3 succeeds when anchor is exactly 3 content lines away."""
    search = ["def foo():", "~~~~3", "return x"]
    match = find_match(FILE, search)
    assert match is not None

def test_bounded_wildcard_exceeds_limit():
    """~~~~2 fails when anchor is 3 content lines away."""
    search = ["def foo():", "~~~~2", "return x"]
    match = find_match(FILE, search)
    assert match is None

def test_exact_wildcard_correct():
    """~~~~=3 succeeds when anchor is exactly 3 content lines away."""
    search = ["def foo():", "~~~~=3", "return x"]
    match = find_match(FILE, search)
    assert match is not None

def test_exact_wildcard_wrong_count():
    """~~~~=2 fails when anchor is 3 content lines away."""
    search = ["def foo():", "~~~~=2", "return x"]
    match = find_match(FILE, search)
    assert match is None

def test_wildcard_disambiguates_duplicates():
    """~~~~  with start_hint picks the right duplicate."""
    file_lines = [
        "def process():\n",   # 0
        "    return 1\n",     # 1
        "\n",
        "def process():\n",   # 3
        "    return 2\n",     # 4
    ]
    search = ["def process():", "~~~~", "return 2"]
    match = find_match(file_lines, search, start_hint=4)
    assert match is not None
    assert match[0] == 3

def test_existing_tests_unaffected():
    """Non-wildcard searches still work exactly as before."""
    file_lines = [
        "import os\n",
        "\n",
        "def setup():\n",
        "    print('Setting up')\n",
        "    # Todo: add more setup\n",
    ]
    search = ["def setup():", "    print('Setting up')", "    # Todo: add more setup"]
    match = find_match(file_lines, search)
    assert match is not None
    assert match[0] == 2


# ---------------------------------------------------------------------------
# End-to-end: apply_changes with wildcard search blocks
# ---------------------------------------------------------------------------

def test_apply_wildcard_unbounded(tmp_path, monkeypatch):
    """Wildcard patch replaces only the matched anchor lines; interior lines are preserved."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "app.py"
    target.write_text(
        "def process(items):\n"
        "    validated = validate(items)\n"
        "    result = run(validated)\n"
        "    return result\n"
    )

    START, MID, END = "<" * 4, "=" * 4, ">" * 4
    patch_content = f"""
--- a/{target.name}
{START}
def process(items):
~~~~
    return result
{MID}
def process(items, timeout=30):
    return result
{END}
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)

    content = target.read_text()
    assert "def process(items, timeout=30):" in content
    assert "return result" in content


def test_apply_wildcard_bounded_fail(tmp_path, monkeypatch, capsys):
    """Bounded wildcard that exceeds its limit produces FAILED status."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "fail.py"
    target.write_text(
        "def foo():\n"
        "    a = 1\n"
        "    b = 2\n"
        "    c = 3\n"
        "    return a\n"
    )

    START, MID, END = "<" * 4, "=" * 4, ">" * 4
    patch_content = f"""
--- a/{target.name}
{START}
def foo():
~~~~2
    return a
{MID}
def foo():
~~~~2
    return 42
{END}
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)

    captured = capsys.readouterr()
    # 3 content lines between anchors, bound is 2 — should fail
    assert "return 42" not in target.read_text()
    assert "FAILED" in captured.out
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