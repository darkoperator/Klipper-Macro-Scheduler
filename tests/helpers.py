"""Test doubles for the Moonraker APIs the scheduler uses.

Only the boundary is faked: the database, Klippy and the server object. The
database round-trips through JSON so tests can't pass by sharing live objects
with the code under test.
"""
import importlib.util
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tests trigger failures on purpose; keep their tracebacks out of the output.
logging.disable(logging.CRITICAL)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ms = load_module("macro_scheduler", ROOT / "macro_scheduler.py")


class FakeServerError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


class FakeDatabase:
    def __init__(self):
        self.items = {}
        self.fail_inserts = False
        self.fail_gets = False

    async def get_item(self, namespace, key, default=None):
        if self.fail_gets:
            raise RuntimeError("database read failed")
        raw = self.items.get((namespace, key))
        return default if raw is None else json.loads(raw)

    async def insert_item(self, namespace, key, value):
        if self.fail_inserts:
            raise RuntimeError("database write failed")
        self.items[(namespace, key)] = json.dumps(value)

    def stored(self):
        return json.loads(self.items[("macro_scheduler", "schedules")])

    def seed(self, schedules, next_id=None, version=None):
        blob = {
            "schedules": {str(s["id"]): s for s in schedules},
            "next_id": next_id or (max(s["id"] for s in schedules) + 1),
        }
        if version is not None:
            blob["version"] = version
        self.items[("macro_scheduler", "schedules")] = json.dumps(blob)


class FakeKlippy:
    def __init__(self):
        self.gcode = []
        self.print_state = "standby"
        self.ready = True
        self.run_error = None

    async def query_objects(self, objects):
        if not self.ready:
            raise FakeServerError("Klippy Host not connected", 503)
        return {"print_stats": {"state": self.print_state}}

    async def run_gcode(self, script):
        self.gcode.append(script)
        if self.run_error is not None:
            raise self.run_error
        return "ok"


class FakeServer:
    error = FakeServerError

    def __init__(self, klippy, database):
        self.klippy = klippy
        self.database = database
        self.endpoints = {}
        self.event_handlers = {}
        self.notifications = {}
        self.events = []

    def register_endpoint(self, uri, methods, callback, **kwargs):
        self.endpoints[uri] = callback

    def register_event_handler(self, event, callback):
        self.event_handlers[event] = callback

    def register_notification(self, event, notify_name=None):
        self.notifications[event] = notify_name

    def send_event(self, event, *args):
        self.events.append((event, args))

    def lookup_component(self, name):
        return {"klippy_apis": self.klippy, "database": self.database}[name]


class FakeConfig:
    def __init__(self, server):
        self.server = server

    def get_server(self):
        return self.server

    def get_name(self):
        return "macro_scheduler"


_MISSING = object()


class FakeRequest:
    def __init__(self, **args):
        self.args = args

    def get(self, key, default=_MISSING):
        if key in self.args:
            return self.args[key]
        if default is _MISSING:
            raise FakeServerError(f"No data for argument: {key}")
        return default

    def get_str(self, key, default=_MISSING):
        return self.get(key, default)

    def get_int(self, key, default=_MISSING):
        value = self.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            raise FakeServerError(f"Invalid int: {key}")
