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

`````md
**Instruction: Code Modification Format**

Please provide all code changes using the **Multi-File Search and Replace Block** format.
**CRITICAL:** Wrap your *entire* output in **quadruple backticks** (````) to prevent rendering errors.

**Syntax:**

```text
--- a/path/to/target_file.py
@ patch annotation describing modification
<<<< LINE_HINT
[Original Code Block]
====
[New Code Block]
====
[Optional: Tail Context]
>>>>

```
**Rules:**

1. **Header:** `--- a/path/to/file`.
2. **Path Resolution:** If source code is provided in a single dump (e.g. `x.md`), use the **actual file path** found *inside* the text (e.g. `src/utils.py`), not the container filename.
3. **Start:** `<<<<` followed by a line number hint (e.g., `<<<< 50`). This is a fuzzy anchor; rely on the content match for precision.
4. **Search:** Copy the *exact* original code to replace. No comments or placeholders.
5. **Replace:** The new code to insert.
6. **Tail Context (Optional):** Use a second `====` divider to provide 1-2 lines of code that must exist *immediately after* the replacement. Use this to anchor small inserts without quoting large blocks.
7. **End:** `>>>>`.

**Operations:**

* **Modify:** Provide Search and Replace blocks. Ensure the Search block is unique.
* **Create:** Empty Search block (`<<<<\n====`).
* **Delete:** Empty Search AND Replace blocks (`<<<<\n====\n>>>>`).

**Example (Anchoring an insert ~line 20):**

```text
--- a/src/main.py
<<<< 16:24
    x = 1
====
    x = 2
====
    # This line confirms we are inserting before 'return x'
    return x
>>>>
```

**Annotation:**

You may optionally precede a block with a line starting with @  to describe the intent of the specific change. This helps with debugging if the patch fails.

**Example:**

````
--- a/src/main.py
@ Fixes off-by-one error in loop
<<<< 16:24
    x = 1
====
    x = 2
====
    # This line confirms we are inserting before 'return x'
    return x
>>>>
````

`````

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