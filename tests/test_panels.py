"""Logic tests for the KlipperScreen panels.

GTK isn't available in CI, so widgets are mocks. These tests cover what the
panels send and decide, not how they render.
"""
import builtins
import sys
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from helpers import ROOT, load_module

PANELS = ROOT / "klipperscreen" / "panels"


class FakeScreenPanel:
    def __init__(self, screen, title, **kwargs):
        self._screen = screen
        self.labels = {}
        self.content = MagicMock()
        self.bts = 1


def load_panel(filename):
    """Import a panel file with stand-ins for GTK and KlipperScreen."""
    builtins._ = lambda text: text
    gi = types.ModuleType("gi")
    gi.require_version = lambda *args: None
    repository = types.ModuleType("gi.repository")
    repository.Gtk = MagicMock()
    repository.GLib = MagicMock()
    repository.GLib.markup_escape_text = lambda text: text
    repository.Pango = MagicMock()
    includes = types.ModuleType("ks_includes")
    screen_panel = types.ModuleType("ks_includes.screen_panel")
    screen_panel.ScreenPanel = FakeScreenPanel
    sys.modules.update({
        "gi": gi, "gi.repository": repository,
        "ks_includes": includes, "ks_includes.screen_panel": screen_panel,
    })
    return load_module(f"panel_{filename}", PANELS / f"{filename}.py"), repository.Gtk


def make_panel(module, use_24h=True):
    panel = module.Panel.__new__(module.Panel)
    panel._screen = MagicMock()
    panel._screen._ws.send_method.return_value = True
    panel._gtk = MagicMock()
    panel._config = MagicMock()
    panel._config.get_main_config.return_value.getboolean.return_value = use_24h
    panel.labels = {"status": MagicMock(), "schedule_grid": MagicMock()}
    panel.labels["schedule_grid"].get_children.return_value = []
    panel.bts = 1
    return panel


def ok(**result):
    return {"result": result}


def err(message):
    return {"error": {"code": 400, "message": message}}


class ListPanel(unittest.TestCase):
    def setUp(self):
        self.module, self.Gtk = load_panel("macro_scheduler")
        self.panel = make_panel(self.module)
        self.send = self.panel._screen._ws.send_method

    def test_opening_the_panel_loads_schedules_over_the_websocket(self):
        self.panel.activate()
        self.assertEqual(self.send.call_args[0][0], "server.macro_scheduler.schedules")

    def test_no_rest_client_is_needed(self):
        del self.panel._screen.apiclient
        self.panel.refresh_schedules()
        self.send.assert_called_once()

    def test_disconnected_socket_shows_a_message_instead_of_loading_forever(self):
        self.send.return_value = False
        self.panel.refresh_schedules()
        self.panel.labels["status"].set_text.assert_called_with("Not connected")

    def test_load_failure_shows_the_server_message(self):
        self.panel._on_schedules_loaded(err("Stored schedules could not be read"), "m", {})
        self.panel.labels["status"].set_text.assert_called_with(
            "Stored schedules could not be read"
        )

    def test_loaded_schedules_update_the_status(self):
        self.panel._on_schedules_loaded(ok(schedules=[]), "m", {})
        self.panel.labels["status"].set_text.assert_called_with("0 schedule(s) loaded")

    def test_websocket_callback_returns_falsy_so_glib_does_not_repeat_it(self):
        self.assertFalse(self.panel._on_schedules_loaded(ok(schedules=[]), "m", {}))
        self.assertFalse(self.panel._on_action_done(ok(), "m", {}))

    def test_delete_asks_for_confirmation_first(self):
        self.panel._confirm_delete(None, 3, "Morning")
        self.panel._gtk.Dialog.assert_called_once()
        self.send.assert_not_called()

    def test_confirmed_delete_is_sent(self):
        dialog = MagicMock()
        self.panel._on_delete_response(dialog, self.Gtk.ResponseType.OK, 3)
        self.assertEqual(self.send.call_args[0][:2], ("server.macro_scheduler.delete", {"id": 3}))
        self.panel._gtk.remove_dialog.assert_called_with(dialog)

    def test_cancelled_delete_sends_nothing(self):
        self.panel._on_delete_response(MagicMock(), self.Gtk.ResponseType.CANCEL, 3)
        self.send.assert_not_called()

    def test_toggle_is_sent(self):
        self.panel._toggle_schedule(None, 3)
        self.assertEqual(self.send.call_args[0][:2], ("server.macro_scheduler.toggle", {"id": 3}))

    def test_action_error_shows_the_server_message(self):
        self.panel._on_action_done(err("Can't enable this schedule"), "m", {})
        self.panel._screen.show_popup_message.assert_called_once()
        self.assertIn("Can't enable", self.panel._screen.show_popup_message.call_args[0][0])

    def test_opening_the_editor_leaves_the_back_stack_alone(self):
        self.panel._screen._cur_panels = ["main", "macro_scheduler"]
        self.panel._open_creator()
        self.assertEqual(self.panel._screen._cur_panels, ["main", "macro_scheduler"])
        self.panel._screen.show_panel.assert_called_once()

    def test_next_run_is_readable_in_24_hour_time(self):
        text = self.panel._format_datetime("2026-11-03T21:05:00")
        self.assertIn("21:05", text)
        self.assertNotIn("T", text.split()[-1])

    def test_next_run_respects_12_hour_setting(self):
        panel = make_panel(self.module, use_24h=False)
        self.assertIn("09:05 PM", panel._format_datetime("2026-11-03T21:05:00"))

    def test_bad_time_is_shown_as_is(self):
        self.assertEqual(self.panel._format_datetime("soon"), "soon")

    def test_details_show_a_failed_last_run(self):
        details = self.panel._format_details({
            "macro": "HEAT", "schedule_type": "daily", "enabled": True,
            "next_run": "2026-11-03T21:05:00",
            "last_status": "failed", "last_error": "Unknown command",
        })
        self.assertIn("Unknown command", details)
        self.assertNotIn("2026-11-03T21:05:00", details)


class EditorPanel(unittest.TestCase):
    def setUp(self):
        self.module, self.Gtk = load_panel("macro_scheduler_editor")
        self.panel = make_panel(self.module)
        self.send = self.panel._screen._ws.send_method

    def time_controls(self, hour, minute, pm=None):
        controls = {"hour": MagicMock(), "minute": MagicMock(), "am": None, "pm": None}
        controls["hour"].get_value_as_int.return_value = hour
        controls["minute"].get_value_as_int.return_value = minute
        if pm is not None:
            controls["am"], controls["pm"] = MagicMock(), MagicMock()
            controls["am"].get_active.return_value = not pm
            controls["pm"].get_active.return_value = pm
        return controls

    def test_time_in_24_hour_mode(self):
        self.assertEqual(self.panel._get_time_value(self.time_controls(21, 5)), "21:05")

    def test_time_in_12_hour_mode(self):
        panel = make_panel(self.module, use_24h=False)
        for hour, pm, expected in [
            (12, False, "00:30"), (1, False, "01:30"), (12, True, "12:30"), (1, True, "13:30"),
        ]:
            with self.subTest(hour=hour, pm=pm):
                self.assertEqual(
                    panel._get_time_value(self.time_controls(hour, 30, pm=pm)), expected
                )

    def test_set_time_in_12_hour_mode_keeps_noon_as_pm(self):
        panel = make_panel(self.module, use_24h=False)
        controls = self.time_controls(1, 0, pm=False)
        panel._set_time(controls, 12, 0)
        controls["hour"].set_value.assert_called_with(12)
        controls["pm"].set_active.assert_called_with(True)
        controls["am"].set_active.assert_called_with(False)

    def test_default_once_time_is_always_in_the_future(self):
        for now in [
            datetime(2026, 11, 2, 15, 40), datetime(2026, 11, 2, 23, 59),
            datetime(2026, 11, 2, 0, 0),
        ]:
            with self.subTest(now=now):
                self.assertGreater(self.module.default_once_datetime(now), now)

    def test_once_in_the_past_is_refused_before_sending(self):
        self.panel._once_date_button = MagicMock()
        self.panel._once_date_value = (datetime.now() - timedelta(days=1)).date()
        self.panel._once_time_controls = self.time_controls(12, 0)
        with self.assertRaises(ValueError):
            self.panel._collect_once_fields()

    def test_create_sends_over_the_websocket(self):
        self.panel._collect_payload = lambda: {"name": "x"}
        self.panel._create_schedule(None)
        self.assertEqual(self.send.call_args[0][:2], ("server.macro_scheduler.add", {"name": "x"}))

    def test_create_when_disconnected_reports_it(self):
        self.send.return_value = False
        self.panel._collect_payload = lambda: {"name": "x"}
        self.panel._create_schedule(None)
        self.panel._screen.show_popup_message.assert_called_once()

    def test_server_rejection_shows_its_message_and_stays_on_the_form(self):
        self.panel._on_created(err("Date and time must be in the future"), "m", {})
        self.assertIn("future", self.panel._screen.show_popup_message.call_args[0][0])
        self.panel._screen._menu_go_back.assert_not_called()

    def test_success_returns_to_the_list(self):
        self.panel._on_created(ok(schedule={"id": 1}), "m", {})
        self.panel._screen._menu_go_back.assert_called_once()
        self.panel._screen.show_panel.assert_not_called()

    def test_cancel_goes_back_without_growing_the_stack(self):
        self.panel._go_back()
        self.panel._screen._menu_go_back.assert_called_once()
        self.panel._screen.show_panel.assert_not_called()

    def test_policy_settings_are_collected(self):
        self.panel._missed_switch = MagicMock()
        self.panel._printing_switch = MagicMock()
        self.panel._missed_switch.get_active.return_value = True
        self.panel._printing_switch.get_active.return_value = False
        self.assertEqual(
            self.panel._collect_policy_fields(),
            {"missed_run_policy": "run", "skip_if_printing": False},
        )

    def test_opening_the_editor_resets_the_form(self):
        self.panel._reset_form = MagicMock()
        self.panel.activate()
        self.panel._reset_form.assert_called_once()


if __name__ == "__main__":
    unittest.main()
