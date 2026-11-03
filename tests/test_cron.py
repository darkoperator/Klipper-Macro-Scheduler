import unittest
from datetime import datetime

from helpers import ms

NOW = datetime(2026, 11, 2, 20, 11, 47)  # A Monday


class NextRun(unittest.TestCase):
    CASES = [
        ("* * * * *", NOW, datetime(2026, 11, 2, 20, 12)),
        ("*/15 * * * *", NOW, datetime(2026, 11, 2, 20, 15)),
        ("0 9,17 * * *", NOW, datetime(2026, 11, 3, 9, 0)),
        ("0 9,17 * * *", datetime(2026, 11, 3, 10, 0), datetime(2026, 11, 3, 17, 0)),
        ("0 9 * * 1-5", datetime(2026, 11, 6, 10, 0), datetime(2026, 11, 9, 9, 0)),
        ("0 9 * * 7", NOW, datetime(2026, 11, 8, 9, 0)),
        ("0 9 * * 0", NOW, datetime(2026, 11, 8, 9, 0)),
        ("0 9 1,15 * *", NOW, datetime(2026, 11, 15, 9, 0)),
        ("0 9 * 1,6 *", NOW, datetime(2027, 1, 1, 9, 0)),
        ("*/15 8-17 * * *", datetime(2026, 11, 2, 17, 50), datetime(2026, 11, 3, 8, 0)),
        ("0-30/10 * * * *", datetime(2026, 11, 2, 20, 21), datetime(2026, 11, 2, 20, 30)),
        ("0 */3 * * *", NOW, datetime(2026, 11, 2, 21, 0)),
        ("0 0 29 2 *", NOW, datetime(2028, 2, 29, 0, 0)),
    ]

    def test_next_run_matches_cron_semantics(self):
        for expr, now, expected in self.CASES:
            with self.subTest(expr=expr, now=now):
                self.assertEqual(ms.parse_cron(expr).next_after(now), expected)

    def test_next_run_is_strictly_after_now(self):
        at = datetime(2026, 11, 2, 9, 0)
        self.assertEqual(
            ms.parse_cron("0 9 * * *").next_after(at), datetime(2026, 11, 3, 9, 0)
        )

    def test_day_of_month_or_weekday_when_both_are_restricted(self):
        # Standard cron: the 3rd (a Tuesday) OR any Friday.
        cron = ms.parse_cron("0 9 3 * 5")
        self.assertEqual(cron.next_after(NOW), datetime(2026, 11, 3, 9, 0))
        self.assertEqual(
            cron.next_after(datetime(2026, 11, 3, 9, 0)), datetime(2026, 11, 6, 9, 0)
        )


class Rejected(unittest.TestCase):
    def test_invalid_expressions_raise(self):
        for expr in [
            "", "bogus", "a b c d e", "* * * *", "* * * * * *", "60 * * * *",
            "* 24 * * *", "* * 0 * *", "* * 32 * *", "* * * 0 *", "* * * 13 *",
            "* * * * 8", "5-1 * * * *", "*/0 * * * *", "1,, * * * *",
            "0 9 * * MON", "0 9 * JAN *", "1/5 * * * *", "-1 * * * *",
        ]:
            with self.subTest(expr=expr):
                with self.assertRaises(ValueError):
                    ms.parse_cron(expr)

    def test_date_that_never_occurs_is_rejected(self):
        with self.assertRaises(ValueError):
            ms.parse_cron("0 0 31 2 *")


if __name__ == "__main__":
    unittest.main()
