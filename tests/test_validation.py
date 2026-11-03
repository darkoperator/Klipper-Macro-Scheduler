import unittest
from datetime import datetime

from helpers import ms

NOW = datetime(2026, 11, 2, 20, 0)


def fields(**overrides):
    base = {"name": "n", "macro": "M", "schedule_type": "daily", "time": "06:00"}
    base.update(overrides)
    return base


class Accepted(unittest.TestCase):
    def test_policy_defaults_are_the_safe_ones(self):
        out = ms.validate_schedule(fields(), NOW)
        self.assertEqual(out["missed_run_policy"], "skip")
        self.assertIs(out["skip_if_printing"], True)

    def test_policies_can_be_opted_out_per_schedule(self):
        out = ms.validate_schedule(
            fields(missed_run_policy="run", skip_if_printing=False), NOW
        )
        self.assertEqual(out["missed_run_policy"], "run")
        self.assertIs(out["skip_if_printing"], False)

    def test_each_type_keeps_its_own_fields(self):
        cases = [
            (dict(schedule_type="once", datetime="2026-11-03T07:00"), "datetime"),
            (dict(schedule_type="daily", time="7:05"), "time"),
            (dict(schedule_type="weekly", time="07:00", days=[0, 6]), "days"),
            (dict(schedule_type="interval", interval_minutes=5), "interval_minutes"),
            (dict(schedule_type="cron", cron_expression="0 9 * * 1-5"), "cron_expression"),
        ]
        for extra, key in cases:
            with self.subTest(extra=extra):
                self.assertIn(key, ms.validate_schedule(fields(**extra), NOW))

    def test_interval_given_as_numeric_string_is_converted(self):
        out = ms.validate_schedule(
            fields(schedule_type="interval", interval_minutes="15"), NOW
        )
        self.assertEqual(out["interval_minutes"], 15)


class Rejected(unittest.TestCase):
    CASES = [
        dict(name=""),
        dict(name="   "),
        dict(name="a\nb"),
        dict(macro=""),
        dict(macro="M\nFIRMWARE_RESTART"),
        dict(macro="M X=1"),
        dict(macro="M;"),
        dict(schedule_type="fortnightly"),
        dict(time="25:00"),
        dict(time="06:61"),
        dict(time="noon"),
        dict(schedule_type="weekly", days=[]),
        dict(schedule_type="weekly", days=[7]),
        dict(schedule_type="weekly", days=[-1]),
        dict(schedule_type="weekly", days=["1"]),
        dict(schedule_type="weekly", days=[True]),
        dict(schedule_type="weekly", days=1),
        dict(schedule_type="interval", interval_minutes=0),
        dict(schedule_type="interval", interval_minutes=-5),
        dict(schedule_type="interval", interval_minutes=1.5),
        dict(schedule_type="interval", interval_minutes="soon"),
        dict(schedule_type="interval", interval_minutes=True),
        dict(schedule_type="cron", cron_expression="bogus"),
        dict(schedule_type="once", datetime="not-a-date"),
        dict(schedule_type="once", datetime="2026-11-03T07:00:00+00:00"),
        dict(schedule_type="once", datetime="2026-11-02T19:59:00"),
        dict(params="TEMP=60"),
        dict(params={"BAD KEY": 1}),
        dict(params={"A\nB": 1}),
        dict(params={"A": "1\nFIRMWARE_RESTART"}),
        dict(params={"A": "1;x"}),
        dict(params={"A": 'x"y'}),
        dict(params={"A": [1]}),
        dict(params={"A": None}),
        dict(missed_run_policy="maybe"),
        dict(skip_if_printing="sometimes"),
    ]

    def test_invalid_input_raises(self):
        for overrides in self.CASES:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    ms.validate_schedule(fields(**overrides), NOW)


class Gcode(unittest.TestCase):
    def test_macro_without_params(self):
        self.assertEqual(ms.build_gcode("M", {}), "M")

    def test_params_are_appended(self):
        self.assertEqual(ms.build_gcode("M", {"A": 1, "B": 2.5}), "M A=1 B=2.5")

    def test_values_with_spaces_or_empty_are_quoted(self):
        self.assertEqual(
            ms.build_gcode("M", {"FILE": "my part.gcode", "E": ""}),
            'M FILE="my part.gcode" E=""',
        )


if __name__ == "__main__":
    unittest.main()
