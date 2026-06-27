# Prompting Guide

**xtrshow** and **xtrpatch** are designed to work with *any* Large Language Model (ChatGPT, Claude, Gemini, DeepSeek, etc.).

However, LLMs default to outputting standard `diff` files or rewriting whole files. To make `xtrpatch` work, instruct the model to use the **Search and Replace Block** format below.

---

## 1. Sharing Code

First, get your code into the LLM's context window.

1.  Run `xtrshow` in your terminal.
2.  Select the relevant files.
3.  Press `Enter` to output the formatted text.
4.  **Copy and Paste** the output directly into your chat prompt.

> **Tip:** On macOS/Linux, pipe directly to the clipboard:
> `xtrshow | pbcopy`
>
> Working on the same fileset again later? Re-export without reselecting:
> `xtrshow --update`

---

## 2. Prompt for LLMs

Tell the LLM **how** to format its output so `xtrpatch` can read it. Copy the block below into your prompt (or save it as a Custom Instruction / System Prompt):

`````md
**Instruction: Code Modification Format**

Output all changes as **Search/Replace Blocks**, wrapped entirely in **quadruple backticks** (````) to avoid rendering errors.

```text
--- a/path/to/file.py
@ optional: describe the change
<<<< LINE_HINT
[code to find]
====
[code to replace it with]
====
[optional tail: line that must follow the match]
>>>>
```

**Anchoring — this is what prevents failures:**
- Anchor on stable lines: function/class signatures, unique declarations. Avoid anchoring on comments, strings, or blanks — they drift between context and edit time.
- Don't copy whole functions. Anchor the first line, `~~~~` to skip the volatile middle, anchor a closing line:

```text
<<<< 40
def process(items):
~~~~
    return result
====
def process(items, timeout=30):
    return result
>>>>
```

- `~~~~` skips any number of lines; `~~~~5` up to 5; `~~~~=5` exactly 5. Search side only.
- Keep the search block as small as stays unique. If a block appears twice, add a neighboring line or set `LINE_HINT` to disambiguate.
- Indentation is normalized — don't fret exact whitespace.
- `LINE_HINT` (e.g. `<<<< 50` or `<<<< 50:60`) is a fuzzy nudge; the content match decides.
- Path: use the real path found inside a code dump (e.g. `src/utils.py`), not the container filename.

**Operations:**
- **Modify:** search + replace.
- **Insert:** empty search + line hint (`<<<< 20`); add a tail line to anchor the spot.
- **Create file:** empty search block.
- **Delete section:** real search + empty replace.
- **Delete file:** `! DELETE FILE` on its own line (no block needed).

**Tail context** pins what must come *immediately after* a match — useful to place an edit precisely when the search alone is ambiguous:

```text
--- a/config.ini
<<<<
version = 1
====
version = 2
====
debug = True
>>>>
```
`````

---

## 3. Format Reference

Quick reference for each operation.

### Modify
```text
--- a/src/main.py
<<<< 10
def hello():
    print("Old")
====
def hello():
    print("New")
>>>>
```

### Wildcard (skip volatile interior)
```text
--- a/src/main.py
<<<< 10
def hello(name):
~~~~
    return greeting
====
def hello(name, formal=False):
    return greeting
>>>>
```

### Insert (empty search + hint + tail)
```text
--- a/src/main.py
<<<< 16
====
    x = 2
====
    return x
>>>>
```

### Create File
```text
--- a/src/new_helper.py
<<<<
====
def help_me():
    return True
>>>>
```

### Delete Section
```text
--- a/src/main.py
<<<<
    deprecated_call()
====
>>>>
```

### Delete File
```text
--- a/src/deprecated.py
! DELETE FILE
```

---

## 4. Advanced Workflows (Gemini Gems / Custom GPTs)

If you use Google Gemini or ChatGPT frequently, you can bake these instructions into a persistent "Persona" or "Gem."

We provide a comprehensive Developer Protocol designed for Gemini, including:

* State Management (Planning vs. Implementing)
* Output Protocols (Scratchpads, Memos)
* Full `xtrpatch` syntax integration

👉 **See [GEMINI.md](GEMINI.md) for the full system prompt.**