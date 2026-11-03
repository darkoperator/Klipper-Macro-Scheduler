import configparser
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

REPO_FILES = (
    "install.py", "install.sh", "macro_scheduler.py", "scheduler_ui.html",
    "klipperscreen/panels/macro_scheduler.py",
    "klipperscreen/panels/macro_scheduler_editor.py",
)
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}
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
        # A copy of this checkout, so the installer's update hook lands in the
        # temporary folder instead of the developer's own .git.
        self.repo = self.home / "macro_scheduler"
        self.copy_repo_files(self.repo)
        (self.repo / ".git" / "hooks").mkdir(parents=True)
        self.hook = self.repo / ".git" / "hooks" / "post-merge"

    @staticmethod
    def copy_repo_files(dest):
        for name in REPO_FILES:
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(ROOT / name), str(dest / name))

    def run_installer(self, *args, check=True):
        env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, str(self.repo / "install.py"), *args],
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
                self.assertEqual(link.resolve(), (self.repo / source).resolve())

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

    def persistent_files(self, path, section):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(str(path))
        value = parser.get(section, "persistent_files")
        return [line.strip() for line in value.splitlines() if line.strip()]

    def test_existing_multiline_list_gets_the_page_added(self):
        self.moonraker_conf.write_text(
            "[update_manager mainsail]\ntype: web\npath: ~/mainsail\n"
            "persistent_files:\n  theme.css\n  logo.png\nchannel: stable\n"
        )
        result = self.run_installer()
        self.assertEqual(
            self.persistent_files(self.moonraker_conf, "update_manager mainsail"),
            ["theme.css", "logo.png", "scheduler.html"],
        )
        self.assertIn("channel: stable", self.moonraker_conf.read_text())
        self.assertNotIn("Warnings", result.stdout)

    def test_existing_single_value_gets_the_page_added(self):
        self.moonraker_conf.write_text(
            "[update_manager mainsail]\ntype: web\npersistent_files: theme.css\n"
        )
        self.run_installer()
        self.assertEqual(
            self.persistent_files(self.moonraker_conf, "update_manager mainsail"),
            ["theme.css", "scheduler.html"],
        )

    def test_page_already_listed_is_not_added_again(self):
        self.moonraker_conf.write_text(
            "[update_manager mainsail]\ntype: web\npersistent_files:\n  scheduler.html\n"
        )
        self.run_installer()
        self.assertEqual(self.moonraker_conf.read_text().count("scheduler.html"), 1)

    def test_client_moonraker_does_not_update_gets_no_warning_or_section(self):
        (self.home / "fluidd").mkdir()
        result = self.run_installer()
        self.assertNotIn("fluidd", self.moonraker_conf.read_text())
        self.assertNotIn("Warnings", result.stdout)
        self.assertTrue((self.home / "fluidd" / "scheduler.html").is_symlink())

    def test_section_in_an_included_file_is_updated_there(self):
        included = self.config / "updates.conf"
        included.write_text(MAINSAIL_SECTION)
        self.moonraker_conf.write_text("[server]\n\n[include updates.conf]\n")
        self.run_installer()
        self.assertEqual(
            self.persistent_files(included, "update_manager mainsail"), ["scheduler.html"]
        )
        self.assertNotIn("update_manager mainsail", self.moonraker_conf.read_text())
        self.assertTrue(list(self.config.glob("updates.conf.bak*")))

    def test_includes_are_followed_through_globs_and_nesting(self):
        extras = self.config / "extras"
        extras.mkdir()
        (extras / "nested.conf").write_text(MAINSAIL_SECTION)
        (extras / "first.conf").write_text("[include nested.conf]\n")
        self.moonraker_conf.write_text("[include extras/f*.conf]\n")
        self.run_installer()
        self.assertEqual(
            self.persistent_files(extras / "nested.conf", "update_manager mainsail"),
            ["scheduler.html"],
        )

    def test_recursive_include_does_not_hang(self):
        (self.config / "a.conf").write_text("[include moonraker.conf]\n")
        self.moonraker_conf.write_text("[include a.conf]\n")
        self.run_installer()

    def test_macro_scheduler_section_in_an_include_is_not_duplicated(self):
        (self.config / "a.conf").write_text(
            "[macro_scheduler]\n\n[update_manager macro_scheduler]\ntype: git_repo\n"
            "install_script: install.py\n"
        )
        self.moonraker_conf.write_text("[include a.conf]\n")
        self.run_installer()
        self.assertNotIn("macro_scheduler", self.moonraker_conf.read_text())
        self.assertNotIn("install_script", (self.config / "a.conf").read_text())

    def test_section_is_matched_by_path_not_just_name(self):
        web = self.home / "custom_web"
        web.mkdir()
        self.moonraker_conf.write_text(
            "[update_manager my_client]\ntype: web\npath: ~/custom_web\n\n"
            "[update_manager mainsail]\ntype: web\npath: ~/mainsail\n"
        )
        self.run_installer("--web-dir", str(web))
        self.assertEqual(
            self.persistent_files(self.moonraker_conf, "update_manager my_client"),
            ["scheduler.html"],
        )
        self.assertNotIn(
            "persistent_files",
            self.moonraker_conf.read_text().split("[update_manager mainsail]")[1],
        )

    def test_section_named_for_a_client_at_another_path_is_not_changed(self):
        self.moonraker_conf.write_text(
            "[update_manager mainsail]\ntype: web\npath: ~/somewhere_else\n"
        )
        self.run_installer()
        self.assertNotIn("persistent_files", self.moonraker_conf.read_text())

    def test_older_client_section_name_is_recognized(self):
        self.moonraker_conf.write_text("[update_manager client mainsail]\ntype: web\n")
        self.run_installer()
        self.assertEqual(
            self.persistent_files(self.moonraker_conf, "update_manager client mainsail"),
            ["scheduler.html"],
        )


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


class UpdateHook(InstallCase):
    """Moonraker updates with `git pull` and never runs install scripts, so a
    post-merge hook in this repo re-runs the installer after each update."""

    def hook_lines(self):
        return [line for line in self.hook.read_text().splitlines()
                if "install.py" in line and not line.startswith("#")]

    def test_hook_is_installed_and_executable(self):
        self.run_installer()
        self.assertTrue(self.hook.is_file())
        self.assertTrue(os.stat(str(self.hook)).st_mode & stat.S_IXUSR)
        self.assertEqual(len(self.hook_lines()), 1)
        self.assertIn(str(self.config), self.hook_lines()[0])

    def test_hook_repeats_the_install_with_the_same_paths(self):
        moonraker = self.home / "other_moonraker"
        (moonraker / "moonraker" / "components").mkdir(parents=True)
        web = self.home / "custom_web"
        web.mkdir()
        self.run_installer("--moonraker-dir", str(moonraker), "--web-dir", str(web))
        line = self.hook_lines()[0]
        self.assertIn(str(moonraker), line)
        self.assertIn(str(web), line)
        self.assertNotIn("--dry-run", line)

    def test_default_web_folders_are_looked_up_again_on_each_update(self):
        self.run_installer()
        self.assertNotIn("--web-dir", self.hook_lines()[0])

    def test_each_printer_instance_gets_its_own_line(self):
        other = self.home / "printer_2_data" / "config"
        other.mkdir(parents=True)
        (other / "moonraker.conf").write_text("[server]\n")
        self.run_installer()
        self.run_installer("--config-dir", str(other))
        self.run_installer("--config-dir", str(other))
        lines = self.hook_lines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(any(str(other) in line for line in lines))

    def test_reinstalling_an_instance_with_new_paths_replaces_its_line(self):
        web = self.home / "custom_web"
        web.mkdir()
        self.run_installer()
        self.run_installer("--web-dir", str(web))
        lines = self.hook_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn(str(web), lines[0])

    def test_someone_elses_hook_is_left_alone_with_a_warning(self):
        self.hook.write_text("#!/bin/sh\necho mine\n")
        result = self.run_installer()
        self.assertEqual(self.hook.read_text(), "#!/bin/sh\necho mine\n")
        self.assertIn("post-merge", result.stdout)

    def test_not_a_git_checkout_is_skipped_quietly(self):
        shutil.rmtree(str(self.repo / ".git"))
        result = self.run_installer()
        self.assertFalse((self.repo / ".git").exists())
        self.assertNotIn("post-merge", result.stdout)

    def test_dry_run_does_not_write_the_hook(self):
        result = self.run_installer("--dry-run")
        self.assertFalse(self.hook.exists())
        self.assertIn("post-merge", result.stdout)

    @unittest.skipIf(shutil.which("git") is None, "git not installed")
    def test_git_pull_reruns_the_installer(self):
        env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1", **GIT_ENV)

        def git(cwd, *args):
            subprocess.run(["git", *args], cwd=str(cwd), env=env, check=True,
                           capture_output=True)

        upstream = self.home / "upstream"
        self.copy_repo_files(upstream)
        git(upstream, "init", "-q", "-b", "main")
        git(upstream, "add", "-A")
        git(upstream, "commit", "-q", "-m", "v1")
        shutil.rmtree(str(self.repo))
        git(self.home, "clone", "-q", str(upstream), str(self.repo))

        self.run_installer()
        link = self.components / "macro_scheduler.py"
        link.unlink()
        (upstream / "README.md").write_text("v2\n")
        git(upstream, "add", "-A")
        git(upstream, "commit", "-q", "-m", "v2")
        git(self.repo, "pull", "-q", "--ff-only")

        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), (self.repo / "macro_scheduler.py").resolve())


class LegacyScript(InstallCase):
    def test_install_sh_delegates_to_install_py(self):
        script = (self.repo / "install.sh").read_text()
        self.assertIn("install.py", script)
        env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")
        subprocess.run(["bash", str(self.repo / "install.sh")], env=env, check=True, capture_output=True)
        self.assertTrue((self.components / "macro_scheduler.py").is_symlink())


if __name__ == "__main__":
    unittest.main()
