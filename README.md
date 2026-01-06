# xtrshow

Interactive file tree selector for sharing code with LLMs

## Installation
```bash
pip install xtrshow
```

## Usage
```bash
xtrshow .                    # Browse current directory
xtrshow /path/to/dir         # Browse specific directory
xtrshow . --max-depth 2      # Limit depth
xtrshow . --pattern ".py"    # Filter by pattern
```

Select files with arrow keys and space, press Enter to output.