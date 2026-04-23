#!/usr/bin/env python3
import sys
import re
import argparse
import os
import shutil
from pathlib import Path

def normalize(line):
    """Normalize line for comparison (strip whitespace)."""
    return line.strip()

def find_match(file_lines, search_lines, start_hint=None):
    """Find the best match for search_lines in file_lines."""
    norm_search = [normalize(l) for l in search_lines if normalize(l)]
    if not norm_search:
        return None
    
    candidates = []
    
    for i in range(len(file_lines)):
        if normalize(file_lines[i]) != norm_search[0]:
            continue
            
        match = True
        file_idx = i
        search_idx = 0
        
        while search_idx < len(norm_search):
            if file_idx >= len(file_lines):
                match = False
                break
            
            norm_file_line = normalize(file_lines[file_idx])
            
            if not norm_file_line:
                file_idx += 1
                continue
                
            if norm_file_line != norm_search[search_idx]:
                match = False
                break
            
            file_idx += 1
            search_idx += 1
            
        if match:
            candidates.append((i, file_idx))

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]
    
    if start_hint is not None:
        best_candidate = min(candidates, key=lambda x: abs((x[0] + 1) - start_hint))
        return best_candidate
        
    print(f"Error: Ambiguous match. Found {len(candidates)} instances of block.")
    return None

def parse_multi_file_patch(content, default_target=None):
    """Parses a patch file containing multiple file sections."""
    changes = {}
    current_file = default_target
    current_annotation = None
    lines = content.splitlines()
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Capture Annotations
        if stripped.startswith("@"):
            current_annotation = stripped[1:].strip()
            i += 1
            continue

        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("File: "):
            parts = line.split(maxsplit=1)
            if len(parts) > 1:
                raw_path = parts[1].strip()
                if (line.startswith("--- ") and raw_path.startswith("a/")) or \
                   (line.startswith("+++ ") and raw_path.startswith("b/")):
                    raw_path = raw_path[2:]
                current_file = raw_path
            current_annotation = None # Reset annotation on file change
            i += 1
            continue

        # Support ':' or '~' for range hints (e.g., 10:15 or 10~15)
        # ALLOW '<<' (2 brackets) as a start marker, but ONLY if the line ends immediately
        # after the hint. This prevents matching C++ streams or bitwise shifts like '<< 5;'.
        block_match = re.match(r'^(?:<<<<|<<)\s*(\d+)?(?:[:~](\d+))?\s*$', stripped)
        
        if block_match:
            block_start_line = i + 1
            
            if not current_file:
                i += 1
                continue

            hint_start = int(block_match.group(1)) if block_match.group(1) else None
            
            i += 1
            search_lines = []
            while i < len(lines) and lines[i].strip() != "====":
                search_lines.append(lines[i])
                i += 1
            
            if i < len(lines) and lines[i].strip() == "====":
                i += 1 
                replace_lines = []
                tail_lines = []
                
                # Consume Replace Block (until >>>> OR second ====)
                while i < len(lines):
                    s = lines[i].strip()
                    if s == ">>>>" or s == "====":
                        break
                    replace_lines.append(lines[i])
                    i += 1
                
                # Check for Tail Context (second ====)
                if i < len(lines) and lines[i].strip() == "====":
                    i += 1 # skip second ====
                    while i < len(lines) and lines[i].strip() != ">>>>":
                        tail_lines.append(lines[i])
                        i += 1

                if i < len(lines) and lines[i].strip() == ">>>>":
                    if current_file not in changes:
                        changes[current_file] = []
                    
                    changes[current_file].append({
                        'patch_line': block_start_line,
                        'hint': hint_start,
                        'search': search_lines,
                        'replace': replace_lines,
                        'tail': tail_lines,
                        'annotation': current_annotation
                    })
                    current_annotation = None # Consumed
            i += 1
            continue
            
        i += 1
        
    return changes

def get_backup_path(src_path, backup_dir_root):
    """Calculates the next available versioned path."""
    try:
        rel_path = src_path.relative_to(Path.cwd())
    except ValueError:
        rel_path = Path(src_path.name)

    base_backup_dir = backup_dir_root / rel_path.parent
    base_backup_dir.mkdir(parents=True, exist_ok=True)
    
    filename = rel_path.name
    
    v0 = base_backup_dir / (filename + ".orig")
    if not v0.exists():
        return v0, 0
        
    i = 1
    while True:
        next_path = base_backup_dir / (filename + f".{i}.orig")
        if not next_path.exists():
            return next_path, i
        i += 1

def create_backup(filepath):
    """Creates a versioned backup of the file."""
    try:
        src = Path(filepath).resolve()
        backup_root = Path.cwd() / ".xtrpatch"
        dest, version = get_backup_path(src, backup_root)
        shutil.copy2(src, dest)
        return dest, version
    except Exception as e:
        print(f"  ! Warning: Failed to create backup: {e}")
        return None, None

def archive_patch_file(patch_source_path, target_filepath, version_index):
    """
    Copies the patch file to .xtrpatch/.../target_file.version.patch
    This stores the patch alongside the backup of the file it modified.
    """
    if not patch_source_path:
        return
    try:
        # Calculate where the backup lives
        target_path = Path(target_filepath).resolve()
        try:
            rel_path = target_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = Path(target_path.name)
            
        backup_dir = Path.cwd() / ".xtrpatch" / rel_path.parent
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        filename = rel_path.name
        
        # Format: target.py.patch (v0), target.py.1.patch (v1)
        if version_index == 0:
            dest = backup_dir / (filename + ".patch")
        else:
            dest = backup_dir / (filename + f".{version_index}.patch")
            
        if not dest.exists():
            shutil.copy2(patch_source_path, dest)
            print(f"  (Patch archived to {dest})")
            
    except Exception as e:
        print(f"  ! Warning: Failed to archive patch file: {e}")

def save_log_file(log_content, target_filepath, version_index):
    """Saves the command output log."""
    try:
        target_path = Path(target_filepath).resolve()
        try:
            rel_path = target_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = Path(target_path.name)
            
        backup_dir = Path.cwd() / ".xtrpatch" / rel_path.parent
        backup_dir.mkdir(parents=True, exist_ok=True)
        filename = rel_path.name
        
        suffix = ".out" if version_index == 0 else f".{version_index}.out"
        dest = backup_dir / (filename + suffix)
        
        with open(dest, 'w') as f:
            f.write(log_content)
    except Exception as e:
        print(f"  ! Warning: Failed to save log file: {e}")

def save_error_report(target_filepath, version_index, log_content):
    """Creates a combined error report with quintuple backticks."""
    try:
        target_path = Path(target_filepath).resolve()
        try:
            rel_path = target_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = Path(target_path.name)
            
        backup_dir = Path.cwd() / ".xtrpatch" / rel_path.parent
        filename = rel_path.name
        
        suffix_base = "" if version_index == 0 else f".{version_index}"
        
        orig_path = backup_dir / (filename + suffix_base + ".orig")
        patch_path = backup_dir / (filename + suffix_base + ".patch")
        
        report_path = backup_dir / (filename + suffix_base + ".rpterr")
        
        report = []
        
        # 1. Original
        report.append(f"Content of {orig_path.name}:")
        report.append("'''''")
        if orig_path.exists():
            report.append(orig_path.read_text())
        else:
            report.append("(File not found)")
        report.append("'''''\n")

        # 2. Patch
        report.append(f"Content of {patch_path.name}:")
        report.append("'''''")
        if patch_path.exists():
            report.append(patch_path.read_text())
        else:
            report.append("(File not found)")
        report.append("'''''\n")

        # 3. Output
        report.append(f"Output Log:")
        report.append("'''''")
        report.append(log_content)
        report.append("'''''\n")
        
        with open(report_path, 'w') as f:
            f.write("\n".join(report))
            
        print(f"  ! Error Report generated: {report_path}")

    except Exception as e:
        print(f"  ! Warning: Failed to generate error report: {e}")

def save_log_file(log_content, target_filepath, version_index):
    """Saves the command output log."""
    try:
        target_path = Path(target_filepath).resolve()
        try:
            rel_path = target_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = Path(target_path.name)
            
        backup_dir = Path.cwd() / ".xtrpatch" / rel_path.parent
        backup_dir.mkdir(parents=True, exist_ok=True)
        filename = rel_path.name
        
        suffix = ".out" if version_index == 0 else f".{version_index}.out"
        dest = backup_dir / (filename + suffix)
        
        with open(dest, 'w') as f:
            f.write(log_content)
    except Exception as e:
        print(f"  ! Warning: Failed to save log file: {e}")

def save_error_report(target_filepath, version_index, log_content):
    """Creates a combined error report with quintuple backticks."""
    try:
        target_path = Path(target_filepath).resolve()
        try:
            rel_path = target_path.relative_to(Path.cwd())
        except ValueError:
            rel_path = Path(target_path.name)
            
        backup_dir = Path.cwd() / ".xtrpatch" / rel_path.parent
        filename = rel_path.name
        
        suffix_base = "" if version_index == 0 else f".{version_index}"
        
        orig_path = backup_dir / (filename + suffix_base + ".orig")
        patch_path = backup_dir / (filename + suffix_base + ".patch")
        
        report_path = backup_dir / (filename + suffix_base + ".rpterr")
        
        report = []
        
        # 1. Original
        report.append(f"Content of {orig_path.name}:")
        report.append("'''''")
        if orig_path.exists():
            report.append(orig_path.read_text())
        else:
            report.append("(File not found)")
        report.append("'''''\n")

        # 2. Patch
        report.append(f"Content of {patch_path.name}:")
        report.append("'''''")
        if patch_path.exists():
            report.append(patch_path.read_text())
        else:
            report.append("(File not found)")
        report.append("'''''\n")

        # 3. Output
        report.append(f"Output Log:")
        report.append("'''''")
        report.append(log_content)
        report.append("'''''\n")
        
        with open(report_path, 'w') as f:
            f.write("\n".join(report))
            
        print(f"  ! Error Report generated: {report_path}")

    except Exception as e:
        print(f"  ! Warning: Failed to generate error report: {e}")

def revert_file(target_file):
    """Reverts the file to its most recent backup."""
    try:
        target = Path(target_file).resolve()
        try:
            rel_path = target.relative_to(Path.cwd())
        except ValueError:
            rel_path = Path(target.name)

        backup_dir = Path.cwd() / ".xtrpatch" / rel_path.parent
        filename = rel_path.name
        
        if not backup_dir.exists():
            print(f"No backups found for {target_file}")
            return

        backups = []
        base = backup_dir / (filename + ".orig")
        if base.exists():
            backups.append((0, base))
            
        for f in backup_dir.iterdir():
            if f.name.startswith(filename + ".") and f.name.endswith(".orig"):
                parts = f.name.split('.')
                if len(parts) >= 3 and parts[-2].isdigit():
                    idx = int(parts[-2])
                    backups.append((idx, f))
        
        if not backups:
            print(f"No backups found for {target_file}")
            return
            
        backups.sort(key=lambda x: x[0], reverse=True)
        latest_version, latest_backup = backups[0]
        
        print(f"Reverting {target_file}...")
        print(f"  Source: {latest_backup} (v{latest_version})")
        
        shutil.copy2(latest_backup, target)
        print("  ✓ File restored successfully.")
        
    except Exception as e:
        print(f"Error during revert: {e}")

def apply_changes(changes_dict, patch_source_path=None):
    """Applies parsed changes to files."""
    for filepath, blocks in changes_dict.items():
        log_buffer = []
        # Store output in buffer to print summary at end of file processing
        def output(msg):
            print(msg)
            log_buffer.append(str(msg))
        
        # We also maintain a silent buffer for the log file to ensure full detail is preserved
        # even if we make the console output concise.
        
        file_delta_total = 0
        hunk_stats = []

        # --- File Deletion Logic ---
        if os.path.exists(filepath):
            # Trigger: Single block, Empty Search, Empty Replace
            if len(blocks) == 1 and not blocks[0]['search'] and not blocks[0]['replace']:
                try:
                    # 1. Backup (Crucial for Undo/Revert)
                    backup_path, version = create_backup(filepath)
                    if backup_path and patch_source_path:
                        archive_patch_file(patch_source_path, filepath, version)
                    
                    # 2. Delete
                    orig_len = 0
                    try:
                        with open(filepath, 'r') as f: orig_len = len(f.readlines())
                    except: pass

                    os.remove(filepath)
                    output(f"🗑️  {filepath} ... DELETED (Δ-{orig_len} lines)")
                    save_log_file("\n".join(log_buffer), filepath, version)
                except Exception as e:
                    output(f"❌ {filepath} ... FAILED TO DELETE: {e}")
                    save_log_file("\n".join(log_buffer), filepath, version)
                continue

        if not os.path.exists(filepath):
            if len(blocks) == 1 and not blocks[0]['search']:
                try:
                    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
                    new_content = "".join([l + '\n' for l in blocks[0]['replace']])
                    new_len = len(blocks[0]['replace'])
                    
                    # Backup logic (even for new files, we claim version 0)
                    backup_path, version = get_backup_path(Path(filepath), Path.cwd() / ".xtrpatch")
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    backup_path.touch()
                    
                    if patch_source_path:
                        archive_patch_file(patch_source_path, filepath, version)
                        
                    with open(filepath, 'w') as f:
                        f.write(new_content)
                        
                    output(f"✨ {filepath} ... CREATED (Δ+{new_len} lines)")
                    save_log_file("\n".join(log_buffer), filepath, version)
                except Exception as e:
                    output(f"❌ {filepath} ... FAILED TO CREATE: {e}")
                    save_log_file("\n".join(log_buffer), filepath, version)
                continue
            else:
                output(f"❌ {filepath} ... NOT FOUND (Cannot modify missing file)")
                continue

        # --- Modification Logic ---
        
        # 1. Always Create Backup First (Transaction Start)
        backup_path, version = create_backup(filepath)
        if backup_path and patch_source_path:
            archive_patch_file(patch_source_path, filepath, version)
        elif not backup_path:
            version = 0

        try:
            with open(filepath, 'r') as f:
                file_lines = f.readlines()
        except Exception as e:
            output(f"❌ {filepath} ... ERROR READING: {e}")
            continue

        error_occurred = False
        
        for i, block in enumerate(blocks, 1):
            hunk_res = {'id': i, 'annotation': block.get('annotation', '')}
            
            # Handle Pure Insertion (Empty Search + Line Hint)
            if not block['search'] and block['hint'] is not None:
                # Insert at the specific line (0-indexed)
                # Python slices handle out-of-bounds gracefully (appending)
                idx = max(0, block['hint'] - 1)
                match = (idx, idx)
            else:
                match = find_match(file_lines, block['search'], block['hint'])
            
            if match:
                start, end = match
                
                # --- Tail Context Verification (Robust) ---
                valid_match = True
                if block.get('tail'):
                    # 1. Normalize expectation
                    norm_tail_block = [normalize(l) for l in block['tail'] if normalize(l)]
                    
                    if norm_tail_block:
                        current_file_idx = end
                        tail_idx = 0
                        
                        while tail_idx < len(norm_tail_block):
                            if current_file_idx >= len(file_lines):
                                valid_match = False
                                break
                            
                            norm_file = normalize(file_lines[current_file_idx])
                            
                            if not norm_file: # Skip blank lines in file
                                current_file_idx += 1
                                continue
                                
                            norm_tail = norm_tail_block[tail_idx]
                            
                            if norm_file != norm_tail:
                                valid_match = False
                                break
                                
                            current_file_idx += 1
                            tail_idx += 1
                
                if valid_match:
                    new_lines = [l + '\n' for l in block['replace']]
                    file_lines[start:end] = new_lines
                    
                    # Stats
                    rep_len = len(block['search'])
                    new_len = len(block['replace'])
                    delta = new_len - rep_len
                    file_delta_total += delta
                    
                    hunk_res.update({
                        'status': 'APPLIED',
                        'rep': rep_len,
                        'new': new_len,
                        'delta': delta
                    })
                else:
                    error_occurred = True
                    hunk_res['status'] = 'BLOCKED'
            else:
                # Check if redundant (already applied)
                already_applied = find_match(file_lines, block['replace'])
                
                if already_applied:
                    hunk_res['status'] = 'SKIPPED'
                else:
                    error_occurred = True
                    hunk_res['status'] = 'FAILED'
                    hunk_res['hint'] = block['hint']

            hunk_stats.append(hunk_res)

        # --- Generate Report ---
        
        # 1. Determine File Status
        successes = [h for h in hunk_stats if h['status'] == 'APPLIED']
        fails = [h for h in hunk_stats if h['status'] in ('FAILED', 'BLOCKED')]
        
        if not fails and successes:
             file_icon = "✅ SUCCESS"
        elif not fails and not successes:
             file_icon = "⏭️  SKIPPED" # All redundant
        elif fails and successes:
             file_icon = "⚠️  PARTIAL"
        else:
             file_icon = "❌ FAILED"
        
        # 2. Print Header
        sign = "+" if file_delta_total >= 0 else ""
        header = f"📄 {filepath:<40} {file_icon} (Δ{sign}{file_delta_total} lines)"
        output(header)
        
        # 3. Print Hunks
        for h in hunk_stats:
            desc = f"@ {h['annotation']}" if h['annotation'] else f"Hunk {h['id']}"
            if len(desc) > 30: desc = desc[:27] + "..."
            
            if h['status'] == 'APPLIED':
                d_sign = "+" if h['delta'] >= 0 else ""
                meta = f"[Rep: {h['rep']}, New: {h['new']}, Δ{d_sign}{h['delta']}]"
                line = f"   {h['id']}. ✅ {desc:<32} {meta}"
            elif h['status'] == 'SKIPPED':
                line = f"   {h['id']}. 🧠 {desc:<32} [Already Applied]"
            elif h['status'] == 'BLOCKED':
                line = f"   {h['id']}. 🛑 {desc:<32} [Tail Context Mismatch]"
            elif h['status'] == 'FAILED':
                hint = f"~Line {h['hint']}" if h.get('hint') else "No Hint"
                line = f"   {h['id']}. ❌ {desc:<32} [Block Not Found] {hint}"
            
            output(line)

        # Save output log
        save_log_file("\n".join(log_buffer), filepath, version)

        # Generate Error Report if needed
        if error_occurred:
            save_error_report(filepath, version, "\n".join(log_buffer))

        if successes:
            with open(filepath, 'w') as f:
                f.writelines(file_lines)

def main():
    parser = argparse.ArgumentParser(
        description="Apply AI-generated search/replace blocks",
        usage="%(prog)s [options] [target_file] [patch_file]"
    )
    
    parser.add_argument("--revert", action="store_true", help="Revert file(s) to latest backup")
    parser.add_argument("args", nargs="*", help="File to revert, or Patch file to apply")

    args = parser.parse_args()
    
    if not args.args:
        parser.print_help()
        sys.exit(1)

    if args.revert:
        target_candidate = args.args[0]
        if os.path.exists(target_candidate) and os.path.isfile(target_candidate):
             with open(target_candidate, 'r') as f:
                 try:
                     content = f.read()
                     if "--- a/" in content or "File: " in content:
                         changes = parse_multi_file_patch(content)
                         if changes:
                             print(f"Found {len(changes)} target(s) in patch file to revert.")
                             for filepath in changes.keys():
                                 revert_file(filepath)
                             sys.exit(0)
                 except UnicodeDecodeError:
                     pass
        revert_file(target_candidate)
        sys.exit(0)

    patch_path = None
    target_override = None

    if len(args.args) == 1:
        patch_path = args.args[0]
    elif len(args.args) == 2:
        target_override = args.args[0]
        patch_path = args.args[1]

    if not os.path.exists(patch_path):
        print(f"Error: File '{patch_path}' not found.")
        sys.exit(1)
        
    with open(patch_path, 'r') as f:
        content = f.read()
        
    changes = parse_multi_file_patch(content, default_target=target_override)
    
    if not changes:
        print("No valid blocks found in patch file.")
        sys.exit(1)
    
    apply_changes(changes, patch_source_path=patch_path)

if __name__ == "__main__":
    main()