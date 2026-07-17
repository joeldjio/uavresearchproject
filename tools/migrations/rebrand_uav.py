#!/usr/bin/env python3
"""Rebrand UAVResearch/uavresearch to SkyMeshX/skymeshx."""
import os
from pathlib import Path

def rebrand_file(filepath):
    """Replace UAVResearch variations with SkyMeshX."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if 'uavresearch' not in content.lower() and 'uav research' not in content.lower():
            return False
            
        original = content
        # Replace all variations
        content = content.replace('UAVResearch', 'SkyMeshX')
        content = content.replace('uavresearch', 'skymeshx')
        content = content.replace('UAVRESEARCH', 'SKYMESHX')
        content = content.replace('UAV Research', 'SkyMeshX')
        content = content.replace('uav research', 'skymeshx')
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"Error {filepath}: {e}")
    return False

root = Path.cwd()
exclude_dirs = {'.git', 'build', 'dist', '__pycache__', '.pytest_cache', 'node_modules'}
exclude_files = {'rebrand_imports.py', 'rebrand_batch.py', 'do_rebrand.py', 'rebrand_uav.py'}
extensions = {'.py', '.md', '.yml', '.yaml', '.txt', '.iss', '.spec', '.toml', '.json', '.qml'}

changed = []
total = 0

print("Scanning for UAVResearch references...")
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
