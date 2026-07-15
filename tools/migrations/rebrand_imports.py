#!/usr/bin/env python3
"""
Script to rebrand all 'droneresearch' imports to 'skymeshx' across the codebase.
"""
import os
import re
from pathlib import Path

def rebrand_file(filepath):
    """Replace droneresearch with skymeshx in a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # Replace imports and references
        content = re.sub(r'\bdroneresearch\b', 'skymeshx', content)
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

def main():
    """Rebrand all Python files in the project."""
    root = Path(__file__).parent.parent
    
    # Patterns to search
    patterns = ['**/*.py', '**/*.md', '**/*.yml', '**/*.yaml', '**/*.toml', '**/*.txt', '**/*.iss', '**/*.spec']
    
    # Directories to exclude
    exclude_dirs = {'.git', '.pytest_cache', '__pycache__', 'node_modules', '.venv', 'venv', 'build', 'dist', '*.egg-info'}
    
    changed_files = []
    
    for pattern in patterns:
        for filepath in root.glob(pattern):
            # Skip excluded directories
            if any(excluded in filepath.parts for excluded in exclude_dirs):
                continue
            
            # Skip this script itself
            if filepath.name == 'rebrand_imports.py':
                continue
                
            if rebrand_file(filepath):
                changed_files.append(str(filepath.relative_to(root)))
    
    print(f"\n[OK] Rebranding complete!")
    print(f"Changed {len(changed_files)} files:")
    for f in sorted(changed_files)[:20]:  # Show first 20
        print(f"   - {f}")
    if len(changed_files) > 20:
        print(f"   ... and {len(changed_files) - 20} more files")

if __name__ == '__main__':
    main()
