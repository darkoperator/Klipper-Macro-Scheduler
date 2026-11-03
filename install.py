#!/usr/bin/env python3
# Copyright (C) 2025 Carlos Perez <carlos_perez@darkoperator.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
"""
Klipper Macro Scheduler installer.

Links the Moonraker component, web UI and KlipperScreen panels to this checkout,
so a `git pull` or an Update Manager update takes effect after a service
restart. Also adds the required entries to moonraker.conf and
KlipperScreen.conf, backing up each file it changes, and adds a Git hook so
it runs again after each Update Manager update.

Run it again at any time; it only changes what is out of place. For a setup
with several printers, run it once per instance with --config-dir.
"""

import argparse
import os
import re
import shlex
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
INCLUDE_RE = re.compile(r"^\[include\s+([^\]]+?)\s*\]\s*$", re.MULTILINE)
UPDATE_SECTION_RE = re.compile(
    r"^\[update_manager\s+([^\]]+?)\s*\]\s*$.*?(?=^\[|\Z)", re.MULTILINE | re.DOTALL
)
# The option and any indented lines that continue its list.
PERSISTENT_FILES_RE = re.compile(
    r"^persistent_files\s*[:=][^\n]*(?:\n|\Z)(?:[ \t]+\S[^\n]*(?:\n|\Z))*", re.MULTILINE
)


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


HOOK_MARKER = "# Added by Klipper Macro Scheduler's install.py."
HOOK_HEADER = (
    "#!/bin/sh\n"
    f"{HOOK_MARKER}\n"
    "# Moonraker's Update Manager runs `git pull` here but never runs install\n"
    "# scripts, so Git runs this after each update to re-run the installer.\n"
    "# One line per printer instance; delete a line to stop updating it.\n"
)


def installer_command(paths: Paths) -> List[str]:
    """The command that repeats this install, with every path made absolute."""
    command = [
        sys.executable, str(SCRIPT_DIR / "install.py"),
        "--config-dir", str(paths.config.resolve()),
        "--moonraker-dir", str(paths.moonraker.resolve()),
        "--klipperscreen-dir", str(paths.klipperscreen.resolve()),
    ]
    # Default web folders are looked up again each time, so a web client
    # installed later is picked up.
    if paths.web_explicit:
        for web_dir in paths.web:
            command += ["--web-dir", str(web_dir.resolve())]
    return command


def config_dir_of(line: str) -> Optional[str]:
    try:
        words = shlex.split(line)
    except ValueError:
        return None
    if "--config-dir" in words[:-1]:
        return words[words.index("--config-dir") + 1]
    return None


def install_update_hook(paths: Paths, report: Report) -> None:
    """Have Git re-run the installer after Moonraker updates this repo.

    Moonraker updates with `git pull`, which runs post-merge. Recovery and
    rollback use `git reset --hard`, which doesn't; the next normal update
    catches up.
    """
    git_dir = SCRIPT_DIR / ".git"
    if not git_dir.is_dir():
        return
    hook = git_dir / "hooks" / "post-merge"
    command = installer_command(paths)
    line = " ".join(shlex.quote(word) for word in command)

    current = hook.read_text() if hook.exists() else None
    if current is not None and HOOK_MARKER not in current:
        report.warnings.append(
            f"{hook} already exists and wasn't written by this installer, so it was "
            "left alone and updates won't re-run the installer. To fix, add this "
            f"line to it:\n      {line}"
        )
        return

    config_dir = str(paths.config.resolve())
    kept = []
    if current is not None:
        kept = [
            existing for existing in current.splitlines()
            if existing.strip() and not existing.startswith("#")
            and config_dir_of(existing) != config_dir
        ]
    updated = HOOK_HEADER + "".join(f"{existing}\n" for existing in kept + [line])
    if updated == current:
        return
    report.actions.append(f"Write update hook {hook}")
    if report.dry_run:
        return
    hook.parent.mkdir(exist_ok=True)
    hook.write_text(updated)
    hook.chmod(0o755)


def has_section(text: str, name: str) -> bool:
    return re.search(rf"(?m)^\[{re.escape(name)}\]\s*$", text) is not None


def section_span(text: str, name: str) -> Optional[re.Match]:
    """Match a whole config section, from its header up to the next header."""
    return re.search(
        rf"(?ms)^\[{re.escape(name)}\]\s*$.*?(?=^\[|\Z)", text
    )


def config_files(main_config: Path) -> List[Path]:
    """Return a config file and every file it includes, as Moonraker reads them."""
    found: List[Path] = []
    seen = set()

    def visit(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(path)
        for pattern in INCLUDE_RE.findall(path.read_text()):
            if pattern.startswith("/"):
                absolute = Path(pattern)
                matches = absolute.parent.glob(absolute.name)
            else:
                matches = path.parent.glob(pattern)
            for match in sorted(matches):
                if match.is_file():
                    visit(match)

    visit(main_config)
    return found


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


def section_updates_folder(name: str, body: str, web_dir: Path) -> bool:
    """Tell whether an update_manager section manages a web client folder."""
    path_option = re.search(r"(?m)^path\s*[:=]\s*(\S+)", body)
    if path_option is not None:
        return Path(path_option.group(1)).expanduser().resolve() == web_dir.resolve()
    return name.split()[-1] == web_dir.name


def add_page_to_section(body: str) -> str:
    """Add the web page to a section's persistent_files list."""
    existing = PERSISTENT_FILES_RE.search(body)
    if existing is None:
        header, _, rest = body.partition("\n")
        return f"{header}\npersistent_files: {WEB_PAGE}\n{rest}"
    if WEB_PAGE in existing.group(0).replace(":", " ").replace("=", " ").split():
        return body
    option = existing.group(0)
    if not option.endswith("\n"):
        option += "\n"
    return body[:existing.start()] + option + f"    {WEB_PAGE}\n" + body[existing.end():]


def protect_web_page(text: str, web_dirs: List[Path]) -> str:
    """Keep the page when Moonraker replaces a web client's folder.

    Moonraker deletes everything in the folder during an update except
    persistent_files. A client with no section is never updated by Moonraker, so
    it needs nothing. If one is added later, running the installer again covers it.
    """
    def update_section(match: "re.Match[str]") -> str:
        body = match.group(0)
        if any(section_updates_folder(match.group(1), body, path) for path in web_dirs):
            return add_page_to_section(body)
        return body

    return UPDATE_SECTION_RE.sub(update_section, text)


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
    originals = {path: path.read_text() for path in config_files(config_path)}
    updated = dict(originals)
    all_text = "\n".join(originals.values())
    if not has_section(all_text, "macro_scheduler"):
        updated[config_path] = updated[config_path].rstrip() + "\n\n[macro_scheduler]\n"
    if not has_section(all_text, "update_manager macro_scheduler"):
        updated[config_path] = updated[config_path].rstrip() + (
            "\n\n[update_manager macro_scheduler]\n"
            "type: git_repo\n"
            f"path: {repo_config_path()}\n"
            f"origin: {ORIGIN_URL}\n"
            "primary_branch: main\n"
            "managed_services: moonraker\n"
        )
    for path, text in updated.items():
        text = protect_web_page(remove_install_script(text), web_dirs)
        write_config(path, originals[path], text, report)


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
    install_update_hook(paths, report)
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
