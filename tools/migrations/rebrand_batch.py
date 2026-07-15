p#!/usr/bin/env python3
"""Batch rebrand all files from droneresearch to skymeshx."""
import os
import re
from pathlib import Path

def rebrand_file(filepath):
    """Replace droneresearch with skymeshx in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        original = content
        content = re.sub(r'\bdroneresearch\b', 'skymeshx', content)
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"Error: {filepath}: {e}")
    return False

root = Path(__file__).parent.parent
exclude = {'.git', 'build', 'dist', '__pycache__', '.pytest_cache', 'node_modules'}
extensions = {'.py', '.md', '.yml', '.yaml', '.txt', '.iss', '.spec', '.toml'}

changed = []
for file in root.rglob('*'):
    if file.is_file() and file.suffix in extensions:
        if any(ex in file.parts for ex in exclude):
            continue
        if file.name in ['rebrand_imports.py', 'rebrand_batch.py']:
            continue
        if rebrand_file(file):
            changed.append(str(file.relative_to(root)))

print(f"Changed {len(changed)} files")
for f in sorted(changed)[:30]:
    print(f"  {f}")
if len(changed) > 30:
    print(f"  ... and {len(changed)-30} more")
