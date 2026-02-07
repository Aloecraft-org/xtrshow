import pytest
from xtrshow.repatch import find_match, normalize

# --- Fixtures & Data ---

@pytest.fixture
def sample_file_content():
    """A sample file content simulating a Python script."""
    return [
        "import os\n",
        "\n",
        "def setup():\n",
        "    print('Setting up')\n",
        "    # Todo: add more setup\n",
        "\n",
        "def teardown():\n",
        "    print('Tearing down')\n",
        "\n",
        "def duplicate_func():\n",
        "    return True\n",
        "\n",
        "# Some space\n",
        "def duplicate_func():\n",
        "    return True\n"
    ]

# --- Unit Tests ---

def test_exact_match(sample_file_content):
    """Test 1: It should find an exact match."""
    search_block = [
        "def setup():",
        "    print('Setting up')",
        "    # Todo: add more setup"
    ]
    
    # Run matcher
    match = find_match(sample_file_content, search_block)
    
    assert match is not None
    start, end = match
    # 'def setup():' is at index 2 in sample_file_content
    assert start == 2
    # The block has 3 lines, so end should be 5
    assert end == 5

def test_whitespace_insensitivity(sample_file_content):
    """Test 2: It should match even if indentation differs (LLM error)."""
    # LLM output often uses 2 spaces instead of 4, or forgets indentation
    search_block = [
        "def setup():",
        "  print('Setting up')",  # 2 spaces (file has 4)
        "    # Todo: add more setup" # 4 spaces
    ]
    
    match = find_match(sample_file_content, search_block)
    
    assert match is not None
    assert sample_file_content[match[0]].startswith("def setup")

def test_disambiguation_with_hint(sample_file_content):
    """Test 3: It should use the line number hint to pick the right duplicate."""
    # 'duplicate_func' appears at line 10 and line 14 (indices 9 and 13)
    search_block = [
        "def duplicate_func():",
        "    return True"
    ]
    
    # Case A: Hint near line 10
    match_1 = find_match(sample_file_content, search_block, start_hint=10)
    assert match_1[0] == 9  # 0-indexed
    
    # Case B: Hint near line 15
    match_2 = find_match(sample_file_content, search_block, start_hint=15)
    assert match_2[0] == 13 # 0-indexed

def test_ambiguity_failure(sample_file_content):
    """Test 4: It should fail (return None) if multiple matches exist with no hint."""
    search_block = [
        "def duplicate_func():",
        "    return True"
    ]
    
    # No hint provided -> Should detect ambiguity
    match = find_match(sample_file_content, search_block, start_hint=None)
    
    # Expectation: The function prints an error and returns None to avoid damaging code
    assert match is None

def test_ignore_empty_lines_in_search(sample_file_content):
    """Test 5: It should ignore blank lines in the search block."""
    # LLMs often insert random blank lines in their output
    search_block = [
        "def teardown():",
        "",  # Extra blank line that isn't in the file
        "    print('Tearing down')"
    ]
    
    match = find_match(sample_file_content, search_block)
    
    assert match is not None
    assert sample_file_content[match[0]].startswith("def teardown")

def test_skip_file_comments(sample_file_content):
    """Test 6: It should skip over non-matching lines in file to find the block."""
    search_block = ["def teardown():"]
    match = find_match(sample_file_content, search_block)
    assert match is not None
    assert match[0] == 6  # index of teardown