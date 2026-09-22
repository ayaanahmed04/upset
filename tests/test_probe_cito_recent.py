"""Check safe Cito event/bout discovery without using a live API key."""

import unittest

from upset.data.probe_cito_recent import summarize_listing


class ProbeRecentTests(unittest.TestCase):
    def test_event_listing_prints_only_identifiers_and_dates(self):
        events = {
            "data": {
                "events": [
                    {
                        "id": "event-1",
                        "slug": "ufc-recent",
                        "eventDate": "2026-09-19",
                        "hasStats": True,
                        "privateValue": "do not print",
                    }
                ]
            }
        }
        summary = summarize_listing(events, kind="event")
        self.assertEqual(
            summary,
            [
                {
                    "id": "event-1",
                    "slug": "ufc-recent",
                    "event_date": "2026-09-19",
                    "has_stats": True,
                }
            ],
        )
        self.assertNotIn("do not print", str(summary))

    def test_bout_listing_accepts_nested_or_flat_rows(self):
        nested = {
            "data": {"bouts": [{"bout": {"id": "bout-1", "status": "completed"}}]}
        }
        flat = {"data": [{"id": 12910, "hasStats": True}]}
        self.assertEqual(
            summarize_listing(nested, kind="bout"),
            [{"id": "bout-1", "status": "completed", "has_stats": None}],
        )
        self.assertEqual(summarize_listing(flat, kind="bout")[0]["id"], "12910")

    def test_unknown_listing_does_not_guess(self):
        for payload in (
            None,
            {"data": {"surprise": []}},
            {"success": False, "data": []},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                summarize_listing(payload, kind="event")


if __name__ == "__main__":
    unittest.main()
