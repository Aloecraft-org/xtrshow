import pytest
from xtrshow.repatch import parse_multi_file_patch, apply_changes

def test_pure_insertion_prepend(tmp_path, monkeypatch):
    """
    Test that an empty search block with hint 1 inserts at the top of the file.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "prepend.py"
    target.write_text("line1\nline2\n")
    
    # Prepend 'header'
    patch_content = f"""
--- a/{target.name}
<<<< 1
====
# header
====
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    content = target.read_text()
    assert content.startswith("# header\nline1")

def test_pure_insertion_middle(tmp_path, monkeypatch):
    """
    Test insertion at a specific line number (e.g. line 2).
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "middle.py"
    target.write_text("line1\nline3\n")
    
    # Insert 'line2' at line 2
    patch_content = f"""
--- a/{target.name}
<<<< 2
====
line2
====
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    lines = target.read_text().splitlines()
    assert lines[0] == "line1"
    assert lines[1] == "line2"
    assert lines[2] == "line3"

def test_pure_insertion_append(tmp_path, monkeypatch):
    """
    Test that a large hint appends to the end.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "append.py"
    target.write_text("line1\n")
    
    # Hint 50 (way past end)
    patch_content = f"""
--- a/{target.name}
<<<< 50
====
footer
====
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    content = target.read_text()
    assert content.strip().endswith("footer")
