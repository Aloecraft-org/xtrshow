# Prompting Guide

**xtrshow** and **xtrpatch** are designed to work with *any* Large Language Model (ChatGPT, Claude, Gemini, DeepSeek, etc.).

However, LLMs are trained to output standard `diff` files or just rewrite whole files by default. To make `xtrpatch` work, you need to instruct the model to use the **Search and Replace Block** format.

---

## 1. Sharing Code

First, get your code into the LLM's context window.

1.  Run `xtrshow` in your terminal.
2.  Select the relevant files.
3.  Press `Enter` to output the formatted text.
4.  **Copy and Paste** the output directly into your chat prompt.

> **Tip:** On macOS, you can pipe directly to the clipboard:
> `xtrshow | pbcopy`


## 2. The "Magic" Instruction

When you ask for changes, you must tell the LLM **how** to format the code so `xtrpatch` can read it.

**Copy and paste the following block into your prompt (or save it as a Custom Instruction/System Prompt):**

```
**Code Output Formatting Instruction:**

Please provide all code changes using the **Multi-File Search and Replace Block** format. Do not use standard unified diffs or git patches.

**Output Formatting:**
* **CRITICAL:** Wrap your entire patch output in **quadruple backticks** (````) instead of triple backticks. This prevents markdown rendering errors.

**Patch Syntax:**
1.  **Header:** Start every file section with `--- a/path/to/file`.
2.  **Start Block:** `<<<< LINE_HINT` (e.g. `<<<< 50` or `<<<< 50~55`).
3.  **Original Code:** Paste the *exact* lines from the source code that need to be replaced. Do not use comments like `// ... existing code ...`.
4.  **Divider:** `====`
5.  **New Code:** Paste the new code to insert.
6.  **End Block:** `>>>>`

**Special Operations:**
* **Create File:** Use an empty Original Code block.
* **Delete File:** Use empty Original AND New Code blocks.

```

---

## 3. Format Reference

If the LLM is struggling, you can provide these examples to help it calibrate.

### Standard Modification
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

### File Creation

```text
--- a/src/new_helper.py
<<<<
====
def help_me():
    return True
>>>>

```

### File Deletion

```text
--- a/src/deprecated.py
<<<<
====
>>>>

```

### Advanced: Tail Context (Lookahead)

If you need to ensure a patch is applied in a specific location (e.g., distinguishing between two identical lines), you can add a **Tail Context** block using a second separator.

```text
--- a/config.ini
<<<<
version = 1
====
version = 2
====
# This line must exist immediately AFTER the block for the patch to apply
debug = True
>>>>

```

---

## 4. Advanced Workflows (Gemini Gems / Custom GPTs)

If you use Google Gemini or ChatGPT frequently, you can bake these instructions into a persistent "Persona" or "Gem."

We have provided a comprehensive Developer Protocol designed specifically for Gemini, which includes:

* State Management (Planning vs. Implementing)
* Output Protocols (Scratchpads, Memos)
* Full `xtrpatch` syntax integration

👉 **See [GEMINI.md](GEMINI.md) for the full system prompt.**