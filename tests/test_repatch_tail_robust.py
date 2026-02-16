import pytest
from xtrshow.repatch import parse_multi_file_patch, apply_changes

def test_tail_robust_file_has_extra_blanks(tmp_path, monkeypatch):
    """
    Scenario: The file has extra blank lines between the patch target 
    and the tail context. The patcher should skip them and find the match.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "robust_a.py"
    target.write_text("old_code\n\n\n\nverify_me\n")
    
    START = "<" * 4
    MID = "=" * 4
    END = ">" * 4

    patch_content = f"""
--- a/{target.name}
{START}
old_code
{MID}
new_code
{MID}
verify_me
{END}
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    # Should apply successfully despite 3 blank lines in file
    assert "new_code" in target.read_text()

def test_tail_robust_patch_has_extra_blanks(tmp_path, monkeypatch):
    """
    Scenario: The patch definition has blank lines in the tail (maybe due 
    to copy-paste formatting), but the file is tight. Patcher should ignore
    the blanks in the tail definition.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "robust_b.py"
    target.write_text("old_code\nverify_me\n")
    
    START = "<" * 4
    MID = "=" * 4
    END = ">" * 4

    # Tail block has empty lines surrounding the verification code
    patch_content = f"""
--- a/{target.name}
{START}
old_code
{MID}
new_code
{MID}

verify_me

{END}
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    assert "new_code" in target.read_text()

def test_tail_robust_mismatch_fails(tmp_path, capsys, monkeypatch):
    """
    Scenario: Even with robust matching, actual content mismatches 
    should still fail the patch.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "robust_c.py"
    target.write_text("old_code\n\nwrong_verification\n")
    
    START = "<" * 4
    MID = "=" * 4
    END = ">" * 4

    patch_content = f"""
--- a/{target.name}
{START}
old_code
{MID}
new_code
{MID}
correct_verification
{END}
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    # Should NOT change the file
    assert "old_code" in target.read_text()
    
    captured = capsys.readouterr()
    assert "Tail context mismatch" in captured.out