#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. ./.env
set +a
exec .venv/bin/python manage.py runserver 0.0.0.0:8000 --noreload
