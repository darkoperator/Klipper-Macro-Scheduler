import asyncio
import unittest
from datetime import datetime, timedelta

from helpers import FakeConfig, FakeDatabase, FakeKlippy, FakeRequest, FakeServer, ms

T0 = datetime(2026, 11, 2, 20, 0, 0)  # A Monday


def daily(**overrides):
    base = {
        "name": "heat", "macro": "HEAT", "schedule_type": "daily", "time": "21:00",
    }
    base.update(overrides)
    return base


class SchedulerCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.klippy = FakeKlippy()
        self.server = FakeServer(self.klippy, self.db)
        self.clock = T0
        self.s = self.make()

    def make(self):
        s = ms.MacroScheduler(FakeConfig(self.server))
        s._now = lambda: self.clock
        return s

    async def boot(self, s=None):
        s = s or self.s
        await s._load_schedules()
        return s

    async def add(self, **fields):
        result = await self.s._handle_add_schedule(FakeRequest(**fields))
        return result["schedule"]

    async def tick(self, at=None, s=None):
        s = s or self.s
        if at is not None:
            self.clock = at
        await s._process_due()
        if s._running:
            await asyncio.gather(*list(s._running.values()), return_exceptions=True)

    def listed(self, s=None):
        return list((s or self.s).schedules.values())


class Firing(SchedulerCase):
    async def test_fires_on_time_once_and_moves_to_next_day(self):
        await self.boot()
        sched = await self.add(**daily())
        await self.tick(T0 + timedelta(minutes=59))
        self.assertEqual(self.klippy.gcode, [])
        await self.tick(T0 + timedelta(hours=1, seconds=1))
        await self.tick()
        self.assertEqual(self.klippy.gcode, ["HEAT"])
        self.assertEqual(sched["next_run"], "2026-11-03T21:00:00")
        self.assertEqual(sched["last_status"], "ok")
        self.assertEqual(sched["last_run"], "2026-11-02T21:00:01")

    async def test_interval_runs_after_the_interval_not_on_creation(self):
        await self.boot()
        await self.add(name="i", macro="M", schedule_type="interval", interval_minutes=10)
        await self.tick()
        self.assertEqual(self.klippy.gcode, [])
        await self.tick(T0 + timedelta(minutes=10))
        self.assertEqual(self.klippy.gcode, ["M"])

    async def test_once_runs_a_single_time_then_disables(self):
        await self.boot()
        sched = await self.add(
            name="o", macro="M", schedule_type="once", datetime="2026-11-02T20:05:00"
        )
        await self.tick(T0 + timedelta(minutes=5))
        await self.tick(T0 + timedelta(minutes=6))
        self.assertEqual(self.klippy.gcode, ["M"])
        self.assertFalse(sched["enabled"])
        self.assertIsNone(sched["next_run"])

    async def test_disabled_schedule_does_not_fire(self):
        await self.boot()
        sched = await self.add(**daily())
        await self.s._handle_toggle_schedule(FakeRequest(id=sched["id"]))
        await self.tick(T0 + timedelta(hours=1))
        self.assertEqual(self.klippy.gcode, [])

    async def test_params_reach_gcode(self):
        await self.boot()
        await self.add(**daily(params={"TEMP": 60}))
        await self.tick(T0 + timedelta(hours=1))
        self.assertEqual(self.klippy.gcode, ["HEAT TEMP=60"])


class MissedRuns(SchedulerCase):
    async def test_overdue_run_after_downtime_is_skipped_by_default(self):
        await self.boot()
        sched = await self.add(**daily())
        restarted = self.make()
        await self.boot(restarted)
        await self.tick(T0 + timedelta(days=5), s=restarted)
        self.assertEqual(self.klippy.gcode, [])
        stored = restarted.schedules[sched["id"]]
        self.assertEqual(stored["last_status"], "missed")
        self.assertEqual(stored["next_run"], "2026-11-07T21:00:00")

    async def test_overdue_run_happens_when_policy_is_run(self):
        await self.boot()
        sched = await self.add(**daily(missed_run_policy="run"))
        await self.tick(T0 + timedelta(days=5))
        self.assertEqual(self.klippy.gcode, ["HEAT"])
        self.assertEqual(sched["last_status"], "ok")

    async def test_slightly_late_run_is_not_treated_as_missed(self):
        await self.boot()
        await self.add(**daily())
        await self.tick(T0 + timedelta(hours=1, seconds=ms.MISSED_GRACE_SECONDS))
        self.assertEqual(self.klippy.gcode, ["HEAT"])

    async def test_missed_once_is_disabled_and_reported(self):
        await self.boot()
        sched = await self.add(
            name="o", macro="M", schedule_type="once", datetime="2026-11-02T20:05:00"
        )
        await self.tick(T0 + timedelta(days=1))
        self.assertEqual(self.klippy.gcode, [])
        self.assertFalse(sched["enabled"])
        self.assertEqual(sched["last_status"], "missed")

    async def test_clock_jump_while_waiting_is_detected(self):
        # The old per-schedule sleep could not notice the wall clock moving.
        await self.boot()
        await self.add(**daily(time="20:30"))
        self.assertLessEqual(self.s._seconds_until_next_check(), ms.TICK_SECONDS)
        await self.tick(T0 + timedelta(minutes=30))
        self.assertEqual(self.klippy.gcode, ["HEAT"])


class Reenable(SchedulerCase):
    async def test_reenabling_after_time_passed_recalculates_without_firing(self):
        await self.boot()
        sched = await self.add(**daily())
        await self.s._handle_toggle_schedule(FakeRequest(id=sched["id"]))
        self.clock = T0 + timedelta(hours=5)
        await self.s._handle_toggle_schedule(FakeRequest(id=sched["id"]))
        await self.tick()
        self.assertEqual(self.klippy.gcode, [])
        self.assertEqual(sched["next_run"], "2026-11-03T21:00:00")

    async def test_completed_once_cannot_be_reenabled(self):
        await self.boot()
        sched = await self.add(
            name="o", macro="M", schedule_type="once", datetime="2026-11-02T20:05:00"
        )
        await self.tick(T0 + timedelta(minutes=5))
        with self.assertRaises(self.server.error) as ctx:
            await self.s._handle_toggle_schedule(FakeRequest(id=sched["id"]))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertFalse(sched["enabled"])
        await self.tick()
        self.assertEqual(self.klippy.gcode, ["M"])

    async def test_future_once_can_be_paused_and_resumed(self):
        await self.boot()
        sched = await self.add(
            name="o", macro="M", schedule_type="once", datetime="2026-11-03T20:05:00"
        )
        await self.s._handle_toggle_schedule(FakeRequest(id=sched["id"]))
        await self.s._handle_toggle_schedule(FakeRequest(id=sched["id"]))
        self.assertTrue(sched["enabled"])
        self.assertEqual(sched["next_run"], "2026-11-03T20:05:00")


class Printing(SchedulerCase):
    async def test_skips_while_printing_or_paused_by_default(self):
        for state in ("printing", "paused"):
            with self.subTest(state=state):
                self.setUp()
                await self.boot()
                self.klippy.print_state = state
                sched = await self.add(**daily())
                await self.tick(T0 + timedelta(hours=1))
                self.assertEqual(self.klippy.gcode, [])
                self.assertEqual(sched["last_status"], "skipped")
                self.assertIn(state, sched["last_error"])
                self.assertEqual(sched["next_run"], "2026-11-03T21:00:00")

    async def test_runs_during_print_when_opted_in(self):
        await self.boot()
        self.klippy.print_state = "printing"
        await self.add(**daily(skip_if_printing=False))
        await self.tick(T0 + timedelta(hours=1))
        self.assertEqual(self.klippy.gcode, ["HEAT"])

    async def test_runs_when_print_finished(self):
        for state in ("standby", "complete", "cancelled", "error"):
            with self.subTest(state=state):
                self.setUp()
                await self.boot()
                self.klippy.print_state = state
                await self.add(**daily())
                await self.tick(T0 + timedelta(hours=1))
                self.assertEqual(self.klippy.gcode, ["HEAT"])


class Outcomes(SchedulerCase):
    async def test_failed_macro_records_the_error(self):
        await self.boot()
        self.klippy.run_error = RuntimeError("Unknown command: HEAT")
        sched = await self.add(**daily())
        await self.tick(T0 + timedelta(hours=1))
        self.assertEqual(sched["last_status"], "failed")
        self.assertIn("Unknown command", sched["last_error"])
        self.assertEqual(self.db.stored()["schedules"]["1"]["last_status"], "failed")

    async def test_failed_recurring_advances_without_retry(self):
        await self.boot()
        self.klippy.run_error = RuntimeError("boom")
        sched = await self.add(**daily())
        await self.tick(T0 + timedelta(hours=1))
        await self.tick(T0 + timedelta(hours=1, minutes=1))
        self.assertEqual(len(self.klippy.gcode), 1)
        self.assertEqual(sched["next_run"], "2026-11-03T21:00:00")

    async def test_failed_once_stays_visible_as_failed(self):
        await self.boot()
        self.klippy.run_error = RuntimeError("boom")
        sched = await self.add(
            name="o", macro="M", schedule_type="once", datetime="2026-11-02T20:05:00"
        )
        await self.tick(T0 + timedelta(minutes=5))
        self.assertFalse(sched["enabled"])
        self.assertEqual(sched["last_status"], "failed")

    async def test_klipper_down_records_failure_and_advances(self):
        await self.boot()
        self.klippy.ready = False
        sched = await self.add(**daily())
        await self.tick(T0 + timedelta(hours=1))
        self.assertEqual(self.klippy.gcode, [])
        self.assertEqual(sched["last_status"], "failed")
        self.assertIn("Klipper", sched["last_error"])
        self.assertEqual(sched["next_run"], "2026-11-03T21:00:00")

    async def test_klipper_down_holds_the_run_when_policy_is_run(self):
        await self.boot()
        self.klippy.ready = False
        sched = await self.add(**daily(missed_run_policy="run"))
        await self.tick(T0 + timedelta(hours=1))
        self.assertEqual(sched["next_run"], "2026-11-02T21:00:00")
        self.klippy.ready = True
        await self.tick(T0 + timedelta(hours=2))
        self.assertEqual(self.klippy.gcode, ["HEAT"])
        self.assertEqual(sched["next_run"], "2026-11-03T21:00:00")

    async def test_event_reports_the_outcome(self):
        await self.boot()
        self.klippy.run_error = RuntimeError("boom")
        await self.add(**daily())
        await self.tick(T0 + timedelta(hours=1))
        name, args = self.server.events[-1]
        self.assertEqual(name, "macro_scheduler:executed")
        self.assertEqual(args[0]["status"], "failed")
        self.assertEqual(args[0]["error"], "boom")
        self.assertEqual(args[0]["schedule"], "heat")

    async def test_event_is_registered_for_websocket_clients(self):
        self.assertEqual(
            self.server.notifications["macro_scheduler:executed"],
            "macro_scheduler_executed",
        )


class Restarts(SchedulerCase):
    async def test_attempt_is_saved_before_the_macro_runs(self):
        await self.boot()
        await self.add(**daily())
        seen = []

        async def run_gcode(script):
            seen.append(self.db.stored()["schedules"]["1"])
            return "ok"

        self.klippy.run_gcode = run_gcode
        await self.tick(T0 + timedelta(hours=1))
        self.assertEqual(seen[0]["last_status"], "running")
        self.assertEqual(seen[0]["next_run"], "2026-11-03T21:00:00")

    async def test_restart_mid_macro_marks_interrupted_and_does_not_rerun(self):
        await self.boot()
        await self.add(**daily())
        release = asyncio.Event()

        async def run_gcode(script):
            self.klippy.gcode.append(script)
            await release.wait()

        self.klippy.run_gcode = run_gcode
        self.clock = T0 + timedelta(hours=1)
        await self.s._process_due()
        await asyncio.sleep(0)

        restarted = self.make()
        await self.boot(restarted)
        await self.tick(s=restarted)
        release.set()
        await asyncio.gather(*list(self.s._running.values()))
        self.assertEqual(self.klippy.gcode, ["HEAT"])
        self.assertEqual(restarted.schedules[1]["last_status"], "interrupted")

    async def test_long_macro_does_not_block_other_schedules(self):
        await self.boot()
        await self.add(**daily())
        await self.add(name="b", macro="OTHER", schedule_type="daily", time="21:00")
        release = asyncio.Event()

        async def run_gcode(script):
            self.klippy.gcode.append(script)
            if script == "HEAT":
                await release.wait()

        self.klippy.run_gcode = run_gcode
        self.clock = T0 + timedelta(hours=1)
        await asyncio.wait_for(self.s._process_due(), 1)
        await asyncio.sleep(0)
        self.assertCountEqual(self.klippy.gcode, ["HEAT", "OTHER"])
        release.set()
        await asyncio.gather(*list(self.s._running.values()))

    async def test_overlapping_run_is_not_started(self):
        await self.boot()
        sched = await self.add(name="i", macro="M", schedule_type="interval", interval_minutes=1)
        release = asyncio.Event()

        async def run_gcode(script):
            self.klippy.gcode.append(script)
            await release.wait()

        self.klippy.run_gcode = run_gcode
        self.clock = T0 + timedelta(minutes=1)
        await self.s._process_due()
        await asyncio.sleep(0)
        self.clock = T0 + timedelta(minutes=2)
        await self.s._process_due()
        await asyncio.sleep(0)
        self.assertEqual(self.klippy.gcode, ["M"])
        self.assertEqual(sched["next_run"], "2026-11-02T20:03:00")
        release.set()
        await asyncio.gather(*list(self.s._running.values()))


class Persistence(SchedulerCase):
    async def test_schedules_load_without_klipper(self):
        self.db.seed([{
            "id": 1, "name": "old", "macro": "M", "schedule_type": "daily",
            "time": "06:00", "params": {}, "enabled": True,
            "next_run": "2026-11-03T06:00:00",
        }])
        self.klippy.ready = False
        await self.boot()
        result = await self.s._handle_list_schedules(FakeRequest())
        self.assertEqual([x["name"] for x in result["schedules"]], ["old"])

    async def test_schedule_added_before_klipper_is_ready_survives_restart(self):
        self.klippy.ready = False
        await self.boot()
        await self.add(**daily())
        restarted = self.make()
        await self.boot(restarted)
        self.assertEqual([x["name"] for x in self.listed(restarted)], ["heat"])

    async def test_klippy_ready_does_not_reload_or_refire(self):
        await self.boot()
        sched = await self.add(**daily())
        self.assertNotIn("server:klippy_ready", self.server.event_handlers.get("reload", []))
        handler = self.server.event_handlers["server:klippy_ready"]
        await handler()
        self.assertIs(self.s.schedules[sched["id"]], sched)

    async def test_failed_save_on_add_reports_error_and_keeps_nothing(self):
        await self.boot()
        self.db.fail_inserts = True
        with self.assertRaises(self.server.error) as ctx:
            await self.add(**daily())
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(self.s.schedules, {})

    async def test_failed_save_on_toggle_rolls_back(self):
        await self.boot()
        sched = await self.add(**daily())
        self.db.fail_inserts = True
        with self.assertRaises(self.server.error):
            await self.s._handle_toggle_schedule(FakeRequest(id=sched["id"]))
        self.assertTrue(self.s.schedules[sched["id"]]["enabled"])

    async def test_failed_save_on_delete_rolls_back(self):
        await self.boot()
        sched = await self.add(**daily())
        self.db.fail_inserts = True
        with self.assertRaises(self.server.error):
            await self.s._handle_delete_schedule(FakeRequest(id=sched["id"]))
        self.assertIn(sched["id"], self.s.schedules)

    async def test_failed_load_blocks_writes_so_data_is_not_overwritten(self):
        self.db.seed([{
            "id": 1, "name": "old", "macro": "M", "schedule_type": "daily",
            "time": "06:00", "params": {}, "enabled": True,
            "next_run": "2026-11-03T06:00:00",
        }])
        self.db.fail_gets = True
        await self.boot()
        with self.assertRaises(self.server.error) as ctx:
            await self.add(**daily())
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(self.db.stored()["schedules"]["1"]["name"], "old")

    async def test_failed_load_is_retried(self):
        self.db.seed([{
            "id": 1, "name": "old", "macro": "M", "schedule_type": "daily",
            "time": "06:00", "params": {}, "enabled": True,
            "next_run": "2026-11-03T06:00:00",
        }])
        self.db.fail_gets = True
        await self.boot()
        self.db.fail_gets = False
        await self.s._ensure_loaded()
        self.assertEqual([x["name"] for x in self.listed()], ["old"])


class Migration(SchedulerCase):
    def legacy(self, **overrides):
        base = {
            "id": 1, "name": "old", "macro": "M", "schedule_type": "daily",
            "time": "06:00", "params": {}, "enabled": True,
            "next_run": "2026-11-03T06:00:00",
        }
        base.update(overrides)
        return base

    async def test_old_schedule_gets_safe_defaults(self):
        self.db.seed([self.legacy()])
        await self.boot()
        sched = self.s.schedules[1]
        self.assertEqual(sched["missed_run_policy"], "skip")
        self.assertIs(sched["skip_if_printing"], True)
        self.assertTrue(sched["enabled"])

    async def test_old_cron_next_run_is_recalculated(self):
        self.db.seed([self.legacy(
            schedule_type="cron", cron_expression="0 9 * * 1-5",
            next_run="2026-11-07T09:00:00",  # A Saturday, from the old parser
        )])
        await self.boot()
        self.assertEqual(self.s.schedules[1]["next_run"], "2026-11-03T09:00:00")

    async def test_invalid_stored_schedule_is_disabled_with_a_reason(self):
        cases = [
            dict(schedule_type="cron", cron_expression="bogus"),
            dict(macro="M\nFIRMWARE_RESTART"),
            dict(macro="M117 hello"),
            dict(schedule_type="interval", interval_minutes=0),
            dict(params={"A": "1\nB"}),
            dict(schedule_type="fortnightly"),
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.setUp()
                self.db.seed([self.legacy(**overrides)])
                await self.boot()
                await self.tick(T0 + timedelta(days=1))
                sched = self.s.schedules[1]
                self.assertFalse(sched["enabled"])
                self.assertEqual(sched["last_status"], "invalid")
                self.assertTrue(sched["last_error"])
                self.assertEqual(self.klippy.gcode, [])

    async def test_invalid_stored_schedule_cannot_be_enabled(self):
        self.db.seed([self.legacy(schedule_type="cron", cron_expression="bogus")])
        await self.boot()
        with self.assertRaises(self.server.error):
            await self.s._handle_toggle_schedule(FakeRequest(id=1))
        self.assertFalse(self.s.schedules[1]["enabled"])

    async def test_past_once_from_old_version_is_kept_and_reported_missed(self):
        self.db.seed([self.legacy(
            schedule_type="once", datetime="2026-11-01T06:00:00",
            next_run="2026-11-01T06:00:00",
        )])
        await self.boot()
        await self.tick()
        sched = self.s.schedules[1]
        self.assertEqual(sched["last_status"], "missed")
        self.assertFalse(sched["enabled"])
        self.assertEqual(self.klippy.gcode, [])

    async def test_completed_once_from_old_version_stays_valid(self):
        self.db.seed([self.legacy(
            schedule_type="once", datetime="2026-11-01T06:00:00",
            next_run="2026-11-01T06:00:00", enabled=False,
        )])
        await self.boot()
        self.assertNotEqual(self.s.schedules[1].get("last_status"), "invalid")


class Api(SchedulerCase):
    async def test_invalid_add_is_a_400_and_stores_nothing(self):
        await self.boot()
        for fields in [
            dict(name="x", macro="M", schedule_type="interval", interval_minutes=0),
            dict(name="x", macro="M", schedule_type="cron", cron_expression="bogus"),
            dict(name="x", macro="M", schedule_type="once", datetime="2026-11-02T19:00:00"),
        ]:
            with self.subTest(fields=fields):
                with self.assertRaises(self.server.error) as ctx:
                    await self.add(**fields)
                self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(self.s.schedules, {})

    async def test_unknown_id_is_a_404(self):
        await self.boot()
        for handler in (self.s._handle_toggle_schedule, self.s._handle_delete_schedule):
            with self.assertRaises(self.server.error) as ctx:
                await handler(FakeRequest(id=99))
            self.assertEqual(ctx.exception.status_code, 404)

    async def test_ids_are_not_reused_after_restart(self):
        await self.boot()
        first = await self.add(**daily())
        await self.s._handle_delete_schedule(FakeRequest(id=first["id"]))
        self.s = self.make()
        await self.boot()
        second = await self.add(**daily())
        self.assertNotEqual(first["id"], second["id"])

    async def test_list_text_reports_last_outcome(self):
        await self.boot()
        self.klippy.run_error = RuntimeError("boom")
        await self.add(**daily())
        await self.tick(T0 + timedelta(hours=1))
        text = (await self.s._handle_list_text(FakeRequest()))["text"]
        self.assertIn("Last result: failed", text)
        self.assertIn("boom", text)


class Lifecycle(SchedulerCase):
    async def test_background_loop_fires_due_schedule_and_stops_on_exit(self):
        self.db.seed([{
            "id": 1, "name": "old", "macro": "M", "schedule_type": "daily",
            "time": "20:00", "params": {}, "enabled": True,
            "next_run": "2026-11-02T20:00:00",
        }])
        await self.s.component_init()
        for _ in range(50):
            await asyncio.sleep(0.01)
            if self.klippy.gcode:
                break
        self.assertEqual(self.klippy.gcode, ["M"])
        await self.s.on_exit()
        self.assertTrue(self.s._loop_task.done())


if __name__ == "__main__":
    unittest.main()
