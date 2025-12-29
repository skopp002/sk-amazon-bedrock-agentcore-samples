# Security Setup for Lakehouse Agent

## Overview
This directory has been configured with security measures to prevent AWS account numbers from being committed to the repository.

## What Was Done

### 1. Git Pre-commit Hook
A pre-commit hook has been installed at `.git/hooks/pre-commit` that:
- Automatically scans all staged files for AWS account numbers
- Redacts 12-digit account numbers with `XXXXXXXXXXXX`
- Redacts account numbers in ARNs (e.g., `arn:aws:iam::XXXXXXXXXXXX:role/...`)
- Re-stages modified files automatically

**Files scanned:**
- Jupyter notebooks (`.ipynb`) - outputs only
- All text files in `lakehouse-agent/` directory (`.md`, `.py`, `.yaml`, `.json`, etc.)
- Other text files across the repository

### 2. .gitignore Configuration
Created `02-use-cases/lakehouse-agent/.gitignore` to exclude:
- Python bytecode (`__pycache__/`, `*.pyc`)
- Virtual environments (`venv/`, `.venv/`, `env/`)
- Environment files (`.env`, `.env.local`)
- IDE files (`.vscode/`, `.idea/`)
- AWS credentials (`.aws/`, `*.pem`)
- AgentCore config files (`.bedrock_agentcore.yaml`, etc.)

### 3. One-time Cleanup
Ran `redact_lakehouse_accounts.py` to clean existing files:
- ✅ Redacted account numbers from 3 main files:
  - `NEXT_STEPS.md`
  - `README.md`
  - `DEPLOYMENT_STATUS.md`
- ⚠️ Also found account numbers in venv (now excluded from git)

## How It Works

### Automatic Protection (Pre-commit Hook)
Every time you commit:
```bash
git add .
git commit -m "Your message"
```

The hook will:
1. Scan staged files for account numbers
2. Redact any found
3. Re-stage the cleaned files
4. Continue with the commit

Example output:
```
🔍 Scanning files for AWS account numbers...
   - 2 lakehouse-agent file(s)
✅ Redacted account numbers from: 02-use-cases/lakehouse-agent/README.md
📝 Re-staging 1 modified file(s)...
✅ Account numbers redacted and files re-staged
```

### Manual Cleanup
To manually scan and clean files:
```bash
python3 redact_lakehouse_accounts.py
```

## Testing the Hook

Test without committing:
```bash
# Stage a file
git add 02-use-cases/lakehouse-agent/README.md

# Run hook manually
.git/hooks/pre-commit

# Check what changed
git diff --cached 02-use-cases/lakehouse-agent/README.md
```

## Bypassing the Hook (Not Recommended)

Only if absolutely necessary:
```bash
git commit --no-verify -m "Your message"
```

## Patterns Detected

The hook detects and redacts:
- **Standalone account numbers**: `XXXXXXXXXXXX` → `XXXXXXXXXXXX`
- **ARNs**: `arn:aws:iam::XXXXXXXXXXXX:role/MyRole` → `arn:aws:iam::XXXXXXXXXXXX:role/MyRole`
- **In any context**: Code, documentation, configuration files, notebook outputs

## Files Protected

### Always Scanned:
- `02-use-cases/lakehouse-agent/**/*.md`
- `02-use-cases/lakehouse-agent/**/*.py`
- `02-use-cases/lakehouse-agent/**/*.yaml`
- `02-use-cases/lakehouse-agent/**/*.json`
- `02-use-cases/lakehouse-agent/**/*.sh`
- All `.ipynb` files (notebook outputs only)

### Excluded from Scanning:
- `venv/`, `.venv/`, `env/` directories
- `__pycache__/` directories
- `.ipynb_checkpoints/` directories

## Troubleshooting

### Hook not running?
```bash
# Check if hook exists and is executable
ls -la .git/hooks/pre-commit

# Make it executable
chmod +x .git/hooks/pre-commit
```

### Hook failing?
```bash
# Check Python version
python3 --version

# Run hook manually to see errors
.git/hooks/pre-commit
```

### Need to commit venv?
Don't! Virtual environments should never be committed. Use `requirements.txt` instead.

## Best Practices

1. **Never commit real account numbers** - Let the hook do its job
2. **Use placeholder values** - Use `XXXXXXXXXXXX` or `XXXXXXXXXXXX` in examples
3. **Review before pushing** - Check `git diff` before pushing to remote
4. **Keep .gitignore updated** - Add new sensitive file patterns as needed
5. **Don't bypass the hook** - It's there to protect you

## Additional Security

Consider also:
- Using AWS Secrets Manager for sensitive values
- Environment variables for configuration
- AWS SSM Parameter Store for shared configuration
- IAM roles instead of hardcoded credentials

## Questions?

See `.git/hooks/README.md` for more details about the pre-commit hook.
