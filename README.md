# xtrshow

<div align="center">

<img src="doc/icon.png" style="height:96px; width:96px;"/>

**Code Extraction & Patching Made Easy**

[![PyPI Version](https://img.shields.io/pypi/v/xtrshow.svg)](https://pypi.org/project/xtrshow/)
[![Python Versions](https://img.shields.io/pypi/pyversions/xtrshow.svg)](https://pypi.org/project/xtrshow/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

[![CI Status](https://github.com/Aloecraft-org/xtrshow/actions/workflows/main.yml/badge.svg)](https://github.com/Aloecraft-org/xtrshow/actions/workflows/main.yml)
[![Downloads](https://static.pepy.tech/badge/xtrshow)](https://pepy.tech/project/xtrshow)

</div>

`xtrshow` is a CLI suite designed to optimize the "Context Injection" and "Code Application" loop when working with AI coding assistants (ChatGPT, Claude, Gemini, etc.).

It solves the two biggest points of friction in AI-assisted development:
1.  **Getting code INTO the LLM:** Quickly selecting relevant files and formatting them so the model can reference exact lines.
2.  **Getting code OUT of the LLM:** Applying changes safely without manually copy-pasting dozens of snippets.

## Installation

```bash
pip install xtrshow
```

## `xtrshow` and `xtrpatch` Commands: Quickstart

The workflow consists of three steps: **Extract, Prompt, Apply**.

1. **Extract Context:** Run `xtrshow` to interactively select files and copy them to your clipboard.
```bash
xtrshow | pbcopy  # (MacOS/Linux)
```
2. **Prompt:** Paste the context into your LLM, then ask it to reply using the **Search & Replace Block** format. A copy-pasteable instruction block lives in the [Prompting Guide](doc/PROMPTING.md).
3. **Apply:** Save the LLM's response to a file (e.g., `changes.txt`) and apply it.
```bash
xtrpatch changes.txt
```

> **Tip:** Iterating on the same set of files? Skip reselection and re-export the last selection with `xtrshow --update`.

👉 **[Read the Full Getting Started Guide](doc/GETTING_STARTED.md)**

## Features

### `xtrshow` (The Extractor)

* **Interactive TUI:** Browse and select files with a fast, keyboard-driven interface.
* **LLM-Optimized Output:** Formats code with line numbers and file headers so the model can anchor edits to exact locations.
* **Smart Filtering:** Automatically ignores noise directories like `node_modules`, `.git`, and build artifacts.
* **Re-Export:** Re-run the last selection without touching the TUI via `--update`.
* **Multi-File Export:** Dump separate files for RAG pipelines via `--multi`.

### `xtrpatch` (The Patcher)

* **Safety First:** Automatic, versioned atomic backups for every modified file.
* **Checksum Verification:** Detects when a file has changed since its last backup, guarding against silent overwrites.
* **Robust Matching:** "Fuzzy" whitespace matching handles common LLM indentation errors.
* **Wildcard Anchors:** `~~~~` lets the model skip volatile interior lines and anchor only on stable signatures — dramatically reducing failed patches.
* **Conflict Detection:** Catches overlapping edit blocks before they corrupt a file.
* **Full Lifecycle:** Create files, delete sections, delete whole files (`! DELETE FILE`), and modify existing code.
* **Undo Button:** Built-in `--revert` command to instantly unwind changes.

👉 **[See Detailed Feature List](doc/FEATURES.md)**

## Prompting the LLM

To use `xtrpatch` effectively, instruct the LLM to output code as Search and Replace Blocks. Standard git diffs are often too fragile for LLM generation.

We provide a copy-pasteable instruction block for this purpose.

👉 **[Read the Prompting Guide](doc/PROMPTING.md)**

## Advanced Workflows

For power users of **Google Gemini**, we have developed a comprehensive "Developer Protocol" that turns the LLM into a more reliable pair programmer with persistent state management and standardized output formats.

👉 **[See the Gemini Protocol](doc/GEMINI.md)**

## License

Apache 2.0