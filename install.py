#!/usr/bin/env python3
# Copyright (C) 2025 Carlos Perez <carlos_perez@darkoperator.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
"""
Klipper Macro Scheduler installer.

Links the Moonraker component, web UI and KlipperScreen panels to this checkout,
so a `git pull` or an Update Manager update takes effect after a service
restart. Also adds the required entries to moonraker.conf and
KlipperScreen.conf, backing up each file it changes.

Run it again at any time; it only changes what is out of place. For a setup
with several printers, run it once per instance with --config-dir.
"""

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
PANEL_FILES = ("macro_scheduler.py", "macro_scheduler_editor.py")
WEB_PAGE = "scheduler.html"
DEFAULT_WEB_CLIENTS = ("mainsail", "fluidd")
ORIGIN_URL = "https://github.com/darkoperator/Klipper-Macro-Scheduler.git"


@dataclass
class Paths:
    moonraker: Path
    klipperscreen: Path
    web: List[Path]
    config: Path
    web_explicit: bool = False


@dataclass
class Report:
    dry_run: bool
    actions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def backup_file(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak{timestamp}")
    shutil.copy2(path, backup)
    return backup


def link_file(src: Path, dst: Path, report: Report) -> None:
    """Point dst at src, replacing an older copy or link."""
    if dst.is_symlink() and dst.resolve() == src.resolve():
        return
    report.actions.append(f"Link {dst} -> {src}")
    if report.dry_run:
        return
    temp = dst.with_name(dst.name + ".macro_scheduler_tmp")
    if temp.is_symlink() or temp.exists():
        temp.unlink()
    temp.symlink_to(src)
    os.replace(str(temp), str(dst))


def exclude_from_repo(repo: Path, relative_path: str, report: Report) -> None:
    """Stop the host repo reporting our link as an untracked source file.

    Moonraker's Update Manager warns about untracked source files, and removes
    them during a repair unless they are excluded.
    """
    info_dir = repo / ".git" / "info"
    if not info_dir.is_dir():
        return
    exclude = info_dir / "exclude"
    current = exclude.read_text() if exclude.exists() else ""
    if relative_path in current.splitlines():
        return
    report.actions.append(f"Add {relative_path} to {exclude}")
    if report.dry_run:
        return
    if current and not current.endswith("\n"):
        current += "\n"
    exclude.write_text(current + relative_path + "\n")


def has_section(text: str, name: str) -> bool:
    return re.search(rf"(?m)^\[{re.escape(name)}\]\s*$", text) is not None


def section_span(text: str, name: str) -> Optional[re.Match]:
    """Match a whole config section, from its header up to the next header."""
    return re.search(
        rf"(?ms)^\[{re.escape(name)}\]\s*$.*?(?=^\[|\Z)", text
    )


def write_config(path: Path, original: str, updated: str, report: Report) -> None:
    if updated == original:
        return
    if report.dry_run:
        report.actions.append(f"Update {path.name}")
        return
    backup = backup_file(path)
    path.write_text(updated.rstrip() + "\n")
    report.actions.append(f"Updated {path.name} (backup saved as {backup.name})")


def repo_config_path() -> str:
    try:
        return "~/" + str(SCRIPT_DIR.relative_to(Path.home()))
    except ValueError:
        return str(SCRIPT_DIR)


def add_persistent_web_page(text: str, client: str, report: Report) -> str:
    """Keep the web page when Moonraker replaces the web client's folder."""
    section = f"update_manager {client}"
    match = section_span(text, section)
    if match is None:
        report.warnings.append(
            f"No [{section}] section found in moonraker.conf. If that client is "
            f"updated through Moonraker, add 'persistent_files: {WEB_PAGE}' to its "
            "section or the page will be removed by each update."
        )
        return text
    body = match.group(0)
    if WEB_PAGE in body:
        return text
    if re.search(r"(?m)^persistent_files\s*[:=]", body):
        report.warnings.append(
            f"[{section}] already sets persistent_files. Add {WEB_PAGE} to that "
            "list or the page will be removed by each update."
        )
        return text
    header, _, rest = body.partition("\n")
    updated = f"{header}\npersistent_files: {WEB_PAGE}\n{rest}"
    return text[:match.start()] + updated + text[match.end():]


def remove_install_script(text: str) -> str:
    """Drop the deprecated option. Moonraker never ran the script anyway."""
    match = section_span(text, "update_manager macro_scheduler")
    if match is None:
        return text
    body = re.sub(r"(?m)^install_script\s*[:=].*\n?", "", match.group(0))
    return text[:match.start()] + body + text[match.end():]


def update_moonraker_config(paths: Paths, web_dirs: List[Path], report: Report) -> None:
    config_path = paths.config / "moonraker.conf"
    if not config_path.exists():
        report.warnings.append(
            f"moonraker.conf not found at {config_path}. Add the sections from the "
            "README yourself."
        )
        return
    original = config_path.read_text()
    text = original
    if not has_section(text, "macro_scheduler"):
        text = text.rstrip() + "\n\n[macro_scheduler]\n"
    if has_section(text, "update_manager macro_scheduler"):
        text = remove_install_script(text)
    else:
        text = text.rstrip() + (
            "\n\n[update_manager macro_scheduler]\n"
            "type: git_repo\n"
            f"path: {repo_config_path()}\n"
            f"origin: {ORIGIN_URL}\n"
            "primary_branch: main\n"
            "managed_services: moonraker\n"
        )
    for web_dir in web_dirs:
        text = add_persistent_web_page(text, web_dir.name, report)
    write_config(config_path, original, text, report)


def update_klipperscreen_config(paths: Paths, report: Report) -> None:
    config_path = paths.config / "KlipperScreen.conf"
    if not config_path.exists():
        report.warnings.append(
            f"KlipperScreen.conf not found at {config_path}, so no menu entry was "
            "added. See the README."
        )
        return
    original = config_path.read_text()
    if re.search(r"(?m)^panel\s*[:=]\s*macro_scheduler\s*$", original):
        return
    text = original.rstrip() + (
        "\n\n[menu __main macro_scheduler]\n"
        "name: Macro Scheduler\n"
        "panel: macro_scheduler\n"
        "icon: clock\n"
    )
    write_config(config_path, original, text, report)


def install(paths: Paths, dry_run: bool) -> Report:
    report = Report(dry_run=dry_run)

    components = paths.moonraker / "moonraker" / "components"
    if not components.is_dir():
        raise SystemExit(
            f"Moonraker components folder not found: {components}\n"
            "Nothing was changed. Use --moonraker-dir if Moonraker is elsewhere."
        )
    link_file(SCRIPT_DIR / "macro_scheduler.py", components / "macro_scheduler.py", report)
    exclude_from_repo(paths.moonraker, "moonraker/components/macro_scheduler.py", report)

    web_dirs = [path for path in paths.web if path.is_dir()]
    for path in paths.web:
        if path not in web_dirs and paths.web_explicit:
            report.warnings.append(f"Web folder not found, skipped: {path}")
    if not web_dirs:
        report.warnings.append(
            "No web client folder found (looked for Mainsail and Fluidd), so the web "
            "UI was not installed. Use --web-dir to set the location."
        )
    for web_dir in web_dirs:
        link_file(SCRIPT_DIR / "scheduler_ui.html", web_dir / WEB_PAGE, report)

    panels_dir = paths.klipperscreen / "panels"
    if panels_dir.is_dir():
        for panel in PANEL_FILES:
            link_file(SCRIPT_DIR / "klipperscreen" / "panels" / panel, panels_dir / panel, report)
            exclude_from_repo(paths.klipperscreen, f"panels/{panel}", report)
        update_klipperscreen_config(paths, report)
    else:
        report.warnings.append(
            f"KlipperScreen not found at {paths.klipperscreen}, so its panels were "
            "skipped. Use --klipperscreen-dir if it is elsewhere."
        )

    update_moonraker_config(paths, web_dirs, report)
    return report


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install Klipper Macro Scheduler and its KlipperScreen panels."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would change without changing anything")
    parser.add_argument("--moonraker-dir", type=Path, default=Path.home() / "moonraker",
                        help="Moonraker checkout (default: ~/moonraker)")
    parser.add_argument("--klipperscreen-dir", type=Path,
                        default=Path.home() / "KlipperScreen",
                        help="KlipperScreen checkout (default: ~/KlipperScreen)")
    parser.add_argument("--web-dir", type=Path, action="append", default=None,
                        help="web client folder; may be repeated "
                             "(default: ~/mainsail and ~/fluidd if present)")
    parser.add_argument("--config-dir", type=Path,
                        default=Path.home() / "printer_data" / "config",
                        help="printer config folder (default: ~/printer_data/config)")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    paths = Paths(
        moonraker=args.moonraker_dir,
        klipperscreen=args.klipperscreen_dir,
        web=args.web_dir or [Path.home() / name for name in DEFAULT_WEB_CLIENTS],
        config=args.config_dir,
        web_explicit=args.web_dir is not None,
    )
    if args.dry_run:
        print("Dry run: nothing will be changed.\n")

    report = install(paths, args.dry_run)

    if report.actions:
        print("Would do:" if args.dry_run else "Done:")
        for action in report.actions:
            print(f"  - {action}")
    else:
        print("Everything is already in place.")
    if report.warnings:
        print("\nWarnings:")
        for warning in report.warnings:
            print(f"  - {warning}")
    if not args.dry_run:
        print(
            "\nNext steps:\n"
            " 1. Restart Moonraker: sudo systemctl restart moonraker\n"
            " 2. Restart KlipperScreen: sudo systemctl restart KlipperScreen\n"
            " 3. Open the web UI at http://your-printer-ip/scheduler.html"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
