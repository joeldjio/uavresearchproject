#!/usr/bin/env python3
"""Complete rebranding from droneresearch to skymeshx."""
import os
import sys
from pathlib import Path

def rebrand_file(filepath):
    """Replace droneresearch with skymeshx in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if 'droneresearch' not in content.lower():
            return False
            
        original = content
        # Replace all variations
        content = content.replace('droneresearch', 'skymeshx')
        content = content.replace('DroneResearch', 'SkyMeshX')
        content = content.replace('DRONERESEARCH', 'SKYMESHX')
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"Error {filepath}: {e}")
    return False

root = Path.cwd()
exclude_dirs = {'.git', 'build', 'dist', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'venv'}
exclude_files = {'rebrand_imports.py', 'rebrand_batch.py', 'do_rebrand.py'}
extensions = {'.py', '.md', '.yml', '.yaml', '.txt', '.iss', '.spec', '.toml', '.json', '.sh'}

changed = []
total = 0

print("Scanning files...")
for file in root.rglob('*'):
    if not file.is_file():
        continue
    if file.suffix not in extensions:
        continue
    if any(ex in file.parts for ex in exclude_dirs):
        continue
    if file.name in exclude_files:
        continue
    
    total += 1
    if rebrand_file(file):
        rel = file.relative_to(root)
        changed.append(str(rel))
        print(f"  [OK] {rel}")

print(f"\n{'='*60}")
print(f"Scanned: {total} files")
print(f"Changed: {len(changed)} files")
print(f"{'='*60}")
