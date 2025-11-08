import logging
from typing import Any, Dict, List

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
                pieces.append(_("next: %s") % next_run)
        else:
            pieces.append(_("disabled"))

        params = schedule.get("params")
        if isinstance(params, dict) and params:
            formatted_params = " ".join(f"{k}={v}" for k, v in params.items())
            pieces.append(formatted_params)

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
            delete_btn.connect("clicked", self._delete_schedule, int(schedule_id))
            button_box.add(delete_btn)

            row.add(button_box)
            grid.attach(row, 0, idx, 1, 1)

        grid.show_all()

    # --------------------------------------------------------------- API calls
    def refresh_schedules(self, _widget=None):
        if not getattr(self._screen, "apiclient", None):
            self._render_placeholder(_("Moonraker connection unavailable"))
            self._set_status(_("Not connected"))
            return

        self._set_status(_("Loading schedules…"))
        response = self._screen.apiclient.send_request("server/macro_scheduler/schedules")

        if not response or "schedules" not in response:
            logging.error("Failed to load schedules: %s", response)
            self._render_placeholder(_("Unable to load schedules"))
            self._set_status(_("Load failed"))
            return

        schedules = response.get("schedules", [])
        self._render_schedule_rows(schedules)
        self._set_status(_("%d schedule(s) loaded") % len(schedules))

    def _toggle_schedule(self, _widget, schedule_id: int):
        if not getattr(self._screen, "apiclient", None):
            return

        result = self._screen.apiclient.post_request(
            "server/macro_scheduler/toggle",
            json={"id": schedule_id},
        )
        if not result:
            self._screen.show_popup_message(_("Failed to toggle schedule"), level=2)
            return
        self.refresh_schedules()

    def _delete_schedule(self, _widget, schedule_id: int):
        if not getattr(self._screen, "apiclient", None):
            return

        result = self._screen.apiclient.post_request(
            "server/macro_scheduler/delete",
            json={"id": schedule_id},
        )
        if not result:
            self._screen.show_popup_message(_("Failed to delete schedule"), level=2)
            return
        self.refresh_schedules()

    def _open_creator(self, _widget=None):
        # Remove existing editor instances so the back stack remains clean
        while "macro_scheduler_editor" in self._screen._cur_panels:
            self._screen._cur_panels.remove("macro_scheduler_editor")
        self._screen.show_panel("macro_scheduler_editor", title=_("New Schedule"), panel_name="macro_scheduler_editor")


__all__ = ["Panel"]
