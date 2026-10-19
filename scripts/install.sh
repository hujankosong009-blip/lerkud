#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# Local development config only; preserve every existing .env.
if [ ! -e .env ]; then
  .venv/bin/python - <<'PY'
from pathlib import Path
import secrets
p=Path('.env')
p.write_text(Path('.env.example').read_text().replace('replace-with-a-random-local-secret',secrets.token_hex(48)))
p.chmod(0o600)
PY
fi
set -a
. ./.env
set +a
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check
