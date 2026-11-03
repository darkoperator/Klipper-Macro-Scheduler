#!/bin/bash
# Kept because older moonraker.conf files name this file in install_script, and
# Moonraker rejects that section if the file is missing. install.py does the work.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/install.py" "$@"
