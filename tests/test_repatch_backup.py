import os
import shutil
from pathlib import Path
from xtrshow.repatch import apply_changes, create_backup

def test_backup_creation(tmp_path):
    """Test that applying changes creates a valid backup file in .xtrpatch/"""
    
    # Setup: Create a fake project structure
    # /tmp/proj/src/main.py
    project_dir = tmp_path / "proj"
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)
    
    target_file = src_dir / "main.py"
    original_content = "def hello():\n    print('world')\n"
    target_file.write_text(original_content)
    
    # Change CWD to project_dir so relative paths work as expected
    os.chdir(project_dir)
    
    # Define a patch
    changes = {
        "src/main.py": [{
            'hint': None,
            'search': ["def hello():", "    print('world')"],
            'replace': ["def hello():", "    print('patched')"]
        }]
    }
    
    # Run the patcher
    apply_changes(changes)
    
    # Assertions
    
    # 1. Verify the file was actually patched
    assert "print('patched')" in target_file.read_text()
    
    # 2. Verify backup directory exists
    backup_dir = project_dir / ".xtrpatch"
    assert backup_dir.exists()
    assert backup_dir.is_dir()
    
    # 3. Verify backup file exists at correct subpath
    # .xtrpatch/src/main.py.orig
    backup_file = backup_dir / "src" / "main.py.orig"
    assert backup_file.exists()
    
    # 4. Verify backup content matches ORIGINAL content
    assert backup_file.read_text() == original_content
    assert "print('patched')" not in backup_file.read_text()

def test_backup_nested_structure(tmp_path):
    """Test deep nesting logic for backups"""
    project_dir = tmp_path / "deep_proj"
    target_file = project_dir / "a" / "b" / "c" / "script.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("old_content")
    
    os.chdir(project_dir)
    
    changes = {
        str(Path("a/b/c/script.py")): [{
            'hint': None,
            'search': ["old_content"],
            'replace': ["new_content"]
        }]
    }
    
    apply_changes(changes)
    
    backup_file = project_dir / ".xtrpatch" / "a" / "b" / "c" / "script.py.orig"
    assert backup_file.exists()
    assert backup_file.read_text() == "old_content"