# macro_scheduler_editor.py
# KlipperScreen panel for the Klipper Macro Scheduler
#
# Copyright (C) 2025 Carlos Perez <carlos_perez@darkoperator.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from ks_includes.screen_panel import ScreenPanel


def default_once_datetime(now: datetime) -> datetime:
    """Return the start of the next hour, so the default is never in the past."""
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


class Panel(ScreenPanel):
    """Panel for creating Macro Scheduler entries (except cron schedules)."""

    SUPPORTED_TYPES = ("once", "daily", "weekly", "interval")
    WEEKDAY_LABELS = [
        _("Mon"),
        _("Tue"),
        _("Wed"),
        _("Thu"),
        _("Fri"),
        _("Sat"),
        _("Sun"),
    ]

    def __init__(self, screen, title):
        title = title or _("New Schedule")
        super().__init__(screen, title)
        self._screen.remove_keyboard()

        self._type_combo: Optional[Gtk.ComboBoxText] = None
        self._name_entry: Optional[Gtk.Entry] = None
        self._macro_combo: Optional[Gtk.ComboBox] = None
        self._params_entry: Optional[Gtk.Entry] = None
        self._stack: Optional[Gtk.Stack] = None
        self._days_buttons: Dict[int, Gtk.ToggleButton] = {}
        self._once_date_button: Optional[Gtk.Button] = None
        self._once_date_value: date = default_once_datetime(datetime.now()).date()
        self._once_time_controls: Dict[str, Any] = {}
        self._daily_time_controls: Dict[str, Any] = {}
        self._weekly_time_controls: Dict[str, Any] = {}
        self._interval_spin: Optional[Gtk.SpinButton] = None
        self._missed_switch: Optional[Gtk.Switch] = None
        self._printing_switch: Optional[Gtk.Switch] = None
        self._combo_drop_times: Dict[int, datetime] = {}

        for child in self.content.get_children():
            self.content.remove(child)

        self._build_form()

    def activate(self):
        # KlipperScreen caches panels, so clear the form each time it is shown.
        self._reset_form()

    # ------------------------------------------------------------------ layout
    def _build_form(self):
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        wrapper.set_hexpand(True)
        wrapper.set_vexpand(True)

        form = Gtk.Grid(row_spacing=10, column_spacing=12)
        form.set_row_homogeneous(False)
        form.set_hexpand(True)
        form.set_vexpand(False)

        row = 0
        self._name_entry = self._add_labeled_entry(
            form,
            row,
            _("Name"),
            placeholder=_("Lights at sunset"),
        )
        row += 1

        self._macro_combo = self._add_macro_combo(form, row)
        row += 1

        self._params_entry = self._add_labeled_entry(
            form,
            row,
            _("Parameters"),
            tooltip=_("Optional key=value pairs separated by spaces, e.g. color=Green brightness=80"),
        )
        row += 1

        self._type_combo = self._add_type_selector(form, row)
        row += 1

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)

        self._stack.add_named(self._build_once_page(), "once")
        self._stack.add_named(self._build_daily_page(), "daily")
        self._stack.add_named(self._build_weekly_page(), "weekly")
        self._stack.add_named(self._build_interval_page(), "interval")
        self._stack.set_visible_child_name("once")

        self._hook_keyboard_entries()

        form.attach(self._stack, 0, row, 2, 1)
        row += 1

        self._missed_switch = self._add_switch(form, row, _("Run if missed"), False)
        row += 1
        self._printing_switch = self._add_switch(form, row, _("Skip while printing"), True)

        scroller = self._gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(form)

        wrapper.pack_start(scroller, True, True, 0)
        wrapper.pack_end(self._build_footer(), False, False, 0)

        # Ensure the content box is empty and sized like other panels
        for child in self.content.get_children():
            self.content.remove(child)
        self.content.set_hexpand(True)
        self.content.set_vexpand(True)
        self.content.pack_start(wrapper, True, True, 0)

    def _hook_keyboard_entries(self):
        fields = [
            self._name_entry,
            self._params_entry,
        ]
        for field in fields:
            if isinstance(field, Gtk.Entry):
                field.connect("touch-event", self._show_keyboard_delayed)
                field.connect("button-press-event", self._show_keyboard_delayed)
                field.connect("focus-out-event", self._screen.remove_keyboard)

    def _reset_form(self):
        if isinstance(self._name_entry, Gtk.Entry):
            self._name_entry.set_text("")
        if isinstance(self._params_entry, Gtk.Entry):
            self._params_entry.set_text("")

        entry = self._macro_combo.get_child() if self._macro_combo else None
        if isinstance(entry, Gtk.Entry):
            entry.set_text("")

        if isinstance(self._type_combo, Gtk.ComboBoxText):
            self._type_combo.set_active_id("once")

        once_default = default_once_datetime(datetime.now())
        self._once_date_value = once_default.date()
        if self._once_date_button:
            self._once_date_button.set_label(self._once_date_value.isoformat())
        if self._once_time_controls:
            self._set_time(self._once_time_controls, once_default.hour, once_default.minute)

        for controls in (self._daily_time_controls, self._weekly_time_controls):
            if controls:
                self._set_time(controls, 12, 0)

        for btn in self._days_buttons.values():
            btn.set_active(False)
            self._apply_toggle_style(btn)

        if isinstance(self._interval_spin, Gtk.SpinButton):
            self._interval_spin.set_value(60)

        if self._missed_switch:
            self._missed_switch.set_active(False)
        if self._printing_switch:
            self._printing_switch.set_active(True)

    @staticmethod
    def _apply_toggle_style(button: Gtk.ToggleButton):
        ctx = button.get_style_context()
        if button.get_active():
            ctx.add_class("button_active")
        else:
            ctx.remove_class("button_active")

    def _on_day_toggled(self, button: Gtk.ToggleButton):
        self._apply_toggle_style(button)

    def _on_period_toggled(self, button: Gtk.ToggleButton, counterpart: Gtk.ToggleButton):
        self._apply_toggle_style(button)
        if button.get_active():
            if counterpart.get_active():
                counterpart.set_active(False)
        else:
            if not counterpart.get_active():
                counterpart.set_active(True)

    def _add_labeled_entry(
        self,
        grid: Gtk.Grid,
        row: int,
        label: str,
        *,
        placeholder: Optional[str] = None,
        tooltip: Optional[str] = None,
    ) -> Gtk.Entry:
        lbl = Gtk.Label(label=f"{label}:")
        lbl.set_xalign(0.0)
        lbl.set_yalign(0.5)
        lbl.set_hexpand(False)
        grid.attach(lbl, 0, row, 1, 1)

        entry = Gtk.Entry()
        entry.set_hexpand(True)
        if placeholder:
            entry.set_placeholder_text(placeholder)
        if tooltip:
            entry.set_tooltip_text(tooltip)
        grid.attach(entry, 1, row, 1, 1)
        return entry

    def _add_switch(self, grid: Gtk.Grid, row: int, label: str, active: bool) -> Gtk.Switch:
        lbl = Gtk.Label(label=f"{label}:")
        lbl.set_xalign(0.0)
        lbl.set_yalign(0.5)
        grid.attach(lbl, 0, row, 1, 1)

        switch = Gtk.Switch()
        switch.set_active(active)
        switch.set_halign(Gtk.Align.START)
        switch.set_valign(Gtk.Align.CENTER)
        grid.attach(switch, 1, row, 1, 1)
        return switch

    def _add_macro_combo(self, grid: Gtk.Grid, row: int) -> Gtk.ComboBox:
        lbl = Gtk.Label(label=_("Macro:"))
        lbl.set_xalign(0.0)
        lbl.set_yalign(0.5)
        grid.attach(lbl, 0, row, 1, 1)

        store = Gtk.ListStore(str)
        macros = sorted(self._printer.get_gcode_macros() or [])
        for macro in macros:
            store.append([macro])

        combo = Gtk.ComboBox.new_with_model_and_entry(store)
        combo.set_hexpand(True)
        combo.set_entry_text_column(0)
        combo.set_tooltip_text(_("Choose a Klipper macro or type its name"))
        combo.connect("notify::popup-shown", self._on_combo_popup_toggle)
        entry = combo.get_child()
        if isinstance(entry, Gtk.Entry):
            entry.set_placeholder_text(_("Green"))
            entry.connect("touch-event", self._show_keyboard_delayed)
            entry.connect("button-press-event", self._show_keyboard_delayed)
            entry.connect("focus-out-event", self._screen.remove_keyboard)
        grid.attach(combo, 1, row, 1, 1)
        return combo

    def _add_type_selector(self, grid: Gtk.Grid, row: int) -> Gtk.ComboBoxText:
        lbl = Gtk.Label(label=_("Type:"))
        lbl.set_xalign(0.0)
        grid.attach(lbl, 0, row, 1, 1)

        combo = Gtk.ComboBoxText()
        combo.set_hexpand(True)
        for schedule_type in self.SUPPORTED_TYPES:
            combo.append(schedule_type, schedule_type.title())
        combo.set_active_id("once")
        combo.connect("notify::popup-shown", self._on_combo_popup_toggle)
        combo.connect("changed", self._on_type_changed)
        grid.attach(combo, 1, row, 1, 1)
        return combo

    def _build_once_page(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        date_button = self._gtk.Button("clock", self._once_date_value.isoformat(), "color1", self.bts * 0.7, Gtk.PositionType.LEFT, 1)
        date_button.get_style_context().add_class("buttons_slim")
        date_button.set_hexpand(False)
        date_button.connect("clicked", self._open_date_picker)
        self._once_date_button = date_button
        box.pack_start(self._wrap_with_label(_("Date"), date_button), False, False, 0)

        time_box, controls = self._build_time_selector()
        self._once_time_controls = controls
        box.pack_start(self._wrap_with_label(_("Time"), time_box), False, False, 0)

        return box

    def _build_daily_page(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        time_box, controls = self._build_time_selector()
        self._daily_time_controls = controls
        box.pack_start(self._wrap_with_label(_("Time"), time_box), False, False, 0)
        return box

    def _build_weekly_page(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        time_box, controls = self._build_time_selector()
        self._weekly_time_controls = controls
        box.pack_start(self._wrap_with_label(_("Time"), time_box), False, False, 0)

        days_grid = Gtk.Grid(row_spacing=4, column_spacing=4)
        for idx, label in enumerate(self.WEEKDAY_LABELS):
            btn = Gtk.ToggleButton(label=label)
            btn.get_style_context().add_class("buttons_slim")
            btn.set_hexpand(True)
            btn.set_active(False)
            btn.connect("toggled", self._on_day_toggled)
            self._apply_toggle_style(btn)
            self._days_buttons[idx] = btn
            days_grid.attach(btn, idx % 4, idx // 4, 1, 1)

        box.pack_start(self._wrap_with_label(_("Days"), days_grid), False, False, 0)
        return box

    def _build_interval_page(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        adjustment = Gtk.Adjustment(60, 1, 10080, 5, 30, 0)
        spin = Gtk.SpinButton(adjustment=adjustment, climb_rate=5, digits=0)
        spin.set_hexpand(False)
        spin.set_value(60)
        box.pack_start(self._wrap_with_label(_("Interval (minutes)"), spin), False, False, 0)
        self._interval_spin = spin
        return box

    def _wrap_with_label(self, text: str, widget: Gtk.Widget) -> Gtk.Box:
        lbl = Gtk.Label(label=f"{text}:")
        lbl.set_xalign(0.0)
        lbl.set_yalign(0.5)
        lbl.set_hexpand(False)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(lbl, False, False, 0)
        row.pack_start(widget, True, True, 0)
        return row

    def _build_footer(self) -> Gtk.Box:
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.set_margin_top(6)

        target_height = int(self._gtk.font_size * 1.1)
        cancel_btn = self._gtk.Button("back", _("Cancel"), "color2", self.bts * 0.35, Gtk.PositionType.LEFT, 1)
        cancel_btn.get_style_context().add_class("buttons_slim")
        cancel_btn.set_size_request(-1, target_height)
        cancel_btn.set_vexpand(False)
        cancel_btn.connect("clicked", self._go_back)
        footer.pack_start(cancel_btn, False, False, 0)

        create_btn = self._gtk.Button("resume", _("Create"), "color3", self.bts * 0.35, Gtk.PositionType.LEFT, 1)
        create_btn.get_style_context().add_class("buttons_slim")
        create_btn.set_size_request(-1, target_height)
        create_btn.set_vexpand(False)
        create_btn.connect("clicked", self._create_schedule)
        footer.pack_end(create_btn, False, False, 0)

        return footer

    # ----------------------------------------------------------------- events
    def _on_combo_popup_toggle(self, combo: Gtk.ComboBox, _param):
        key = id(combo)
        if combo.get_property("popup-shown"):
            self._combo_drop_times[key] = datetime.now()
            return

        last = self._combo_drop_times.get(key)
        if last and (datetime.now() - last).total_seconds() < 0.2:
            GLib.timeout_add(50, combo.popup)

    def _show_keyboard_delayed(self, widget, event):
        def _cb():
            self._screen.show_keyboard(widget, event)
            return False

        GLib.timeout_add(50, _cb)
        return False

    def _on_type_changed(self, combo: Gtk.ComboBoxText):
        selected = combo.get_active_id() or combo.get_active_text()
        if selected in self.SUPPORTED_TYPES:
            self._stack.set_visible_child_name(selected or "once")

    def _go_back(self, _widget=None):
        self._screen._menu_go_back()

    def _create_schedule(self, _widget):
        payload = self._collect_payload()
        if not payload:
            return
        websocket = getattr(self._screen, "_ws", None)
        if websocket is None or not websocket.send_method("server.macro_scheduler.add", payload, self._on_created):
            self._screen.show_popup_message(_("Moonraker connection unavailable"), level=2)

    def _on_created(self, result, _method, _params):
        if "error" in result:
            message = result["error"].get("message", _("Failed to create schedule"))
            logging.error("Scheduler creation failed: %s", message)
            self._screen.show_popup_message(message, level=2)
            return
        self._screen.show_popup_message(_("Schedule created"), level=1)
        self._go_back()

    # -------------------------------------------------------------- validation
    def _collect_payload(self) -> Optional[Dict]:
        name = self._name_entry.get_text().strip() if self._name_entry else ""
        macro = self._get_macro_text()
        schedule_type = (
            self._type_combo.get_active_id() or self._type_combo.get_active_text()
            if self._type_combo
            else "once"
        )
        params_text = self._params_entry.get_text().strip() if self._params_entry else ""

        if not name:
            self._screen.show_popup_message(_("Name is required"), level=2)
            return None
        if not macro:
            self._screen.show_popup_message(_("Macro is required"), level=2)
            return None
        if schedule_type not in self.SUPPORTED_TYPES:
            self._screen.show_popup_message(_("Unsupported schedule type"), level=2)
            return None

        try:
            params = self._parse_params(params_text)
        except ValueError as exc:
            self._screen.show_popup_message(str(exc), level=2)
            return None

        payload: Dict[str, object] = {
            "name": name,
            "macro": macro,
            "schedule_type": schedule_type,
            "params": params,
        }
        payload.update(self._collect_policy_fields())

        try:
            if schedule_type == "once":
                payload.update(self._collect_once_fields())
            elif schedule_type == "daily":
                payload.update(self._collect_daily_fields())
            elif schedule_type == "weekly":
                payload.update(self._collect_weekly_fields())
            elif schedule_type == "interval":
                payload.update(self._collect_interval_fields())
        except ValueError as exc:
            self._screen.show_popup_message(str(exc), level=2)
            return None

        return payload

    def _collect_policy_fields(self) -> Dict[str, object]:
        return {
            "missed_run_policy": "run" if self._missed_switch.get_active() else "skip",
            "skip_if_printing": self._printing_switch.get_active(),
        }

    def _get_macro_text(self) -> str:
        if not self._macro_combo:
            return ""
        entry = self._macro_combo.get_child()
        if isinstance(entry, Gtk.Entry):
            return entry.get_text().strip()
        return ""

    def _parse_params(self, text: str) -> Dict[str, str]:
        params: Dict[str, str] = {}
        if not text:
            return params
        parts = text.split()
        for part in parts:
            if "=" not in part:
                raise ValueError(_("Invalid parameter format: %s") % part)
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                raise ValueError(_("Parameter name missing"))
            params[key] = value
        return params

    def _collect_once_fields(self) -> Dict[str, str]:
        if not self._once_date_button or not self._once_time_controls:
            raise ValueError(_("Incomplete schedule configuration"))
        time_value = self._get_time_value(self._once_time_controls)
        combined = datetime.combine(self._once_date_value, datetime.strptime(time_value, "%H:%M").time())
        if combined <= datetime.now():
            raise ValueError(_("Date and time must be in the future"))
        return {"datetime": combined.isoformat()}

    def _collect_daily_fields(self) -> Dict[str, str]:
        if not self._daily_time_controls:
            raise ValueError(_("Time selection missing"))
        return {"time": self._get_time_value(self._daily_time_controls)}

    def _collect_weekly_fields(self) -> Dict[str, object]:
        if not self._weekly_time_controls:
            raise ValueError(_("Time selection missing"))
        time = self._get_time_value(self._weekly_time_controls)
        days = [idx for idx, btn in self._days_buttons.items() if btn.get_active()]
        if not days:
            raise ValueError(_("Select at least one weekday"))
        return {"time": time, "days": days}

    def _collect_interval_fields(self) -> Dict[str, int]:
        minutes = int(self._interval_spin.get_value()) if self._interval_spin else 0
        if minutes <= 0:
            raise ValueError(_("Interval must be greater than zero"))
        return {"interval_minutes": minutes}

    def _use_24h(self) -> bool:
        return self._config.get_main_config().getboolean("24htime", True)

    @staticmethod
    def _on_time_spin_output(spin: Gtk.SpinButton) -> bool:
        spin.set_text(f"{spin.get_value_as_int():02d}")
        return True

    def _build_time_spin(self, lower: int, upper: int) -> Gtk.SpinButton:
        adjustment = Gtk.Adjustment(lower, lower, upper, 1, 5, 0)
        spin = Gtk.SpinButton(adjustment=adjustment, climb_rate=1, digits=0)
        spin.set_wrap(True)
        spin.set_numeric(True)
        # The on-screen keyboard isn't hooked up here; the +/- buttons set the value.
        spin.set_editable(False)
        spin.connect("output", self._on_time_spin_output)
        return spin

    def _build_time_selector(self) -> (Gtk.Box, Dict[str, Any]):
        use_24h = self._use_24h()
        hour_spin = self._build_time_spin(0, 23) if use_24h else self._build_time_spin(1, 12)
        minute_spin = self._build_time_spin(0, 59)

        container = Gtk.Box(spacing=6)
        container.pack_start(hour_spin, False, False, 0)
        container.pack_start(Gtk.Label(label=":"), False, False, 0)
        container.pack_start(minute_spin, False, False, 0)

        controls = {"hour": hour_spin, "minute": minute_spin, "am": None, "pm": None}
        if not use_24h:
            am_button = Gtk.ToggleButton(label="AM")
            pm_button = Gtk.ToggleButton(label="PM")
            for btn in (am_button, pm_button):
                btn.get_style_context().add_class("buttons_slim")
                btn.set_hexpand(False)
                btn.set_size_request(-1, int(self._gtk.font_size * 1.1))
                container.pack_start(btn, False, False, 0)
            am_button.connect("toggled", self._on_period_toggled, pm_button)
            pm_button.connect("toggled", self._on_period_toggled, am_button)
            controls["am"] = am_button
            controls["pm"] = pm_button

        self._set_time(controls, 12, 0)
        return container, controls

    def _set_time(self, controls: Dict[str, Any], hour: int, minute: int) -> None:
        """Show a 24-hour time in the controls, whichever format they use."""
        controls["minute"].set_value(minute)
        if controls["am"] is None:
            controls["hour"].set_value(hour)
            return
        controls["hour"].set_value(hour % 12 or 12)
        controls["am"].set_active(hour < 12)
        controls["pm"].set_active(hour >= 12)
        self._apply_toggle_style(controls["am"])
        self._apply_toggle_style(controls["pm"])

    def _get_time_value(self, controls: Dict[str, Any]) -> str:
        hour = controls["hour"].get_value_as_int()
        minute = controls["minute"].get_value_as_int()
        if controls["am"] is not None:
            hour = hour % 12
            if controls["pm"].get_active():
                hour += 12
        return f"{hour:02d}:{minute:02d}"

    def _open_date_picker(self, _widget):
        calendar = Gtk.Calendar()
        calendar.select_month(self._once_date_value.month - 1, self._once_date_value.year)
        calendar.select_day(self._once_date_value.day)
        buttons = [
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL, "style": "dialog-error"},
            {"name": _("Select"), "response": Gtk.ResponseType.OK, "style": "dialog-info"},
        ]
        self._gtk.Dialog(_("Select Date"), buttons, calendar, self._on_date_dialog_response, calendar)

    def _on_date_dialog_response(self, dialog, response, calendar: Gtk.Calendar):
        if response == Gtk.ResponseType.OK:
            year, month, day = calendar.get_date()
            self._once_date_value = date(year, month + 1, day)
            if self._once_date_button:
                self._once_date_button.set_label(self._once_date_value.isoformat())
        self._gtk.remove_dialog(dialog)


__all__ = ["Panel"]
