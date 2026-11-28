# Getting Started

**xtrshow** is a CLI suite for extracting codebase context and applying surgical patches. It installs two commands: `xtrshow` (extraction) and `xtrpatch` (application).

## Installation

```bash
pip install xtrshow
```

Requires Python ≥ 3.8. Windows is supported (curses is bundled automatically).

---

## 1. Extracting Code (`xtrshow`)

`xtrshow` opens a Terminal User Interface (TUI) to select files, then formats them into a dense, line-numbered Markdown block on stdout.

### Interactive Mode

```bash
xtrshow              # browse current directory
xtrshow path/to/dir  # browse a specific directory
```

**Keys:**

| Key | Action |
| --- | --- |
| `↑` / `↓` | Move cursor |
| `←` / `→` | Collapse/expand directory (or jump to parent/first child) |
| `Space` | Toggle selection |
| `a` / `A` | Select / deselect everything under the cursor |
| `p` or `Enter` | Confirm and export |
| `q` | Quit without output |

The status bar shows the running count and total size of your selection — useful for staying inside a model's context budget.

### CLI Flags

```bash
xtrshow --pattern ".py"     # filter by filename substring
xtrshow --max-depth 2       # limit recursion depth
xtrshow --clean             # omit line numbers (raw content)
xtrshow -o context.md       # write to a file instead of stdout
xtrshow --no-ignore         # show ignored dirs (.git, node_modules, ...)
xtrshow --no-meta           # omit the per-file metadata line
xtrshow --no-hash           # keep the metadata line, drop the sha256 digest
```

### File Metadata

Each exported file block includes a `# meta:` line under its header with the file's size, line count, modification date (plus creation date on platforms that track it — macOS and Windows; Linux doesn't expose true creation time), its permissions and owner, and a SHA-256 digest:

```
--- a/src/main.py
+++ b/src/main.py
# meta: 4.2 KB | 128 lines | modified 2026-08-26T10:32:11-04:00 | mode 0644 (rw-r--r--) | owner mike:staff | sha256 9f2b...c41e
```

This gives the LLM a sense of which files are freshest without costing more than a line of context. Pass `--no-meta` to omit it. The line starts with `#`, so it's inert if it ever ends up inside a patch file.

The digest is over the file's **raw bytes on disk**, not the line-numbered, newline-normalized text inside the fence. That means it matches `sha256sum src/main.py` and the checksums `xtrpatch` records under `.xtr/backup/`, so you can verify a paste by hand:

```bash
sha256sum src/main.py    # compare against the digest in the meta line
```

Its main job is identity, not integrity: re-export the same files after a round of edits and the model can compare digests to see which ones actually changed. Pass `--no-hash` to drop the digest while keeping the rest of the line.

### Re-Exporting (`--update`)

Every export saves your selection to `.xtr/manifest`. When you've changed code and want to send the same files back to the LLM, skip the TUI:

```bash
xtrshow --update > context.md
```

### Multi-File Export (`--multi`)

For pipelines that want one file per source file (e.g., RAG ingestion, or project-file uploads to a chat UI):

```bash
xtrshow --multi                 # writes to .xtrshow/
xtrshow --multi ./my_export_dir # custom directory
```

Paths are flattened (`src/main.py` → `src__main.py.xtr.md`).

### Printing the LLM Instructions (`-p`)

```bash
xtrshow -p
```

Prints the instruction block that teaches the model to reply in the Search & Replace format below. Paste it into your prompt once per session.

---

## 2. Applying Changes (`xtrpatch`)

`xtrpatch` reads a text file containing Search & Replace blocks and applies them. Matching is whitespace-normalized ("fuzzy"), so common LLM indentation errors don't cause failures.

### Basic Usage

```bash
# Save the LLM's reply to a file, then:
xtrpatch changes.patch

# If the patch has no file headers, supply the target explicitly:
xtrpatch target_file.py changes.patch
```

### Reading the Report

Each file gets a summary line and a per-hunk breakdown:

```
📄 src/app.py           ✅ SUCCESS (Δ+3 lines)
   1. ✅ @ Add timeout to foo      [Rep: 1, New: 1, Δ+0]
   2. 🧠 @ Default msg param       [Already Applied]
   3. ❌ @ Rename handler          [Block Not Found] ~Line 42
```

| Icon | Meaning |
| --- | --- |
| ✅ APPLIED | Hunk matched and was written |
| 🧠 SKIPPED | Replacement already present (patch re-run) |
| 🛑 BLOCKED | Tail context didn't match — wrong location, aborted |
| ⚡ CONFLICT | Overlaps an earlier hunk — skipped |
| ❌ FAILED | Search block not found |

On any failure, an **error report** (`.rpterr`) is written next to the backup, bundling the original file, the patch, and the log — paste it back to the LLM for self-correction.

### Safety & Versioning

`xtrpatch` never modifies a file without backing it up first.

* **Backups:** `.xtr/backup/<relative_path>/<filename>.orig`, then `.1.orig`, `.2.orig`, … on subsequent patches.
* **Patch archive:** the applied patch is stored alongside each backup (`<filename>.patch`).
* **External-edit detection:** a checksum of the post-patch state is recorded; if the file changes outside the patch loop, the next apply warns you.

Add `.xtr/` to your `.gitignore` — it holds the manifest, backups, and `--multi` output.

Upgrading from 1.2 or earlier? The first run of either command folds the old
`.xtrpatch/`, `.xtrshow_manifest`, and `.xtrshow/` into `.xtr/` and says so. Your
revert history moves with it. An existing `.xtr/` is never overwritten.

### Reverting Changes

```bash
xtrpatch --revert src/main.py    # restore a file from its latest backup
xtrpatch --revert changes.patch  # revert every file targeted by a patch
```

Revert restores the **most recent** backup — run it repeatedly to walk further back.

### Committing with Git

Add `-gc` (`--git-commit`) and `xtrpatch` commits what it changed, on whatever branch is checked out:

```bash
xtrpatch -gc changes.patch
```

The commit holds only the files the patch changed. Backups under `.xtr/`, the patch file itself, and any other work in your tree, staged or not, are left out. The message is built from the patch's `@` comments:

```
[xtrpatch] Add timeout to foo (+2 more)

a.py
  - Add timeout to foo
  - Default msg param on bar
b.py
  - Set x to 2
old.py
  - Delete file
```

The subject is the first comment, plus a count of the rest. A patch with no comments gets `[xtrpatch] Patch a.py` or `[xtrpatch] Patch 3 files`. Paths are relative to the repository root.

| Flag | Effect |
| --- | --- |
| `-gc`, `--git-commit` | Commit the changed files on the current branch |
| `-gmp`, `--git-msg-prefix PREFIX` | Replace the `[xtrpatch] ` prefix (`-gmp ""` for none) |
| `--git-allow-dirty` | Commit target files whole, earlier uncommitted changes included |
| `--git-on-error ask\|commit\|skip` | What to do when some changes failed (default `ask`) |

The last three need `-gc`. Without `-gc`, `xtrpatch` never runs git.

**Checked before anything is written.** `xtrpatch -gc` stops, with no file touched, when git is not installed, you are not in a repository, a merge, rebase, cherry-pick or revert is in progress, or git has no `user.name` / `user.email` to commit with.

**Files that already have uncommitted changes.** Git commits whole files, so a target with earlier edits would carry them into the patch's commit. `xtrpatch` stops and asks instead:

```
Found uncommitted changes:
  src/app.py

Stash and commit? [y/N]
```

Answering `y` stashes those files, applies and commits the patch, and puts your changes back on top. Only the listed files are stashed. Three things to know:

* The patch is applied to the **committed** version of those files. If it was written against your uncommitted edits, some hunks may not match.
* If your changes and the patch touched the same lines, putting them back conflicts. The commit stands, the file gets conflict markers, and your changes stay in `git stash list` until you resolve it.
* It refuses if anything is already staged, or if a target is untracked. Commit or unstage first, or use `--git-allow-dirty`.

With no terminal attached there is nobody to ask, so it stops. Pass `--git-allow-dirty` to commit the earlier changes along with the patch.

**When some hunks fail.** `xtrpatch` asks whether to commit what did apply. A partial commit says so:

```
[xtrpatch] Add timeout to foo

a.py
  - Add timeout to foo

Not applied:
a.py
  - Rename handler
```

With no terminal it does not commit. `--git-on-error commit` and `--git-on-error skip` answer the question in advance. Either way the patch itself behaves as it always does: hunks that applied stay applied.

**Hooks** run as for any commit. If one rejects the commit, the changes are left applied and staged.

**Exit code.** With `-gc`, `xtrpatch` exits `0` when the commit was made or there was nothing to commit, and `1` when it stopped, did not commit because of failures, the commit failed, or stashed changes could not be put back cleanly.

**Reverting.** `--revert` takes the same flags and follows the same rules:

```bash
xtrpatch --revert -gc changes.patch
```

```
[xtrpatch] Revert: Add timeout to foo (+2 more)

a.py
  - Add timeout to foo
  - Default msg param on bar
b.py
  - Set x to 2
```

The comments come from the patch archived beside the backup being restored, so the message describes the change actually undone even if a later patch touched the file.

---

## 3. Patch File Specification

### Standard Block (Modify)

```text
--- a/path/to/target.py
@ optional one-line description of the change
<<<< LINE_HINT
[content to find]
====
[content to replace it with]
>>>>
```

* **Header:** `--- a/path/to/file`. Each hunk needs its own header — even a second hunk for the same file.
* **Annotation (optional):** `@ description`. Echoed in the apply report; strongly recommended, since it makes failures self-describing.
* **Start:** `<<<<`, optionally with a line hint: `<<<< 50` (near line 50) or `<<<< 50:60` (range). The hint is a disambiguation nudge — content matching decides. `<<` is accepted as a lenient opener; the closer must always be `>>>>`.
* **Search:** must match content exactly, but leading/trailing whitespace and blank lines are normalized.
* **Divider:** `====`.

If a search block matches more than one place and no hint is given, the hunk fails safe rather than guessing.

### Insertion

Empty search block + a line hint inserts at that line:

```text
--- a/app.py
@ Insert header comment at top
<<<< 1
====
# New header
>>>>
```

A hint past the end of file appends. Add a tail section (below) to anchor the spot robustly.

### File Creation

Empty search block, no hint, file doesn't exist:

```text
--- a/src/new_file.py
<<
====
print("Hello World")
>>>>
```

### File Deletion

Preferred shorthand:

```text
--- a/src/deprecated.py
! DELETE FILE
```

(The legacy form — empty search **and** empty replace — still works.) A backup is taken first, so deletion is revertable.

### Whole-File Replacement

To port a file to a new implementation, delete it and create it again in the
same patch. Both hunks name the same path, delete first:

```text
--- a/src/bootstrap.sh
! DELETE FILE

--- a/src/bootstrap.sh
<<<<
====
#!/bin/bash
apt-get update
>>>>
```

This reports ♻️ REWRITTEN and backs up the original, so it is revertable like
any other change. A create block on its own against a file that already exists
is refused instead: that shape is also what a hunk that lost its search text
looks like, and truncating the file to the replace body on that guess would
throw work away.

### Permissions and Ownership

`! CHMOD` and `! CHOWN` lines change a file's mode and owner. They go under the
file header and run after that file's blocks, so a new script can be created
and made executable in one patch:

```text
--- a/scripts/deploy.sh
<<<<
====
#!/bin/sh
make release
>>>>
! CHMOD +x

--- a/etc/app.conf
! CHMOD 640
! CHOWN root:app
```

`! CHMOD` takes octal (`755`, `0644`) or chmod-style symbolic modes (`+x`,
`u+x,g-w`, `go-rwx`, `a+X`). `! CHOWN` takes `user`, `user:group` or `:group`,
by name or numeric id; it usually needs root, and a refused chown fails that
file only. Each line reports `🔐 MODE old → new` or `👤 OWNER old → new`.

The file is backed up first along with its old mode and owner, so `--revert`
puts both back. Adding setuid, setgid or the sticky bit is refused unless you
pass `--allow-special-modes`.

### Renaming (`! REPLACE`)

`! REPLACE old => new` renames every occurrence of a name in one file. It goes
under the file header, like `! CHMOD`:

```text
--- a/src/client.py
@ Rename fetch_all to fetch_pages
! REPLACE fetch_all => fetch_pages
```

* **Literal.** `old` and `new` are plain text, not patterns. `a.b` matches only
  `a.b`.
* **Whole words.** `count` does not match inside `discount` or `count_total`.
  The edge is only required where `old` itself starts or ends with a letter,
  digit or underscore, so `! REPLACE -> => .` works too.
* **Case-sensitive**, and it does not know about strings or comments: every
  whole-word occurrence in the file changes.
* **One file per line.** A name used in three files needs the line under each
  of the three headers.
* **Spaces around `=>` are required.** The first ` => ` on the line separates
  the two sides.

It runs after that file's search/replace blocks and before `! CHMOD` /
`! CHOWN`, so blocks in the same patch are written against the old names and
whatever they add is renamed along with the rest. Several `! REPLACE` lines
run in the order written.

Each line reports `🔁 REPLACE old => new (N places)`. A line that matches
nothing is a failure, unless `new` is already present, which is reported as
🧠 Already Applied the way a re-run hunk is. A malformed line fails rather
than being skipped. The file is backed up first, so `--revert` undoes it.

### Requiring a Commit (`! REQUIRES`)

A patch can say which commit it builds on:

```text
! REQUIRES 3f9c2ab

--- a/src/client.py
@ Use the new helper
...
```

Before writing anything, `xtrpatch` checks that the commit is your current
`HEAD` or an ancestor of it. If you have not pulled it yet, the patch is
refused with nothing applied:

```
This patch needs commit 3f9c2ab, which is not in your current branch. Pull or merge it first.
Pass --ignore-requires to apply anyway.
Nothing was applied.
```

* The value must be a commit hash, short or full. Branch and tag names are
  rejected, since they can point somewhere else on your machine.
* Put it on the first line. Several lines are allowed, and all must be met.
* It is checked whether or not you use `-gc`. Outside a git repository the
  requirement cannot be checked, which also stops the run.
* On a terminal you are asked `Apply anyway? [y/N]`. Otherwise pass
  `--ignore-requires`. You will want that after a squash merge or a rebase,
  where the change is present but the original hash is gone from history.
* `--revert` does not check it.

Versions of `xtrpatch` before this feature ignore the line.

### Section Deletion

Real search block, empty replace block.

### Tail Context (Lookahead)

A second `====` section declares lines that must appear **after** the match. If they don't, the hunk is 🛑 BLOCKED instead of applying in the wrong place:

```text
--- a/config.py
<<
version = 1
====
version = 2
====
debug = True
>>>>
```

### Wildcard Anchors (`~~~~`)

Inside a search block, `~~~~` skips interior lines so the model only has to reproduce stable anchors:

```text
--- a/app.py
@ Add timeout param without reciting the body
<<
def process(items):
~~~~
    return result
====
def process(items, timeout=30):
    return result
>>>>
```

| Form | Meaning |
| --- | --- |
| `~~~~` | Skip any number of lines |
| `~~~~4` | Skip up to 4 content lines |
| `~~~~=4` | Skip exactly 4 content lines |

Note: the matched span — anchors *and* skipped interior — is replaced by the replace block, so include everything you want to keep.