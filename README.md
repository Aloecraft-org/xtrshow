# xtrshow

<div align="center">

<img src="doc/icon.png" style="height:96px; width:96px;"/>

**The bridge between your local codebase and LLMs.**

[![PyPI Version](https://img.shields.io/pypi/v/xtrshow.svg)](https://pypi.org/project/xtrshow/)
[![Python Versions](https://img.shields.io/pypi/pyversions/xtrshow.svg)](https://pypi.org/project/xtrshow/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

[![CI Status](https://github.com/Aloecraft-org/xtrshow/actions/workflows/main.yml/badge.svg)](https://github.com/Aloecraft-org/xtrshow/actions/workflows/main.yml)
[![Downloads](https://static.pepy.tech/badge/xtrshow)](https://pepy.tech/project/xtrshow)


</div>

`xtrshow` is a lightweight CLI suite designed to optimize the "Context Injection" and "Code Application" loop when working with AI coding assistants (ChatGPT, Claude, Gemini, etc.).

It consists of two tools:
1.  **`xtrshow`**: A TUI to select, compress, and format code context for your LLM.
2.  **`xtrpatch`**: A surgical patching tool to apply LLM-generated changes back to your source code safely.

## Installation

```bash
pip install xtrshow
```

## The Workflow

### 1. Extract Context (`xtrshow`)

Stop manually copying and pasting files.

Run `xtrshow` in your directory. Navigate with arrow keys, select files with `Space`, and hit `Enter` (or use `-o` to save to a file).

```bash
# Open interactive TUI
xtrshow

# Or pipe directly to clipboard (Mac/Linux)
xtrshow | pbcopy 
```

The output is formatted specifically for LLMs, including file paths and line numbers (enabled by default) to assist in referencing specific code blocks.

### 2. Prompt the LLM

Paste the output into your LLM. When asking for changes, include the following instruction to get a compatible patch:

> "Provide changes using the Multi-File Search and Replace Block format."

### 3. Apply Changes (`xtrpatch`)

Save the LLM's response to a file (e.g., `response.txt`) and apply it:

```bash
xtrpatch response.txt
```

`xtrpatch` is whitespace-insensitive and uses fuzzy matching, making it significantly more robust than standard `git apply` when dealing with LLM hallucinations or formatting errors.

---

## Features

### Safety First (Atomic Backups)

`xtrpatch` never destroys code.

* Every time a file is patched, the original is backed up to `.xtrpatch/<file>.orig`.
* Backups are versioned (`file.py.orig`, `file.py.1.orig`, `file.py.2.orig`).
* The patch itself is archived alongside the backup.

### Reverting

Made a mistake? You can unwind changes easily:

```bash
# Revert a specific file to its state before the last patch
xtrpatch --revert src/main.py

# Revert all files modified by a specific patch file
xtrpatch --revert response.txt

```

### File Creation

If the LLM wants to create a new file, `xtrpatch` handles that too.

```text
--- a/src/new_feature.py
<<<<
====
def hello():
    print("New file created!")
>>>>

```

## Patch Format Specification

`xtrpatch` uses a custom, hallucination-resistant format:

```text
--- a/path/to/file.py
<<<< 50
def old_function():
    return False
====
def old_function():
    return True
>>>>

```

* **Header:** `--- a/path/to/file`
* **Start:** `<<<< LINE_HINT` or `<<<< START~END` (e.g., `<<<< 50~55`). The `~` indicates an approximate range/fuzzy hint.
* **Search Block:** The existing code to find.
* **Divider:** `====`
* **Replace Block:** The new code.
* **Divider (Optional):** `====` (Use a second divider to provide Tail Context).
* **Tail Context (Optional):** Code that must exist *immediately after* the block to verify location.
* **End:** `>>>>`

### Example with Tail Context

```text
--- a/src/main.rs
<<<< 10~15
    let x = 1;
    let y = 2;
====
    let x = 10;
    let y = 20;
====
    // This line must exist after the block for the patch to apply
    println!("Calculating...");
>>>>
```

## License

Apache 2.0