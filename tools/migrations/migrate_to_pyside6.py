#!/usr/bin/env python3
"""
Migrate PySide6 imports to PySide6 for license compliance.

This script automates the conversion from PySide6 (GPL v3) to PySide6 (LGPL v3)
to enable commercial use of the SkyMeshX project.

Changes made:
1. PySide6 → PySide6 in all imports
2. Signal → Signal
3. Slot → Slot
4. Property → Property
5. QtWebEngineQuick → QtWebEngineQuick (same in PySide6)
"""

import os
import re
from pathlib import Path
from typing import List, Tuple


def find_python_files(root_dir: Path) -> List[Path]:
    """Find all Python files in the project."""
    root = root_dir
    python_files = []
    
    # Search in tools/ui, tests, and root
    for pattern in ["tools/**/*.py", "tests/**/*.py", "*.py"]:
        python_files.extend(root.glob(pattern))
    
    return sorted(set(python_files))


def migrate_file(file_path: Path) -> Tuple[bool, int]:
    """
    Migrate a single file from PySide6 to PySide6.
    
    Returns:
        (changed, num_changes): Whether file was modified and number of changes
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False, 0
    
    original_content = content
    changes = 0
    
    # 1. Replace PySide6 imports with PySide6
    patterns = [
        (r'\bPyQt6\b', 'PySide6'),
        (r'\bpyqtSignal\b', 'Signal'),
        (r'\bpyqtSlot\b', 'Slot'),
        (r'\bpyqtProperty\b', 'Property'),
    ]
    
    for pattern, replacement in patterns:
        new_content, count = re.subn(pattern, replacement, content)
        if count > 0:
            changes += count
            content = new_content
    
    # Only write if changes were made
    if content != original_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, changes
        except Exception as e:
            print(f"Error writing {file_path}: {e}")
            return False, 0
    
    return False, 0


def main():
    """Main migration function."""
    print("=" * 70)
    print("PySide6 -> PySide6 Migration Script")
    print("=" * 70)
    print()
    
    # Get project root (parent of tools/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    print(f"Project root: {project_root}")
    print()
    
    # Find all Python files
    python_files = find_python_files(project_root)
    print(f"Found {len(python_files)} Python files")
    print()
    
    # Migrate each file
    total_files_changed = 0
    total_changes = 0
    
    for file_path in python_files:
        changed, num_changes = migrate_file(file_path)
        if changed:
            total_files_changed += 1
            total_changes += num_changes
            rel_path = file_path.relative_to(project_root)
            print(f"[OK] {rel_path}: {num_changes} changes")
    
    print()
    print("=" * 70)
    print(f"Migration complete!")
    print(f"  Files modified: {total_files_changed}")
    print(f"  Total changes: {total_changes}")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Review the changes with: git diff")
    print("2. Install PySide6: pip uninstall PySide6 PySide6-WebEngine && pip install PySide6 PySide6-WebEngine")
    print("3. Run tests: pytest tests/")
    print("4. Test UI: python -m tools.ui")


if __name__ == "__main__":
    main()
