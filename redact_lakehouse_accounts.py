#!/usr/bin/env python3
"""
One-time script to redact AWS account numbers from lakehouse-agent directory.
Run this before committing to clean up existing account numbers.
"""

import re
from pathlib import Path

# AWS account number pattern (12 digits)
ACCOUNT_PATTERN = re.compile(r'\b\d{12}\b')

# ARN pattern to catch account numbers in ARNs
ARN_PATTERN = re.compile(r'(arn:aws:[a-z0-9\-]+:[a-z0-9\-]*:)(\d{12})(:)')

# Text file extensions to scan
TEXT_EXTENSIONS = {'.md', '.py', '.yaml', '.yml', '.txt', '.json', '.sh', '.cfg', '.ini', '.toml', '.ipynb'}

def redact_account_numbers(text):
    """Replace AWS account numbers with XXXXXXXXXXXX"""
    # Redact standalone account numbers
    text = ACCOUNT_PATTERN.sub('XXXXXXXXXXXX', text)
    
    # Redact account numbers in ARNs
    text = ARN_PATTERN.sub(r'\1XXXXXXXXXXXX\3', text)
    
    return text

def scan_directory(directory):
    """Scan directory for files with account numbers"""
    directory_path = Path(directory)
    
    if not directory_path.exists():
        print(f"❌ Directory not found: {directory}")
        return
    
    print(f"🔍 Scanning {directory} for AWS account numbers...\n")
    
    modified_files = []
    skipped_files = []
    
    # Find all text files
    for file_path in directory_path.rglob('*'):
        # Skip directories and hidden files
        if file_path.is_dir() or file_path.name.startswith('.'):
            continue
        
        # Skip non-text files
        if file_path.suffix not in TEXT_EXTENSIONS:
            continue
        
        # Skip __pycache__ and other generated directories
        if any(skip in str(file_path) for skip in ['__pycache__', '.ipynb_checkpoints', 'venv/', '.venv/', 'env/']):
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            cleaned = redact_account_numbers(content)
            
            if cleaned != content:
                # Show what was found
                account_matches = ACCOUNT_PATTERN.findall(content)
                if account_matches:
                    print(f"📄 {file_path.relative_to(directory_path)}")
                    print(f"   Found {len(set(account_matches))} unique account number(s)")
                
                # Write back
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned)
                
                modified_files.append(file_path)
        
        except Exception as e:
            skipped_files.append((file_path, str(e)))
    
    # Summary
    print(f"\n{'='*60}")
    print(f"✅ Modified {len(modified_files)} file(s)")
    
    if modified_files:
        print("\nModified files:")
        for f in modified_files:
            print(f"  - {f.relative_to(directory_path)}")
    
    if skipped_files:
        print(f"\n⚠️  Skipped {len(skipped_files)} file(s) due to errors:")
        for f, error in skipped_files:
            print(f"  - {f.relative_to(directory_path)}: {error}")
    
    if not modified_files and not skipped_files:
        print("✅ No account numbers found!")

if __name__ == '__main__':
    scan_directory('02-use-cases/lakehouse-agent')
