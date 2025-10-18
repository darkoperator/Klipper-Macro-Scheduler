#!/bin/bash
# Klipper Macro Scheduler Installation Script
# This script is called by Moonraker's update_manager

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOONRAKER_COMPONENTS_DIR="${HOME}/moonraker/moonraker/components"
MAINSAIL_DIR="${HOME}/mainsail"
CONFIG_DIR="${HOME}/printer_data/config"

echo "Installing Klipper Macro Scheduler..."

# Check if running as correct user
if [ "$USER" != "pi" ] && [ "$USER" != "$SUDO_USER" ]; then
    echo "Warning: This script should be run as the pi user or your printer's user"
fi

# Create backup of existing files
if [ -f "${MOONRAKER_COMPONENTS_DIR}/macro_scheduler.py" ]; then
    echo "Backing up existing component..."
    cp "${MOONRAKER_COMPONENTS_DIR}/macro_scheduler.py" \
       "${CONFIG_DIR}/macro_scheduler_backup_$(date +%Y%m%d_%H%M%S).py"
fi

if [ -f "${MAINSAIL_DIR}/scheduler.html" ]; then
    echo "Backing up existing UI..."
    cp "${MAINSAIL_DIR}/scheduler.html" \
       "${CONFIG_DIR}/scheduler_ui_backup_$(date +%Y%m%d_%H%M%S).html"
fi

# Install component
echo "Installing Moonraker component..."
if [ -f "${SCRIPT_DIR}/macro_scheduler.py" ]; then
    cp "${SCRIPT_DIR}/macro_scheduler.py" "${MOONRAKER_COMPONENTS_DIR}/"
    chmod 644 "${MOONRAKER_COMPONENTS_DIR}/macro_scheduler.py"
    echo "Component installed"
else
    echo "Error: macro_scheduler.py not found in ${SCRIPT_DIR}"
    exit 1
fi

# Install UI
echo "Installing Web UI..."
if [ -f "${SCRIPT_DIR}/scheduler_ui.html" ]; then
    cp "${SCRIPT_DIR}/scheduler_ui.html" "${MAINSAIL_DIR}/scheduler.html"
    chmod 644 "${MAINSAIL_DIR}/scheduler.html"
    echo "UI installed"
else
    echo "Error: scheduler_ui.html not found in ${SCRIPT_DIR}"
    exit 1
fi

# Check if [macro_scheduler] section exists in moonraker.conf
MOONRAKER_CONF="${CONFIG_DIR}/moonraker.conf"
if [ -f "${MOONRAKER_CONF}" ]; then
    if ! grep -q "\[macro_scheduler\]" "${MOONRAKER_CONF}"; then
        echo ""
        echo "IMPORTANT: Add this to your moonraker.conf:"
        echo ""
        echo "[macro_scheduler]"
        echo ""
        echo "Then restart Moonraker: sudo systemctl restart moonraker"
    else
        echo "Configuration found in moonraker.conf"
    fi
else
    echo "Warning: moonraker.conf not found at expected location"
fi

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
echo "1. Ensure [macro_scheduler] is in moonraker.conf"
echo "2. Restart Moonraker: sudo systemctl restart moonraker"
echo "3. Access UI at: http://your-printer-ip/scheduler.html"
echo ""
echo "For documentation, see: README.md"

exit 0
