# macro_scheduler.py
# KlipperScreen panel for the Klipper Macro Scheduler
#
# Copyright (C) 2025 Carlos Perez <carlos_perez@darkoperator.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GLib

from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    """KlipperScreen panel for viewing and managing Macro Scheduler entries."""

    def __init__(self, screen, title):
        title = title or _("Macro Scheduler")
        super().__init__(screen, title)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar.set_margin_top(0)
        toolbar.set_margin_bottom(2)

        refresh_btn = self._gtk.Button("refresh", _("Refresh"), "color1", self.bts * 0.7, Gtk.PositionType.LEFT, 1)
        refresh_btn.get_style_context().add_class("buttons_slim")
        refresh_btn.set_hexpand(False)
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.set_vexpand(False)
        refresh_btn.connect("clicked", self.refresh_schedules)
        toolbar.pack_start(refresh_btn, False, False, 0)

        add_btn = self._gtk.Button("custom-script", _("New"), "color3", self.bts * 0.7, Gtk.PositionType.LEFT, 1)
        add_btn.get_style_context().add_class("buttons_slim")
        add_btn.set_hexpand(False)
        add_btn.set_valign(Gtk.Align.CENTER)
        add_btn.set_vexpand(False)
        add_btn.connect("clicked", self._open_creator)
        toolbar.pack_start(add_btn, False, False, 0)

        self.labels["status"] = Gtk.Label(label=_("No schedules loaded"))
        self.labels["status"].set_xalign(0.0)
        self.labels["status"].set_yalign(0.5)
        self.labels["status"].set_hexpand(True)
        self.labels["status"].set_ellipsize(Pango.EllipsizeMode.END)
        toolbar.pack_start(self.labels["status"], True, True, 0)

        self.labels["schedule_grid"] = Gtk.Grid(
            row_spacing=8,
            column_spacing=12,
            hexpand=True,
            vexpand=True,
        )

        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.labels["schedule_grid"])

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        container.pack_start(toolbar, False, False, 0)
        container.pack_start(scroll, True, True, 0)

        self.content.add(container)

    def activate(self):
        # KlipperScreen caches panels, and calls this each time one is shown.
        self.refresh_schedules()

    # ------------------------------------------------------------------ helpers
    def _set_status(self, message: str):
        if "status" in self.labels:
            self.labels["status"].set_text(message)

    def _clear_schedule_rows(self):
        grid = self.labels["schedule_grid"]
        for child in grid.get_children():
            grid.remove(child)

    def _render_placeholder(self, message: str):
        self._clear_schedule_rows()
        placeholder = Gtk.Label(
            label=message,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=True,
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
        )
        self.labels["schedule_grid"].attach(placeholder, 0, 0, 1, 1)
        self.labels["schedule_grid"].show_all()

    def _format_datetime(self, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return str(value)
        use_24h = self._config.get_main_config().getboolean("24htime", True)
        return parsed.strftime("%a %b %d %H:%M" if use_24h else "%a %b %d %I:%M %p")

    def _format_last_result(self, schedule: Dict[str, Any]) -> Optional[str]:
        labels = {
            "ok": _("last run OK"),
            "running": _("running now"),
            "failed": _("last run failed"),
            "missed": _("last run missed"),
            "skipped": _("last run skipped"),
            "interrupted": _("last run interrupted"),
            "invalid": _("invalid"),
        }
        status = schedule.get("last_status")
        if status not in labels:
            return None
        error = schedule.get("last_error")
        return f"{labels[status]}: {error}" if error else labels[status]

    def _format_details(self, schedule: Dict[str, Any]) -> str:
        pieces: List[str] = []

        macro = schedule.get("macro")
        if macro:
            pieces.append(macro)

        schedule_type = schedule.get("schedule_type")
        if schedule_type:
            pieces.append(schedule_type)

        if schedule.get("enabled"):
            next_run = schedule.get("next_run")
            if next_run:
                pieces.append(_("next: %s") % self._format_datetime(next_run))
        else:
            pieces.append(_("disabled"))

        params = schedule.get("params")
        if isinstance(params, dict) and params:
            formatted_params = " ".join(f"{k}={v}" for k, v in params.items())
            pieces.append(formatted_params)

        last_result = self._format_last_result(schedule)
        if last_result:
            pieces.append(last_result)

        return " · ".join(pieces) if pieces else _("No additional details")

    def _render_schedule_rows(self, schedules: List[Dict[str, Any]]):
        self._clear_schedule_rows()
        grid = self.labels["schedule_grid"]

        if not schedules:
            self._render_placeholder(_("No schedules configured"))
            return

        schedules = sorted(schedules, key=lambda s: s.get("name", "").lower())
        for idx, schedule in enumerate(schedules):
            schedule_id = schedule.get("id")
            if schedule_id is None:
                continue

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, hexpand=True)
            row.get_style_context().add_class("frame-item")

            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)

            name = schedule.get("name") or _("Unnamed")
            name_label = Gtk.Label(
                halign=Gtk.Align.START,
                valign=Gtk.Align.START,
                hexpand=True,
                wrap=True,
                wrap_mode=Pango.WrapMode.WORD_CHAR,
            )
            name_label.set_markup(f"<big><b>{GLib.markup_escape_text(name)}</b></big>")
            info_box.add(name_label)

            details_label = Gtk.Label(
                label=self._format_details(schedule),
                halign=Gtk.Align.START,
                valign=Gtk.Align.START,
                hexpand=True,
                wrap=True,
                wrap_mode=Pango.WrapMode.WORD_CHAR,
            )
            info_box.add(details_label)

            row.add(info_box)

            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            toggle_icon = "pause" if schedule.get("enabled") else "resume"
            toggle_label = _("Disable") if schedule.get("enabled") else _("Enable")
            toggle_btn = self._gtk.Button(toggle_icon, toggle_label, "color3", self.bts, Gtk.PositionType.LEFT, 1)
            toggle_btn.get_style_context().add_class("buttons_slim")
            toggle_btn.set_hexpand(False)
            toggle_btn.connect("clicked", self._toggle_schedule, int(schedule_id))
            button_box.add(toggle_btn)

            delete_btn = self._gtk.Button("delete", _("Delete"), "color2", self.bts, Gtk.PositionType.LEFT, 1)
            delete_btn.get_style_context().add_class("buttons_slim")
            delete_btn.set_hexpand(False)
            delete_btn.connect("clicked", self._confirm_delete, int(schedule_id), name)
            button_box.add(delete_btn)

            row.add(button_box)
            grid.attach(row, 0, idx, 1, 1)

        grid.show_all()

    # --------------------------------------------------------------- API calls
    def _send(self, method: str, params: Dict[str, Any], callback) -> bool:
        """Send a Moonraker request, returning False if there's no connection."""
        websocket = getattr(self._screen, "_ws", None)
        if websocket is None:
            return False
        return bool(websocket.send_method(method, params, callback))

    def refresh_schedules(self, _widget=None):
        self._set_status(_("Loading schedules…"))
        if not self._send("server.macro_scheduler.schedules", {}, self._on_schedules_loaded):
            self._render_placeholder(_("Moonraker connection unavailable"))
            self._set_status(_("Not connected"))

    def _on_schedules_loaded(self, result, _method, _params):
        if "error" in result:
            message = result["error"].get("message", _("Unable to load schedules"))
            logging.error("Failed to load schedules: %s", message)
            self._render_placeholder(_("Unable to load schedules"))
            self._set_status(message)
            return
        schedules = result.get("result", {}).get("schedules", [])
        self._render_schedule_rows(schedules)
        self._set_status(_("%d schedule(s) loaded") % len(schedules))

    def _on_action_done(self, result, _method, _params):
        if "error" in result:
            self._screen.show_popup_message(result["error"].get("message", _("Request failed")), level=2)
        self.refresh_schedules()

    def _toggle_schedule(self, _widget, schedule_id: int):
        if not self._send("server.macro_scheduler.toggle", {"id": schedule_id}, self._on_action_done):
            self._screen.show_popup_message(_("Moonraker connection unavailable"), level=2)

    def _confirm_delete(self, _widget, schedule_id: int, name: str):
        buttons = [
            {"name": _("Delete"), "response": Gtk.ResponseType.OK, "style": "dialog-error"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-info"},
        ]
        label = Gtk.Label(
            label=_("Delete schedule \"%s\"?") % name,
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
        )
        self._gtk.Dialog(_("Delete Schedule"), buttons, label, self._on_delete_response, schedule_id)

    def _on_delete_response(self, dialog, response, schedule_id: int):
        self._gtk.remove_dialog(dialog)
        if response != Gtk.ResponseType.OK:
            return
        if not self._send("server.macro_scheduler.delete", {"id": schedule_id}, self._on_action_done):
            self._screen.show_popup_message(_("Moonraker connection unavailable"), level=2)

    def _open_creator(self, _widget=None):
        self._screen.show_panel("macro_scheduler_editor", title=_("New Schedule"), panel_name="macro_scheduler_editor")


__all__ = ["Panel"]
