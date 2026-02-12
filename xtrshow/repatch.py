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
    lines = content.splitlines()
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("File: "):
            parts = line.split(maxsplit=1)
            if len(parts) > 1:
                raw_path = parts[1].strip()
                if (line.startswith("--- ") and raw_path.startswith("a/")) or \
                   (line.startswith("+++ ") and raw_path.startswith("b/")):
                    raw_path = raw_path[2:]
                current_file = raw_path
            i += 1
            continue

        # Support ':' or '~' for range hints (e.g., 10:15 or 10~15)
        block_match = re.match(r'^<<<<\s*(\d+)?(?:[:~](\d+))?', stripped)
        
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
                        'tail': tail_lines
                    })
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
        print(f"\nProcessing: {filepath}")
        
        if not os.path.exists(filepath):
            if len(blocks) == 1 and not blocks[0]['search']:
                try:
                    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
                    new_content = "".join([l + '\n' for l in blocks[0]['replace']])
                    backup_path, version = get_backup_path(Path(filepath), Path.cwd() / ".xtrpatch")
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    backup_path.touch()
                    print(f"  (Backup created at {backup_path})")
                    if patch_source_path:
                        # Pass filepath to archive
                        archive_patch_file(patch_source_path, filepath, version)
                    with open(filepath, 'w') as f:
                        f.write(new_content)
                    print(f"  ✓ Created new file: {filepath}")
                except Exception as e:
                    print(f"  ✗ Failed to create file: {e}")
                continue
            else:
                print(f"  Error: File {filepath} not found.")
                continue

        try:
            with open(filepath, 'r') as f:
                file_lines = f.readlines()
        except Exception as e:
            print(f"  Error reading file: {e}")
            continue

        success_count = 0
        
        for block in blocks:
            match = find_match(file_lines, block['search'], block['hint'])
            
            if match:
                start, end = match
                
                # --- Tail Context Verification ---
                valid_match = True
                if block.get('tail'):
                    # Check if the lines immediately AFTER the match match the tail block
                    tail_start = end
                    tail_block = block['tail']
                    
                    if tail_start + len(tail_block) > len(file_lines):
                        valid_match = False
                        print(f"  ! Tail context mismatch (End of file reached)")
                    else:
                        for idx, tail_line in enumerate(tail_block):
                            file_line = file_lines[tail_start + idx]
                            if normalize(file_line) != normalize(tail_line):
                                valid_match = False
                                print(f"  ! Tail context mismatch at line {tail_start + idx + 1}")
                                print(f"    Expected: {tail_line.strip()}")
                                print(f"    Found:    {file_line.strip()}")
                                break
                
                if valid_match:
                    new_lines = [l + '\n' for l in block['replace']]
                    file_lines[start:end] = new_lines
                    success_count += 1
                    print(f"  ✓ Applied patch at line {start + 1}")
                else:
                    print(f"  ✗ Skipped block due to context mismatch.")
            else:
                hint_msg = f"(Hint: {block['hint']})" if block['hint'] else "(No line hint)"
                
                already_applied = find_match(file_lines, block['replace'])
                
                if already_applied:
                    print(f"  ! Skipped: Block from patch line {block['patch_line']} appears to be already applied.")
                    print(f"    (Found matching replacement code at line {already_applied[0]+1})")
                else:
                    print(f"  ✗ FAILED to find block from patch line {block['patch_line']} {hint_msg}")
                    if block['search']:
                        preview = block['search'][0].strip()
                        if len(preview) > 50:
                            preview = preview[:47] + "..."
                        print(f"    Searching for: '{preview}'")

        if success_count > 0:
            backup_path, version = create_backup(filepath)
            if backup_path:
                print(f"  (Backup created at {backup_path})")
                if patch_source_path:
                    # Pass filepath to archive function
                    archive_patch_file(patch_source_path, filepath, version)
            
            with open(filepath, 'w') as f:
                f.writelines(file_lines)
            print(f"  Saved {success_count} changes.")
        else:
            print("  No changes applied.")

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