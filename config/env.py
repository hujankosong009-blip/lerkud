"""Load simple .env without executing shell commands; injected variables win."""
import os
import re
from pathlib import Path

def load_env():
    path = Path(__file__).resolve().parent.parent / '.env'
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$', line)
        if match:
            value = match[2].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            os.environ.setdefault(match[1], value)
