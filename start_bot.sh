#!/bin/bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

"$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/bot.py"