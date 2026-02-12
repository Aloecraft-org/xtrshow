# Getting Started

**xtrshow** is a CLI suite for extracting codebase context and applying surgical patches. It consists of two binaries: `xtrshow` (extraction) and `xtrpatch` (application).

## Installation

```bash
pip install xtrshow

```

---

## 1. Extracting Code (`xtrshow`)

`xtrshow` provides a Terminal User Interface (TUI) to select files and format them into a dense, annotated Markdown block.

### Interactive Mode

Run without arguments to open the file explorer:

```bash
xtrshow

```

* **Navigation:** Arrow keys (`↑`, `↓`, `←`, `→`).
* **Selection:** `Space` to toggle files/directories. `a`/`A` to select/deselect all in current view.
* **Export:** `Enter` to dump selected content to stdout.

### CLI Flags & Filtering

You can filter the view or modify output behavior using flags:

```bash
# Filter by filename/extension
xtrshow --pattern ".py"

# Limit recursion depth
xtrshow --max-depth 2

# Output raw text (no line numbers)
xtrshow --clean

# Save output to a file instead of stdout
xtrshow -o context.md

```

### Multi-File Export

For pipelines that require distinct files rather than a single concatenated block (e.g., RAG ingestion), use `--multi`.

```bash
# Exports selected files to the .xtrshow/ directory
xtrshow --multi

# Exports to a custom directory
xtrshow --multi ./my_export_dir

```

---

## 2. Applying Changes (`xtrpatch`)

`xtrpatch` reads a text file containing "Search and Replace" blocks and applies them to your codebase. It uses fuzzy matching (whitespace insensitivity) to handle formatting inconsistencies.

### Basic Usage

1. Save your patch content to a file (e.g., `changes.patch`).
2. Run the patcher:

```bash
xtrpatch changes.patch

```

### Safety & Versioning

`xtrpatch` is non-destructive. Every operation performs an atomic backup before modification.

* **Backups Location:** `.xtrpatch/<relative_path>/<filename>.version.orig`
* **Patch Archive:** The patch file used is archived alongside the backup (`.patch`).

### Reverting Changes

You can unwind changes immediately if a patch produces unexpected results.

```bash
# Revert a specific file to its previous state
xtrpatch --revert src/main.py

# Revert all files targeted by a specific patch file
xtrpatch --revert changes.patch

```

---

## 3. Patch File Specification

For `xtrpatch` to function, the input file must adhere to the **Multi-File Search and Replace** format.

### Standard Block

```text
--- a/path/to/target.py
<<<< LINE_HINT
[Exact Source Content]
====
[New Content]
>>>>

```

* **Header:** `--- a/path/to/file` (Standard diff format).
* **Start:** `<<<<` followed by an optional line number hint (e.g., `<<<< 50`) or range (`<<<< 50~55`).
* **Search:** The content to find. Must match textual content exactly (whitespace is normalized).
* **Divider:** `====`.
* **Replace:** The content to insert.
* **End:** `>>>>`.

### File Creation

To create a file, provide an **empty Search block**.

```text
--- a/src/new_file.py
<<<<
====
print("Hello World")
>>>>

```

### File Deletion

To delete a file, provide **empty Search AND Replace blocks**.

```text
--- a/src/deprecated.py
<<<<
====
>>>>

```

### Tail Context (Lookahead)

To ensure uniqueness, you can verify the lines *following* the replacement block by adding a second `====` section.

```text
--- a/config.py
<<<<
version = 1
====
version = 2
====
# This line must exist immediately after 'version = 1' for the patch to apply
debug = True
>>>>

```