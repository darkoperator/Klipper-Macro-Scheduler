#!/usr/bin/env python3
"""
Klipper Macro Scheduler installer.

Performs the following steps:
  - Copies the Moonraker component and web UI into their standard locations.
  - Deploys the KlipperScreen panels (listing + editor) to the configuration
    directory and mirrors them into the KlipperScreen source tree when present.
  - Ensures moonraker.conf contains the required [macro_scheduler] section and
    update_manager stanza (appended when missing).
  - Ensures KlipperScreen.conf exposes menu entries for the new panels.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from textwrap import dedent


SCRIPT_DIR = Path(__file__).resolve().parent

MOONRAKER_COMPONENTS_DIR = Path.home() / "moonraker" / "moonraker" / "components"
MAINSAIL_DIR = Path.home() / "mainsail"
CONFIG_DIR = Path.home() / "printer_data" / "config"
KLIPPERSCREEN_PANEL_DIR = CONFIG_DIR / "KlipperScreen" / "panels"
KLIPPERSCREEN_SRC_DIR = Path.home() / "KlipperScreen" / "panels"

PANEL_FILES = ("macro_scheduler.py", "macro_scheduler_editor.py")


@dataclass
class InstallResult:
    copied_files: list[str]
    warnings: list[str]


def copy_file(src: Path, dst: Path, *, chmod: int | None = 0o644) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if chmod is not None:
        dst.chmod(chmod)


def backup_file(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak{timestamp}")
    shutil.copy2(path, backup)
    return backup


def ensure_moonraker_config(config_path: Path) -> list[str]:
    if not config_path.exists():
        return [f"moonraker.conf not found at {config_path} (skipped automatic config)"]

    text = config_path.read_text()
    changed = False

    macro_section = "\n[macro_scheduler]\n# This enables the macro scheduler component\n"
    if "[macro_scheduler]" not in text:
        text = text.rstrip() + macro_section
        changed = True

    update_block = dedent(
        """

        [update_manager macro_scheduler]
        type: git_repo
        path: ~/macro_scheduler
        origin: https://github.com/darkoperator/klipper-macro-scheduler.git
        primary_branch: main
        managed_services: moonraker
        install_script: install.py
        """
    )
    if "[update_manager macro_scheduler]" not in text:
        text = text.rstrip() + update_block
        changed = True

    if changed:
        backup = backup_file(config_path)
        config_path.write_text(text.rstrip() + "\n")
        return [f"Updated moonraker.conf (backup saved to {backup.name})"]
    return []


def ensure_klipperscreen_config(config_path: Path) -> list[str]:
    if not config_path.exists():
        return [f"KlipperScreen.conf not found at {config_path} (skipped panel menu entries)"]

    text = config_path.read_text()
    changed = False

    list_entry = dedent(
        """

        [menu __main macro_scheduler]
        name: Macro Scheduler
        panel: macro_scheduler
        icon: clock
        """
    )
    editor_entry = dedent(
        """

        [menu __main macro_scheduler_editor]
        name: Macro Scheduler Editor
        panel: macro_scheduler_editor
        icon: clock
        """
    )

    if "panel: macro_scheduler_editor" not in text:
        text = text.rstrip() + editor_entry
        changed = True

    if "panel: macro_scheduler" not in text:
        text = text.rstrip() + list_entry
        changed = True

    if changed:
        backup = backup_file(config_path)
        config_path.write_text(text.rstrip() + "\n")
        return [f"Updated KlipperScreen.conf (backup saved to {backup.name})"]
    return []


def install(dry_run: bool = False) -> InstallResult:
    copied: list[str] = []
    warnings: list[str] = []

    if dry_run:
        print("Running in dry-run mode. No files will be modified.\n")

    # Component
    component_src = SCRIPT_DIR / "macro_scheduler.py"
    component_dst = MOONRAKER_COMPONENTS_DIR / "macro_scheduler.py"
    if dry_run:
        print(f"[DRY] Would copy {component_src} -> {component_dst}")
    else:
        copy_file(component_src, component_dst)
        copied.append(str(component_dst))

    # Web UI
    ui_src = SCRIPT_DIR / "scheduler_ui.html"
    ui_dst = MAINSAIL_DIR / "scheduler.html"
    if dry_run:
        print(f"[DRY] Would copy {ui_src} -> {ui_dst}")
    else:
        copy_file(ui_src, ui_dst)
        copied.append(str(ui_dst))

    # KlipperScreen panels
    for panel in PANEL_FILES:
        src_path = SCRIPT_DIR / "klipperscreen" / "panels" / panel
        if not src_path.exists():
            warnings.append(f"Panel source missing: {src_path}")
            continue

        config_dst = KLIPPERSCREEN_PANEL_DIR / panel
        if dry_run:
            print(f"[DRY] Would copy {src_path} -> {config_dst}")
        else:
            copy_file(src_path, config_dst)
            copied.append(str(config_dst))

        if KLIPPERSCREEN_SRC_DIR.exists():
            src_dst = KLIPPERSCREEN_SRC_DIR / panel
            if dry_run:
                print(f"[DRY] Would copy {src_path} -> {src_dst}")
            else:
                copy_file(src_path, src_dst)
                copied.append(str(src_dst))
        else:
            warnings.append(f"KlipperScreen source panels directory missing: {KLIPPERSCREEN_SRC_DIR} (skipped mirror copy)")

    if dry_run:
        print("\n[DRY] Would update configuration files:")
        ensure_moonraker_config(CONFIG_DIR / "moonraker.conf")
        ensure_klipperscreen_config(CONFIG_DIR / "KlipperScreen.conf")
    else:
        warnings.extend(ensure_moonraker_config(CONFIG_DIR / "moonraker.conf"))
        warnings.extend(ensure_klipperscreen_config(CONFIG_DIR / "KlipperScreen.conf"))

    return InstallResult(copied_files=copied, warnings=warnings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Klipper Macro Scheduler and KlipperScreen panels.")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without modifying files")
    args = parser.parse_args()

    result = install(dry_run=args.dry_run)

    if result.copied_files:
        print("\nCopied files:")
        for path in result.copied_files:
            print(f"  - {path}")

    if result.warnings:
        print("\nWarnings / notes:")
        for warning in result.warnings:
            print(f"  - {warning}")

    if not args.dry_run:
        print(
            "\nInstallation complete.\n"
            "Next steps:\n"
            " 1. Verify moonraker.conf and KlipperScreen.conf updates (backups saved if modified).\n"
            " 2. Restart Moonraker: sudo systemctl restart moonraker\n"
            " 3. Restart KlipperScreen: sudo systemctl restart KlipperScreen\n"
            " 4. Access the web UI at http://your-printer-ip/scheduler.html\n"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
