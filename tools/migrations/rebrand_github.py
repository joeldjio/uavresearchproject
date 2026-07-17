#!/usr/bin/env python3
"""Update GitHub repository URLs from uavresearchproject to skymeshx."""
from pathlib import Path

def rebrand_file(filepath):
    """Replace GitHub URLs."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if 'uavresearchproject' not in content and 'skymeshx-gcs' not in content:
            return False
            
        original = content
        # Replace GitHub URLs
        content = content.replace('joeldjio/skymeshx', 'joeldjio/skymeshx')
        content = content.replace('joeldjio/skymeshx-releases', 'joeldjio/skymeshx-releases')
        content = content.replace('skymeshx-gcs', 'skymeshx-gcs')
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"Error {filepath}: {e}")
    return False

root = Path.cwd()
exclude_dirs = {'.git', 'build', 'dist', '__pycache__', '.pytest_cache'}
extensions = {'.py', '.md', '.yml', '.yaml', '.txt', '.iss', '.spec', '.toml', '.json', '.qml'}

changed = []
total = 0

print("Updating GitHub URLs...")
for file in root.rglob('*'):
    if not file.is_file():
        continue
    if file.suffix not in extensions:
        continue
    if any(ex in file.parts for ex in exclude_dirs):
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
