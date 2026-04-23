import pytest
from xtrshow.repatch import parse_multi_file_patch, apply_changes

def test_loose_syntax_create_file(tmp_path, monkeypatch):
    """Test that '<<' works for file creation (empty search block)."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "loose.py"
    
    # Using '<<' instead of '<<<<'
    patch_content = f"""
--- a/{target.name}
<<
====
print("Created with loose syntax")
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    assert target.exists()
    assert 'print("Created with loose syntax")' in target.read_text()

def test_loose_syntax_with_hint(tmp_path, monkeypatch):
    """Test that '<< 10' works."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "hint.py"
    target.write_text("line1\nline2\nline3\n")
    
    patch_content = f"""
--- a/{target.name}
<< 2
line2
====
line2_modified
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    assert "line2_modified" in target.read_text()

def test_loose_syntax_safeguard_ignores_code(tmp_path, monkeypatch):
    """
    SAFETY CHECK: Ensure lines like '<< some_variable' do NOT trigger a block start.
    This protects against C++ streams or bitwise shifts being mistaken for patches.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "safety.cpp"
    target.write_text("int x = 1;\n")
    
    # The line '<< "text"' looks like a marker but has content after it.
    # The regex '$' anchor should reject this.
    patch_content = f"""
--- a/{target.name}
@ This block should be ignored because the header is invalid
<< "not a hint"
int x = 1;
====
int x = 2;
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    
    # If the parser was too loose, it would find changes. It should find none.
    if changes:
        apply_changes(changes)
        
    assert "int x = 1;" in target.read_text()
    assert "int x = 2;" not in target.read_text()

def test_loose_syntax_requires_strict_closing(tmp_path, monkeypatch):
    """
    Verify we allow '<<' to OPEN, but we do NOT allow '>>' to CLOSE.
    Closing must still be '>>>>'.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "strict_close.py"
    target.write_text("old\n")
    
    # Invalid patch: uses '>>' instead of '>>>>'
    patch_content = f"""
--- a/{target.name}
<<
old
====
new
>>
"""
    changes = parse_multi_file_patch(patch_content)
    
    # The parser logic consumes lines looking for '>>>>'. 
    # If it hits EOF without finding '>>>>', the block is usually discarded 
    # or treated as incomplete depending on implementation details.
    # In current implementation, if it doesn't find '>>>>', the block isn't added to `changes`.
    
    assert target.name not in changes or len(changes[target.name]) == 0