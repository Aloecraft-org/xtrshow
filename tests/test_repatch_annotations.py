import pytest
from xtrshow.repatch import parse_multi_file_patch, apply_changes

def test_parse_annotation():
    """
    Verify that lines starting with '@ ' are captured as annotations
    and attached to the subsequent patch block.
    """
    # Use constructed strings to avoid confusing the patch parser reading THIS file
    START = "<" * 4
    MID = "=" * 4
    END = ">" * 4
    
    patch_content = f"""
--- a/src/logic.py
@ Fix off-by-one error in loop
{START}
for i in range(10):
{MID}
for i in range(11):
{END}
"""
    changes = parse_multi_file_patch(patch_content)
    
    assert 'src/logic.py' in changes
    block = changes['src/logic.py'][0]
    assert block['annotation'] == "Fix off-by-one error in loop"

def test_annotation_reset_between_blocks():
    """
    Verify that an annotation only applies to the immediate next block
    and doesn't "leak" to subsequent blocks.
    """
    START = "<" * 4
    MID = "=" * 4
    END = ">" * 4

    patch_content = f"""
--- a/file.py
@ Change A
{START}
A
{MID}
A_Prime
{END}

{START}
B
{MID}
B_Prime
{END}
"""
    changes = parse_multi_file_patch(patch_content)
    blocks = changes['file.py']
    
    # First block should have the annotation
    assert blocks[0]['annotation'] == "Change A"
    
    # Second block should have NO annotation (None)
    assert blocks[1]['annotation'] is None

def test_apply_prints_annotation_on_success(tmp_path, capsys, monkeypatch):
    """
    Verify that the tool prints the annotation ("Goal: ...") when 
    successfully applying a patch.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "success.py"
    target.write_text("old_code\n")
    
    START = "<" * 4
    MID = "=" * 4
    END = ">" * 4

    patch_content = f"""
--- a/{target.name}
@ Refactoring old code
{START}
old_code
{MID}
new_code
{END}
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    # Capture stdout
    captured = capsys.readouterr()
    
    # Check output
    assert "✅ SUCCESS" in captured.out
    assert "@ Refactoring old code" in captured.out

def test_apply_prints_annotation_on_failure(tmp_path, capsys, monkeypatch):
    """
    Verify that the failure message includes the annotation.
    This is CRITICAL for the LLM self-correction loop.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "fail.py"
    target.write_text("mismatch_content\n")
    
    START = "<" * 4
    MID = "=" * 4
    END = ">" * 4

    patch_content = f"""
--- a/{target.name}
@ Adding validation logic
{START}
target_content
{MID}
new_content
{END}
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    captured = capsys.readouterr()
    
    # Verify standard failure message
    assert "❌ FAILED" in captured.out
    # Verify our annotation is attached to the error line
    assert "@ Adding validation logic" in captured.out

def test_multiple_annotations_per_file(tmp_path, capsys, monkeypatch):
    """
    Verify that we can have multiple patches in one file, each with 
    its own specific annotation (Goal), and they don't overwrite each other.
    """
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "multi.py"
    target.write_text("func_a\n\nfunc_b\n")
    
    START = "<" * 4
    MID = "=" * 4
    END = ">" * 4

    patch_content = f"""
--- a/{target.name}
@ Update A
{START}
func_a
{MID}
func_a_v2
{END}

@ Update B
{START}
func_b
{MID}
func_b_v2
{END}
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    captured = capsys.readouterr()
    
    # Check that both annotations were printed
    assert "@ Update A" in captured.out
    assert "@ Update B" in captured.out
    
    # Verify file content
    content = target.read_text()
    assert "func_a_v2" in content
    assert "func_b_v2" in content