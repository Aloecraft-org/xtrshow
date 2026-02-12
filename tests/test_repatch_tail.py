import os
import pytest
from pathlib import Path
from xtrshow.repatch import apply_changes, parse_multi_file_patch

def test_tail_context_success(tmp_path):
    """
    Test that a patch applies when the tail context (lookahead) matches.
    """
    target_file = tmp_path / "main.rs"
    target_file.write_text("fn main() {\n    let x = 1;\n    let y = 2;\n    println!(\"{}\", x);\n}\n")
    
    # Patch: Change x=1 to x=10, BUT only if followed by y=2
    patch_content = f"""
--- a/{target_file}
<<<<
    let x = 1;
====
    let x = 10;
====
    let y = 2;
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    # Assert: Change was applied
    content = target_file.read_text()
    assert "let x = 10;" in content
    assert "let y = 2;" in content

def test_tail_context_mismatch_skips_patch(tmp_path):
    """
    Test that a patch is ABORTED if the tail context does not match.
    This prevents applying a patch in the wrong location.
    """
    target_file = tmp_path / "config.ini"
    target_file.write_text("[settings]\nversion=1\ndebug=true\n")
    
    # Patch: Change version=1 to version=2
    # Requirement: Must be followed by 'debug=false' (Lookahead)
    # Reality: File has 'debug=true'
    patch_content = f"""
--- a/{target_file}
<<<<
version=1
====
version=2
====
debug=false
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    # Assert: Change was NOT applied because tail matched 'debug=true', not 'false'
    content = target_file.read_text()
    assert "version=1" in content
    assert "version=2" not in content

def test_tail_context_eof_safety(tmp_path):
    """
    Test that we don't crash if the tail context goes past the End of File.
    """
    target_file = tmp_path / "notes.txt"
    target_file.write_text("End of the file.\n")
    
    # Patch: Replace the last line
    # Requirement: Expects another line "footer" after it.
    patch_content = f"""
--- a/{target_file}
<<<<
End of the file.
====
New End.
====
footer
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    # Assert: Skipped because "footer" does not exist (EOF)
    assert "End of the file." in target_file.read_text()

def test_fuzzy_tail_matching(tmp_path):
    """
    Test that tail matching honors whitespace normalization (fuzzy matching).
    """
    target_file = tmp_path / "code.py"
    # File has weird spacing
    target_file.write_text("def init():\n    pass\n    # comment  \n")
    
    # Patch uses standard spacing in tail
    patch_content = f"""
--- a/{target_file}
<<<<
    pass
====
    return
====
    # comment
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    # Assert: Applied despite whitespace differences in the comment
    assert "return" in target_file.read_text()