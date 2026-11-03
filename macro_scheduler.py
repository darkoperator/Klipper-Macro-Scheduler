# macro_scheduler.py
# Moonraker component for scheduling Klipper macros
#
# Copyright (C) 2025 Carlos Perez <carlos_perez@darkoperator.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

VERSION = "0.2.0"

# Longest the scheduler goes without re-reading the wall clock. A Pi has no
# real-time clock, so the time can jump when NTP syncs after boot; a long sleep
# wouldn't notice that.
TICK_SECONDS = 30
# A run this late still counts as on time. Anything later is a missed run.
MISSED_GRACE_SECONDS = 120
DATA_VERSION = 2
DB_NAMESPACE = "macro_scheduler"
DB_KEY = "schedules"
EXECUTED_EVENT = "macro_scheduler:executed"

SCHEDULE_TYPES = ("once", "daily", "weekly", "interval", "cron")
MISSED_RUN_POLICIES = ("skip", "run")
ACTIVE_PRINT_STATES = ("printing", "paused")
# Every field a client may send when creating a schedule.
REQUEST_FIELDS = (
    "name", "macro", "schedule_type", "params", "datetime", "time", "days",
    "interval_minutes", "cron_expression", "missed_run_policy",
    "skip_if_printing",
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_CRON_PART_RE = re.compile(r"^(\*|\d+(?:-\d+)?)(?:/(\d+))?$")
# Eight years is the longest gap between 29 Feb dates, plus a margin.
_CRON_SEARCH_DAYS = 366 * 9


class CronSchedule:
    """A parsed five-field cron expression, using standard cron rules."""

    def __init__(
        self,
        minutes: Set[int],
        hours: Set[int],
        days: Set[int],
        months: Set[int],
        weekdays: Set[int],
        day_restricted: bool,
        weekday_restricted: bool,
    ) -> None:
        self.minutes = sorted(minutes)
        self.hours = sorted(hours)
        self.days = days
        self.months = months
        self.weekdays = weekdays
        self.day_restricted = day_restricted
        self.weekday_restricted = weekday_restricted

    def _matches_date(self, candidate: date) -> bool:
        if candidate.month not in self.months:
            return False
        day_match = candidate.day in self.days
        # Python counts from Monday=0, cron from Sunday=0.
        weekday_match = (candidate.weekday() + 1) % 7 in self.weekdays
        if self.day_restricted and self.weekday_restricted:
            return day_match or weekday_match
        return day_match and weekday_match

    def next_after(self, after: datetime) -> Optional[datetime]:
        """Return the first matching minute after `after`, or None if none."""
        for offset in range(_CRON_SEARCH_DAYS):
            day = after.date() + timedelta(days=offset)
            if not self._matches_date(day):
                continue
            for hour in self.hours:
                for minute in self.minutes:
                    candidate = datetime(day.year, day.month, day.day, hour, minute)
                    if candidate > after:
                        return candidate
        return None


def _parse_cron_field(field: str, low: int, high: int, name: str) -> Set[int]:
    values: Set[int] = set()
    for part in field.split(","):
        match = _CRON_PART_RE.match(part)
        if match is None:
            raise ValueError(f"Invalid cron {name} field: '{field}'")
        base, step_text = match.groups()
        step = int(step_text) if step_text is not None else 1
        if step < 1:
            raise ValueError(f"Invalid cron {name} step: '{part}'")
        if base == "*":
            start, end = low, high
        elif "-" in base:
            start, end = (int(v) for v in base.split("-"))
            if start > end:
                raise ValueError(f"Invalid cron {name} range: '{part}'")
        else:
            if step_text is not None:
                raise ValueError(f"Invalid cron {name} step: '{part}'")
            start = end = int(base)
        if start < low or end > high:
            raise ValueError(
                f"Cron {name} value out of range {low}-{high}: '{part}'"
            )
        values.update(range(start, end + 1, step))
    return values


def parse_cron(expression: str) -> CronSchedule:
    """Parse `minute hour day month weekday`, raising ValueError if invalid.

    Each field accepts `*`, numbers, `a-b` ranges, `,` lists and `/n` steps on
    `*` or a range. Weekday 0 and 7 both mean Sunday.
    """
    parts = str(expression).split()
    if len(parts) != 5:
        raise ValueError(
            "Cron expression must have 5 fields: minute hour day month weekday"
        )
    minute, hour, day, month, weekday = parts
    weekdays = _parse_cron_field(weekday, 0, 7, "weekday")
    schedule = CronSchedule(
        _parse_cron_field(minute, 0, 59, "minute"),
        _parse_cron_field(hour, 0, 23, "hour"),
        _parse_cron_field(day, 1, 31, "day"),
        _parse_cron_field(month, 1, 12, "month"),
        {d % 7 for d in weekdays},
        not day.startswith("*"),
        not weekday.startswith("*"),
    )
    if schedule.next_after(datetime(2024, 1, 1)) is None:
        raise ValueError(f"Cron expression never runs: '{expression}'")
    return schedule


def _validate_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Schedule name is required")
    if _CONTROL_CHARS_RE.search(value):
        raise ValueError("Schedule name contains invalid characters")
    return value.strip()


def _validate_macro(value: Any) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.match(value):
        raise ValueError(
            "Macro must be a single command name, such as PREHEAT_BED. "
            "Pass arguments as parameters."
        )
    return value


def _validate_params(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Parameters must be an object of NAME: value pairs")
    for key, item in value.items():
        if not _IDENTIFIER_RE.match(str(key)):
            raise ValueError(f"Invalid parameter name: '{key}'")
        if not isinstance(item, (str, int, float)):
            raise ValueError(f"Parameter '{key}' must be text or a number")
        text = str(item)
        if _CONTROL_CHARS_RE.search(text) or ";" in text or '"' in text:
            raise ValueError(f"Parameter '{key}' contains invalid characters")
    return value


def _validate_time(value: Any) -> str:
    match = _TIME_RE.match(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError("Time must be in HH:MM format")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("Time must be in HH:MM format")
    return f"{hour:02d}:{minute:02d}"


def _validate_days(value: Any) -> List[int]:
    if not isinstance(value, list) or not value:
        raise ValueError("Weekly schedules need at least one day (0=Monday, 6=Sunday)")
    for day in value:
        if isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 6:
            raise ValueError("Days must be numbers from 0 (Monday) to 6 (Sunday)")
    return sorted(set(value))


def _validate_interval(value: Any) -> int:
    minutes: Optional[int] = None
    if isinstance(value, int) and not isinstance(value, bool):
        minutes = value
    elif isinstance(value, str) and value.strip().isdigit():
        minutes = int(value)
    if minutes is None or minutes < 1:
        raise ValueError("Interval must be a whole number of minutes, at least 1")
    return minutes


def _validate_once_datetime(value: Any, now: datetime, allow_past: bool) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid date and time: '{value}'")
    if parsed.tzinfo is not None:
        raise ValueError(
            "Date and time must be in the printer's local time, with no timezone"
        )
    if not allow_past and parsed <= now:
        raise ValueError("Date and time must be in the future")
    return parsed.isoformat()


def _validate_skip_if_printing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "false"):
        return text == "true"
    raise ValueError("skip_if_printing must be true or false")


def validate_schedule(
    fields: Dict[str, Any], now: datetime, allow_past: bool = False
) -> Dict[str, Any]:
    """Return the normalized settings for a schedule, or raise ValueError.

    `allow_past` is for schedules loaded from storage, where a "once" schedule
    may legitimately have already run.
    """
    schedule_type = fields.get("schedule_type") or "once"
    if schedule_type not in SCHEDULE_TYPES:
        raise ValueError(f"Invalid schedule type: '{schedule_type}'")
    policy = fields.get("missed_run_policy") or "skip"
    if policy not in MISSED_RUN_POLICIES:
        raise ValueError(f"Invalid missed run policy: '{policy}'")
    result: Dict[str, Any] = {
        "name": _validate_name(fields.get("name")),
        "macro": _validate_macro(fields.get("macro")),
        "schedule_type": schedule_type,
        "params": _validate_params(fields.get("params")),
        "missed_run_policy": policy,
        "skip_if_printing": _validate_skip_if_printing(fields.get("skip_if_printing")),
    }
    if schedule_type == "once":
        result["datetime"] = _validate_once_datetime(
            fields.get("datetime"), now, allow_past
        )
    elif schedule_type == "daily":
        result["time"] = _validate_time(fields.get("time"))
    elif schedule_type == "weekly":
        result["time"] = _validate_time(fields.get("time"))
        result["days"] = _validate_days(fields.get("days"))
    elif schedule_type == "interval":
        result["interval_minutes"] = _validate_interval(fields.get("interval_minutes"))
    elif schedule_type == "cron":
        parse_cron(fields.get("cron_expression"))
        result["cron_expression"] = fields["cron_expression"]
    return result


def build_gcode(macro: str, params: Dict[str, Any]) -> str:
    """Build the command line for a macro from already-validated parts."""
    parts = [macro]
    for key, value in params.items():
        text = str(value)
        if not text or re.search(r"\s", text):
            text = f'"{text}"'
        parts.append(f"{key}={text}")
    return " ".join(parts)


def _next_daily(time_str: str, now: datetime) -> datetime:
    hour, minute = (int(v) for v in time_str.split(":"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _next_weekly(time_str: str, days: List[int], now: datetime) -> datetime:
    hour, minute = (int(v) for v in time_str.split(":"))
    candidates = []
    for weekday in days:
        offset = (weekday - now.weekday()) % 7
        candidate = (now + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= now:
            candidate += timedelta(days=7)
        candidates.append(candidate)
    return min(candidates)


def next_run_for(schedule: Dict[str, Any], now: datetime) -> str:
    """Return the next run time for a validated schedule as local ISO text.

    Times are naive local time. A run that falls in the hour skipped by a
    daylight saving change comes due when the clock jumps past it, and is
    handled like any other late run.
    """
    schedule_type = schedule["schedule_type"]
    if schedule_type == "once":
        return schedule["datetime"]
    if schedule_type == "daily":
        return _next_daily(schedule["time"], now).isoformat()
    if schedule_type == "weekly":
        return _next_weekly(schedule["time"], schedule["days"], now).isoformat()
    if schedule_type == "interval":
        due = now + timedelta(minutes=schedule["interval_minutes"])
        return due.replace(microsecond=0).isoformat()
    next_run = parse_cron(schedule["cron_expression"]).next_after(now)
    if next_run is None:
        raise ValueError(
            f"Cron expression never runs: '{schedule['cron_expression']}'"
        )
    return next_run.isoformat()


class MacroScheduler:
    def __init__(self, config) -> None:
        self.server = config.get_server()
        self.name = config.get_name()
        self.database = self.server.lookup_component("database")
        self.schedules: Dict[int, Dict[str, Any]] = {}
        self.next_schedule_id = 1
        self._now: Callable[[], datetime] = datetime.now
        self._loaded = False
        self._running: Dict[int, "asyncio.Task[None]"] = {}
        self._loop_task: Optional["asyncio.Task[None]"] = None
        self._wake_event: Optional[asyncio.Event] = None

        for path, method, callback in (
            ("schedules", "GET", self._handle_list_schedules),
            ("add", "POST", self._handle_add_schedule),
            ("delete", "POST", self._handle_delete_schedule),
            ("toggle", "POST", self._handle_toggle_schedule),
            ("list_text", "GET", self._handle_list_text),
        ):
            self.server.register_endpoint(
                f"/server/macro_scheduler/{path}", [method], callback
            )
        self.server.register_notification(EXECUTED_EVENT, "macro_scheduler_executed")
        self.server.register_event_handler(
            "server:klippy_ready", self._handle_klippy_ready
        )
        logging.info(f"Macro Scheduler {VERSION} Component Initialized")

    # ------------------------------------------------------------- lifecycle
    async def component_init(self) -> None:
        await self._load_schedules()
        self._loop_task = asyncio.create_task(self._run_loop())
        logging.info("Macro Scheduler is ready")

    async def on_exit(self) -> None:
        tasks = list(self._running.values())
        if self._loop_task is not None:
            tasks.append(self._loop_task)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_klippy_ready(self) -> None:
        self._wake_loop()

    def _wake_loop(self) -> None:
        if self._wake_event is not None:
            self._wake_event.set()

    # ----------------------------------------------------------- persistence
    async def _load_schedules(self) -> None:
        """Load and migrate stored schedules.

        If the read raises, `_loaded` stays False, which blocks firing and writes
        so an empty list can't overwrite the stored schedules. This only covers
        errors Moonraker raises: its get_item returns the default for errors
        inside the query, which look the same as nothing being stored yet.
        """
        try:
            data = await self.database.get_item(DB_NAMESPACE, DB_KEY, None)
        except Exception:
            logging.exception("Macro Scheduler: unable to read stored schedules")
            return
        data = data or {}
        self.schedules = {}
        for key, schedule in data.get("schedules", {}).items():
            schedule_id = int(key)
            schedule["id"] = schedule_id
            self.schedules[schedule_id] = schedule
        self.next_schedule_id = data.get("next_id", 1)
        self._loaded = True
        if self._migrate_schedules(data.get("version", 1)):
            await self._try_save()
        logging.info(f"Macro Scheduler: loaded {len(self.schedules)} schedule(s)")

    async def _ensure_loaded(self) -> None:
        if not self._loaded:
            await self._load_schedules()

    def _migrate_schedules(self, stored_version: int) -> bool:
        """Bring loaded schedules up to date. Returns True if any changed."""
        now = self._now()
        changed = stored_version < DATA_VERSION
        for schedule in self.schedules.values():
            before = dict(schedule)
            schedule.setdefault("missed_run_policy", "skip")
            schedule.setdefault("skip_if_printing", True)
            schedule.setdefault("last_run", None)
            schedule.setdefault("last_status", None)
            schedule.setdefault("last_error", None)
            schedule.setdefault("enabled", False)
            try:
                validate_schedule(schedule, now, allow_past=True)
            except ValueError as err:
                schedule["enabled"] = False
                schedule["next_run"] = None
                schedule["last_status"] = "invalid"
                schedule["last_error"] = str(err)
                logging.warning(
                    f"Macro Scheduler: disabled schedule {schedule['id']}: {err}"
                )
            else:
                if schedule["last_status"] == "running":
                    # Moonraker stopped before the macro reported a result. The
                    # next run was already saved, so it won't run twice.
                    schedule["last_status"] = "interrupted"
                    schedule["last_error"] = "Moonraker restarted during this run"
                # Older versions could store a wrong time for cron schedules.
                outdated_cron = (
                    stored_version < DATA_VERSION
                    and schedule["schedule_type"] == "cron"
                )
                if schedule["enabled"] and (outdated_cron or not schedule.get("next_run")):
                    schedule["next_run"] = next_run_for(schedule, now)
            changed = changed or schedule != before
        return changed

    async def _save_schedules(self) -> None:
        await self.database.insert_item(DB_NAMESPACE, DB_KEY, {
            "version": DATA_VERSION,
            "schedules": {str(k): v for k, v in self.schedules.items()},
            "next_id": self.next_schedule_id,
        })

    async def _try_save(self) -> None:
        """Save during a run, where a client can't be told about a failure."""
        try:
            await self._save_schedules()
        except Exception:
            logging.exception("Macro Scheduler: unable to save schedules")

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise self.server.error(
                "Stored schedules could not be read. Check moonraker.log.", 503
            )

    # ------------------------------------------------------------- endpoints
    async def _handle_list_schedules(self, web_request) -> Dict[str, Any]:
        self._require_loaded()
        return {"schedules": list(self.schedules.values())}

    async def _handle_add_schedule(self, web_request) -> Dict[str, Any]:
        self._require_loaded()
        fields = {key: web_request.get(key, None) for key in REQUEST_FIELDS}
        now = self._now()
        try:
            schedule = validate_schedule(fields, now)
            schedule["next_run"] = next_run_for(schedule, now)
        except ValueError as err:
            raise self.server.error(str(err), 400)
        schedule_id = self.next_schedule_id
        schedule.update(
            id=schedule_id, enabled=True,
            last_run=None, last_status=None, last_error=None,
        )
        self.schedules[schedule_id] = schedule
        self.next_schedule_id += 1
        try:
            await self._save_schedules()
        except Exception as err:
            del self.schedules[schedule_id]
            self.next_schedule_id = schedule_id
            raise self._save_error(err)
        self._wake_loop()
        return {"schedule": schedule}

    async def _handle_delete_schedule(self, web_request) -> Dict[str, Any]:
        self._require_loaded()
        schedule_id = web_request.get_int("id")
        schedule = self._get_schedule(schedule_id)
        del self.schedules[schedule_id]
        try:
            await self._save_schedules()
        except Exception as err:
            self.schedules[schedule_id] = schedule
            raise self._save_error(err)
        return {"deleted": schedule_id}

    async def _handle_toggle_schedule(self, web_request) -> Dict[str, Any]:
        self._require_loaded()
        schedule = self._get_schedule(web_request.get_int("id"))
        previous = dict(schedule)
        if schedule.get("enabled"):
            schedule["enabled"] = False
        else:
            self._enable(schedule)
        try:
            await self._save_schedules()
        except Exception as err:
            schedule.clear()
            schedule.update(previous)
            raise self._save_error(err)
        self._wake_loop()
        return {"schedule": schedule}

    async def _handle_list_text(self, web_request) -> Dict[str, Any]:
        self._require_loaded()
        if not self.schedules:
            return {"text": "No scheduled macros configured"}
        lines = ["=== Scheduled Macros ===", ""]
        for sid, schedule in self.schedules.items():
            status = "✓ ACTIVE" if schedule.get("enabled") else "✗ DISABLED"
            lines.append(f"[{sid}] {schedule.get('name')}")
            lines.append(f"    Macro: {schedule.get('macro')}")
            lines.append(f"    Type: {str(schedule.get('schedule_type')).upper()}")
            lines.append(f"    Status: {status}")
            if schedule.get("enabled") and schedule.get("next_run"):
                lines.append(f"    Next run: {schedule['next_run']}")
            if schedule.get("last_status"):
                result = f"    Last result: {schedule['last_status']}"
                if schedule.get("last_error"):
                    result += f" ({schedule['last_error']})"
                lines.append(result)
            lines.append("")
        active = sum(1 for s in self.schedules.values() if s.get("enabled"))
        lines.append(f"Total: {active}/{len(self.schedules)} active")
        return {"text": "\n".join(lines)}

    def _get_schedule(self, schedule_id: int) -> Dict[str, Any]:
        schedule = self.schedules.get(schedule_id)
        if schedule is None:
            raise self.server.error(f"Schedule {schedule_id} not found", 404)
        return schedule

    def _save_error(self, err: Exception):
        logging.exception("Macro Scheduler: unable to save schedules")
        return self.server.error(f"Unable to save schedules: {err}", 500)

    def _enable(self, schedule: Dict[str, Any]) -> None:
        """Enable a schedule, working out its next run from the current time."""
        now = self._now()
        try:
            validate_schedule(schedule, now, allow_past=False)
            schedule["next_run"] = next_run_for(schedule, now)
        except ValueError as err:
            raise self.server.error(f"Can't enable this schedule: {err}", 400)
        schedule["enabled"] = True
        if schedule.get("last_status") == "invalid":
            schedule["last_status"] = None
            schedule["last_error"] = None

    # ------------------------------------------------------------ scheduling
    def _seconds_until_next_check(self) -> float:
        now = self._now()
        wait: float = TICK_SECONDS
        for schedule in self.schedules.values():
            if not schedule.get("enabled") or not schedule.get("next_run"):
                continue
            try:
                due = datetime.fromisoformat(schedule["next_run"])
            except ValueError:
                continue
            wait = min(wait, (due - now).total_seconds())
        return max(wait, 1.0)

    async def _run_loop(self) -> None:
        self._wake_event = asyncio.Event()
        while True:
            try:
                await self._process_due()
            except Exception:
                logging.exception("Macro Scheduler: error checking schedules")
            try:
                await asyncio.wait_for(
                    self._wake_event.wait(), self._seconds_until_next_check()
                )
            except asyncio.TimeoutError:
                pass
            self._wake_event.clear()

    async def _process_due(self) -> None:
        await self._ensure_loaded()
        if not self._loaded:
            return
        now = self._now()
        for schedule in list(self.schedules.values()):
            if not schedule.get("enabled"):
                continue
            try:
                due = datetime.fromisoformat(schedule["next_run"])
            except (KeyError, TypeError, ValueError):
                self._finish(schedule, "invalid", "Stored next run time is invalid")
                schedule["enabled"] = False
                await self._try_save()
                continue
            if due <= now:
                await self._handle_due(schedule, due, now)

    async def _handle_due(
        self, schedule: Dict[str, Any], due: datetime, now: datetime
    ) -> None:
        schedule_id = schedule["id"]
        if schedule_id in self._running:
            logging.info(
                f"Macro Scheduler: schedule {schedule_id} is still running, "
                "skipping this run"
            )
            self._advance(schedule, now)
            await self._try_save()
            return

        catch_up = schedule.get("missed_run_policy") == "run"
        if not catch_up and (now - due).total_seconds() > MISSED_GRACE_SECONDS:
            self._finish(schedule, "missed", f"Was due at {due.isoformat()}")
        else:
            state = await self._get_print_state()
            if state is None:
                if catch_up:
                    return  # Stay due, and run once Klipper is back.
                self._finish(schedule, "failed", "Klipper was not ready")
            elif state in ACTIVE_PRINT_STATES and schedule.get("skip_if_printing", True):
                self._finish(schedule, "skipped", f"Printer was {state}")
            else:
                # Save the attempt first. If Moonraker dies during the macro it
                # is reported as interrupted rather than run a second time.
                schedule["last_run"] = now.isoformat()
                schedule["last_status"] = "running"
                schedule["last_error"] = None
                self._advance(schedule, now)
                await self._try_save()
                self._running[schedule_id] = asyncio.create_task(
                    self._dispatch(schedule)
                )
                return
        self._advance(schedule, now)
        await self._try_save()

    def _advance(self, schedule: Dict[str, Any], now: datetime) -> None:
        if schedule["schedule_type"] == "once":
            schedule["enabled"] = False
            schedule["next_run"] = None
        else:
            schedule["next_run"] = next_run_for(schedule, now)

    async def _get_print_state(self) -> Optional[str]:
        """Return the print state, or None if Klipper can't be reached."""
        klippy_apis = self.server.lookup_component("klippy_apis")
        try:
            result = await klippy_apis.query_objects({"print_stats": ["state"]})
        except Exception as err:
            logging.info(f"Macro Scheduler: Klipper not available: {err}")
            return None
        return result.get("print_stats", {}).get("state", "")

    async def _dispatch(self, schedule: Dict[str, Any]) -> None:
        schedule_id = schedule["id"]
        gcode = build_gcode(schedule["macro"], schedule.get("params") or {})
        klippy_apis = self.server.lookup_component("klippy_apis")
        logging.info(f"Macro Scheduler: running '{gcode}'")
        try:
            try:
                await klippy_apis.run_gcode(gcode)
            except Exception as err:
                logging.error(f"Macro Scheduler: '{gcode}' failed: {err}")
                self._finish(schedule, "failed", str(err))
            else:
                self._finish(schedule, "ok", None)
            await self._try_save()
        finally:
            self._running.pop(schedule_id, None)

    def _finish(
        self, schedule: Dict[str, Any], status: str, error: Optional[str]
    ) -> None:
        """Record the outcome of a run and tell any listening clients."""
        schedule["last_status"] = status
        schedule["last_error"] = error
        self.server.send_event(EXECUTED_EVENT, {
            "schedule": schedule.get("name"),
            "macro": schedule.get("macro"),
            "time": self._now().isoformat(),
            "status": status,
            "error": error,
        })


def load_component(config):
    return MacroScheduler(config)
