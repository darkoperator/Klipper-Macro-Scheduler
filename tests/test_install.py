import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

INSTALLER = ROOT / "install.py"
MAINSAIL_SECTION = (
    "[update_manager mainsail]\ntype: web\nchannel: stable\n"
    "repo: mainsail-crew/mainsail\npath: ~/mainsail\n"
)


class InstallCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()
        self.config = self.home / "printer_data" / "config"
        self.config.mkdir(parents=True)
        self.components = self.home / "moonraker" / "moonraker" / "components"
        self.components.mkdir(parents=True)
        (self.home / "moonraker" / ".git" / "info").mkdir(parents=True)
        self.ks_panels = self.home / "KlipperScreen" / "panels"
        self.ks_panels.mkdir(parents=True)
        (self.home / "KlipperScreen" / ".git" / "info").mkdir(parents=True)
        (self.home / "mainsail").mkdir()
        self.moonraker_conf = self.config / "moonraker.conf"
        self.moonraker_conf.write_text("[server]\nhost: 0.0.0.0\n\n" + MAINSAIL_SECTION)
        self.ks_conf = self.config / "KlipperScreen.conf"
        self.ks_conf.write_text("[main]\n")

    def run_installer(self, *args, check=True):
        env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, str(INSTALLER), *args],
            env=env, capture_output=True, text=True,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def tree(self):
        return sorted(
            (str(p), p.read_text() if p.is_file() else None)
            for p in self.home.rglob("*")
        )


class Deployment(InstallCase):
    def test_files_are_symlinks_into_the_repo_so_updates_take_effect(self):
        self.run_installer()
        for link, source in [
            (self.components / "macro_scheduler.py", "macro_scheduler.py"),
            (self.home / "mainsail" / "scheduler.html", "scheduler_ui.html"),
            (self.ks_panels / "macro_scheduler.py", "klipperscreen/panels/macro_scheduler.py"),
            (self.ks_panels / "macro_scheduler_editor.py", "klipperscreen/panels/macro_scheduler_editor.py"),
        ]:
            with self.subTest(link=link):
                self.assertTrue(link.is_symlink())
                self.assertEqual(link.resolve(), (ROOT / source).resolve())

    def test_copies_from_an_older_install_are_replaced(self):
        old = self.components / "macro_scheduler.py"
        old.write_text("old copy")
        self.run_installer()
        self.assertTrue(old.is_symlink())

    def test_files_are_excluded_from_host_repos(self):
        self.run_installer()
        moonraker = (self.home / "moonraker/.git/info/exclude").read_text()
        self.assertIn("moonraker/components/macro_scheduler.py", moonraker)
        klipperscreen = (self.home / "KlipperScreen/.git/info/exclude").read_text()
        self.assertIn("panels/macro_scheduler.py", klipperscreen)
        self.assertIn("panels/macro_scheduler_editor.py", klipperscreen)

    def test_running_twice_changes_nothing(self):
        self.run_installer()
        first = self.tree()
        self.run_installer()
        self.assertEqual(self.tree(), first)

    def test_no_panel_copy_is_left_in_the_unused_config_directory(self):
        self.run_installer()
        self.assertFalse((self.config / "KlipperScreen").exists())


class WebClients(InstallCase):
    def test_fluidd_is_supported(self):
        (self.home / "mainsail").rmdir()
        (self.home / "fluidd").mkdir()
        self.run_installer()
        self.assertTrue((self.home / "fluidd" / "scheduler.html").is_symlink())
        self.assertFalse((self.home / "mainsail").exists())

    def test_both_web_clients_are_supported(self):
        (self.home / "fluidd").mkdir()
        self.run_installer()
        self.assertTrue((self.home / "fluidd" / "scheduler.html").is_symlink())
        self.assertTrue((self.home / "mainsail" / "scheduler.html").is_symlink())

    def test_missing_web_client_warns_and_creates_nothing(self):
        (self.home / "mainsail").rmdir()
        result = self.run_installer()
        self.assertFalse((self.home / "mainsail").exists())
        self.assertIn("web", result.stdout.lower())

    def test_web_page_survives_mainsail_updates(self):
        self.run_installer()
        text = self.moonraker_conf.read_text()
        section = text.split("[update_manager mainsail]")[1].split("\n[")[0]
        self.assertIn("persistent_files:", section)
        self.assertIn("scheduler.html", section)

    def test_existing_persistent_files_are_left_alone_with_a_warning(self):
        self.moonraker_conf.write_text(
            "[update_manager mainsail]\ntype: web\npersistent_files:\n  theme.css\n"
        )
        result = self.run_installer()
        self.assertIn("theme.css", self.moonraker_conf.read_text())
        self.assertNotIn("scheduler.html", self.moonraker_conf.read_text())
        self.assertIn("persistent_files", result.stdout)


class MissingPieces(InstallCase):
    def test_missing_moonraker_is_an_error_and_changes_nothing(self):
        for path in sorted(self.home.joinpath("moonraker").rglob("*"), reverse=True):
            path.rmdir()
        self.home.joinpath("moonraker").rmdir()
        before = self.tree()
        result = self.run_installer(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.tree(), before)

    def test_missing_klipperscreen_is_skipped_without_creating_it(self):
        for path in sorted(self.home.joinpath("KlipperScreen").rglob("*"), reverse=True):
            path.rmdir()
        self.home.joinpath("KlipperScreen").rmdir()
        result = self.run_installer()
        self.assertFalse((self.home / "KlipperScreen").exists())
        self.assertIn("KlipperScreen", result.stdout)
        self.assertNotIn("macro_scheduler", self.ks_conf.read_text())


class Paths(InstallCase):
    def test_a_second_instance_can_be_targeted(self):
        other = self.home / "printer_2_data" / "config"
        other.mkdir(parents=True)
        (other / "moonraker.conf").write_text("[server]\n")
        self.run_installer("--config-dir", str(other))
        self.assertIn("[macro_scheduler]", (other / "moonraker.conf").read_text())
        self.assertNotIn("[macro_scheduler]", self.moonraker_conf.read_text())

    def test_install_directories_can_be_overridden(self):
        moonraker = self.home / "other_moonraker"
        (moonraker / "moonraker" / "components").mkdir(parents=True)
        web = self.home / "custom_web"
        web.mkdir()
        self.run_installer("--moonraker-dir", str(moonraker), "--web-dir", str(web))
        self.assertTrue((moonraker / "moonraker/components/macro_scheduler.py").is_symlink())
        self.assertTrue((web / "scheduler.html").is_symlink())
        self.assertFalse((self.home / "mainsail" / "scheduler.html").exists())


class MoonrakerConfig(InstallCase):
    def test_sections_are_added(self):
        self.run_installer()
        text = self.moonraker_conf.read_text()
        self.assertIn("[macro_scheduler]", text)
        self.assertIn("[update_manager macro_scheduler]", text)

    def test_update_section_does_not_use_install_script_or_invalid_services(self):
        self.run_installer()
        section = self.moonraker_conf.read_text().split("[update_manager macro_scheduler]")[1]
        self.assertNotIn("install_script", section)
        self.assertIn("managed_services: moonraker", section)
        self.assertNotIn("KlipperScreen", section)

    def test_deprecated_install_script_is_removed_from_existing_section(self):
        self.moonraker_conf.write_text(
            "[update_manager macro_scheduler]\ntype: git_repo\n"
            "path: ~/macro_scheduler\ninstall_script: install.py\n\n"
            "[update_manager other]\ninstall_script: keep.sh\n"
        )
        self.run_installer()
        text = self.moonraker_conf.read_text()
        self.assertNotIn("install_script: install.py", text)
        self.assertIn("install_script: keep.sh", text)

    def test_section_mentioned_only_in_a_comment_is_still_added(self):
        self.moonraker_conf.write_text("# [macro_scheduler] goes here\n")
        self.run_installer()
        self.assertIn("\n[macro_scheduler]", self.moonraker_conf.read_text())

    def test_config_is_backed_up_when_changed(self):
        self.run_installer()
        self.assertTrue(list(self.config.glob("moonraker.conf.bak*")))


class KlipperScreenConfig(InstallCase):
    def test_list_panel_menu_entry_is_added(self):
        self.run_installer()
        self.assertRegex(self.ks_conf.read_text(), r"(?m)^panel: macro_scheduler$")

    def test_editor_gets_no_menu_entry_because_the_list_opens_it(self):
        self.run_installer()
        self.assertNotIn("macro_scheduler_editor", self.ks_conf.read_text())

    def test_existing_editor_entry_does_not_block_the_list_entry(self):
        self.ks_conf.write_text(
            "[menu __main macro_scheduler_editor]\npanel: macro_scheduler_editor\n"
        )
        self.run_installer()
        self.assertRegex(self.ks_conf.read_text(), r"(?m)^panel: macro_scheduler$")


class DryRun(InstallCase):
    def test_dry_run_changes_nothing(self):
        before = self.tree()
        result = self.run_installer("--dry-run")
        self.assertEqual(self.tree(), before)
        self.assertIn("moonraker.conf", result.stdout)


class LegacyScript(InstallCase):
    def test_install_sh_delegates_to_install_py(self):
        script = (ROOT / "install.sh").read_text()
        self.assertIn("install.py", script)
        env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")
        subprocess.run(["bash", str(ROOT / "install.sh")], env=env, check=True, capture_output=True)
        self.assertTrue((self.components / "macro_scheduler.py").is_symlink())


if __name__ == "__main__":
    unittest.main()
