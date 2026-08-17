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

````````md
# Agent Code Modification Format

- Output all changes as **Search/Replace Blocks**
- The entire response should be wrapped in one pair of **quadruple backticks** (````)
    + never triple backticks, even with multiple files or hunks.
- Hunk consists of,
    + a file header
    + comment
    + opening sequence w/ optional line hint
    + search block
    + replace block
    + optional tail context

**Operations:**

- **Modify:** search + replace.
- **Insert:** empty search + line hint (`<<<< 20`); add a tail line to anchor the spot.
- **Create file:** empty search block.
- **Delete section:** real search + empty replace.
- **Delete file:** `! DELETE FILE` on its own line (no block needed).
- **Replace file wholesale:** `! DELETE FILE`, then a create block for the same
  path. Use this instead of quoting a whole file into a search block.

**Syntax (Illustration only. Not the output wrapper):**

    --- a/path/to/file.py
    @ optional: describe the change
    <<<< LINE_HINT
    [code to find]
    ====
    [code to replace it with]
    ====
    [optional tail: line that must follow the match]
    >>>>

**Worked Example (this is what a real response looks like):**

``````
````
--- a/a.py
@ Add timeout to foo
<<<<
def foo():
====
def foo(timeout=30):
>>>>

--- a/a.py
@ Default msg param on bar
<<<< 11
def bar(msg):
====
def bar(msg=None):
>>>>

--- a/b.py
@ Set x to 2
<<<< 5:15
x = 1
====
x = 2
>>>>

--- a/b.py
@ Setup z in y builder
<<<<
# build y
y = builder.create_y() \
~~~~4
    .with_z() \
====
    .setup_z() \
>>>>


--- a/b.py
@ Setup j in i builder just before call to build()
<<<<
# build i
i = builder.create_i() \
    .with_j() \
    ~~~~=4
====
    .setup_j() \
====
    .build()
>>>>
````
``````

Worked Example Notes:

- search blocks must be an exact match (careful for whitespace and comments)
- each hunk has a comment explaining the change
- response is wrapped in quadruple backticks
- output has multiple patches across multiple files
- search block w/o line hint: `<<<<`
- exact match: `<<<< 11`
- fuzzy match: `<<<< 5:15`
- exact wildcard: `~~~~=4` (exactly 4 lines)
- fuzzy wildcard: `~~~~4` (as many as 4 lines)

**Anchoring Tips:**
- Anchor on stable lines (e.g. function/class signatures, unique declarations)
- Keep search blocks minimal. (Avoid replacing entire functions just to tweak a few lines)
- If a block appears twice, add a neighboring line or set `LINE_HINT` to disambiguate.
- Indentation is normalized. Don't fret leading whitespace.
- `LINE_HINT` (e.g. `<<<< 50` or `<<<< 50:60`) is a fuzzy nudge; the content match decides.
- Each hunk — even a second one for the same file — needs its own `--- a/path` header. (use the real path found inside a code dump (e.g. `src/utils.py`), not the container filename.)
- Tail context is useful for disambiguating hunks

````````

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

### Replace File Wholesale
Port a file to a new implementation without quoting the old one into a search
block. The delete and the create name the same path, in that order:

```text
--- a/src/bootstrap.sh
@ Alpine version, replaced wholesale below
! DELETE FILE

--- a/src/bootstrap.sh
@ Debian version
<<<<
====
#!/bin/bash
apt-get update
>>>>
```

The order matters. A create block on its own against a file that already exists
is refused, because that is also what a block that lost its search text looks
like, and the file would be truncated to the replace body on a guess.

---

## 4. Advanced Workflows (Gemini Gems / Custom GPTs)

If you use Google Gemini or ChatGPT frequently, you can bake these instructions into a persistent "Persona" or "Gem."

We provide a comprehensive Developer Protocol designed for Gemini, including:

* State Management (Planning vs. Implementing)
* Output Protocols (Scratchpads, Memos)
* Full `xtrpatch` syntax integration

👉 **See [GEMINI.md](GEMINI.md) for the full system prompt.**