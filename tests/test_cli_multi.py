import os
import sys
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from xtrshow.cli import main

def test_multi_default_directory(tmp_path, monkeypatch):
    """Test --multi without args defaults to .xtrshow directory"""
    
    # 1. Setup Environment
    monkeypatch.chdir(tmp_path)
    
    # Create a dummy file to "select"
    target_file = tmp_path / "src" / "main.py"
    target_file.parent.mkdir()
    target_file.write_text("print('hello')")
    
    # 2. Mock Curses to return our file
    # We mock curses.wrapper to bypass the TUI and return a pre-selected list
    with patch('xtrshow.cli.curses.wrapper', return_value=[str(target_file)]), \
         patch('sys.argv', ['xtrshow', '.', '--multi']):
        
        # 3. Run
        main()
        
    # 4. Verify Output
    output_dir = tmp_path / ".xtrshow"
    assert output_dir.exists()
    assert output_dir.is_dir()
    
    # Check filename flattening (src/main.py -> src__main.py.xtr.md)
    # Note: On Windows sep is \, on Linux /
    expected_name = str(target_file).replace(os.sep, "__") + ".xtr.md"
    output_file = output_dir / expected_name
    
    assert output_file.exists()
    content = output_file.read_text()
    assert "--- a/" in content
    assert "print('hello')" in content

def test_multi_custom_directory(tmp_path, monkeypatch):
    """Test --multi custom_dir creates that specific directory"""
    monkeypatch.chdir(tmp_path)
    f1 = tmp_path / "readme.md"
    f1.write_text("# Hi")
    
    custom_dir = "my_export"
    
    with patch('xtrshow.cli.curses.wrapper', return_value=[str(f1)]), \
         patch('sys.argv', ['xtrshow', '.', '--multi', custom_dir]):
        
        main()
        
    assert (tmp_path / custom_dir).exists()
    # Check that .xtrshow was NOT created
    assert not (tmp_path / ".xtrshow").exists()
    
    # Verify file is inside
    files = list((tmp_path / custom_dir).iterdir())
    assert len(files) == 1
    assert files[0].name.endswith(".xtr.md")

def test_multi_skips_creation_on_error(tmp_path, monkeypatch):
    """Test graceful exit if directory cannot be created"""
    monkeypatch.chdir(tmp_path)
    
    # Create a file named 'blocked' so we can't create a dir named 'blocked'
    (tmp_path / "blocked").write_text("I am a file")
    
    f1 = tmp_path / "test.txt"
    f1.write_text(" content")
    
    with patch('xtrshow.cli.curses.wrapper', return_value=[str(f1)]), \
         patch('sys.argv', ['xtrshow', '.', '--multi', 'blocked']), \
         patch('sys.stderr.write') as mock_stderr:
         
        main()
        
    # Should print error to stderr and NOT crash
    # And definitely not write files
    assert not (tmp_path / "blocked").is_dir()
