import os
import pytest
from pathlib import Path
from xtrshow.repatch import apply_changes, parse_multi_file_patch, revert_file

def test_delete_existing_file(tmp_path):
    """
    Test that a file is deleted when Search and Replace blocks are both empty,
    AND that a backup is created first.
    """
    # 1. Setup
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    os.chdir(project_dir)
    
    target_file = project_dir / "deprecated.py"
    original_content = "def old_code():\n    pass\n"
    target_file.write_text(original_content)
    
    # 2. Define Deletion Patch (Empty Search, Empty Replace)
    patch_content = f"""
--- a/{target_file.name}
<<<<
====
>>>>
"""
    # 3. Apply
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    # 4. Assertions
    # File should be gone
    assert not target_file.exists()
    
    # Backup should exist
    backup = project_dir / ".xtrpatch" / "deprecated.py.orig"
    assert backup.exists()
    assert backup.read_text() == original_content

def test_delete_and_revert_lifecycle(tmp_path):
    """
    Test the full loop: Create -> Delete (via patch) -> Revert (via cli).
    This ensures 'undo' works even for deletions.
    """
    project_dir = tmp_path / "lifecycle_proj"
    project_dir.mkdir()
    os.chdir(project_dir)
    
    # Create File
    target = project_dir / "config.json"
    target.write_text('{"important": true}')
    
    # Delete it via Patch
    patch_content = f"--- a/config.json\n<<<<\n====\n>>>>"
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    assert not target.exists()
    
    # Revert it
    revert_file("config.json")
    
    # Assert Restoration
    assert target.exists()
    assert target.read_text() == '{"important": true}'

def test_mixed_delete_and_modify(tmp_path):
    """
    Test a patch file that modifies one file and deletes another.
    """
    project_dir = tmp_path / "mixed_proj"
    project_dir.mkdir()
    os.chdir(project_dir)
    
    file_keep = project_dir / "keep.py"
    file_del = project_dir / "del.py"
    
    file_keep.write_text("v1")
    file_del.write_text("I die today")
    
    patch_content = f"""
--- a/keep.py
<<<<
v1
====
v2
>>>>

--- a/del.py
<<<<
====
>>>>
"""
    changes = parse_multi_file_patch(patch_content)
    apply_changes(changes)
    
    # keep.py should be modified
    assert file_keep.read_text() == "v2\n"
    
    # del.py should be deleted
    assert not file_del.exists()
    assert (project_dir / ".xtrpatch" / "del.py.orig").exists()