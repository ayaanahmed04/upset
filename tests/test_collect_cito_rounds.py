"""Verify local Cito round collection without making provider requests."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from upset.data.collect_cito_rounds import (
    RoundDownloadError,
    collect_bouts,
    collect_one,
    read_bout_ids,
    round_row_count,
    validate_bout_ids,
)


def response(payload, status=200):
    return SimpleNamespace(status_code=status, json=lambda: payload)


class CollectCitoRoundsTests(unittest.TestCase):
    def test_saves_original_payload_and_uses_verified_cache(self):
        payload = {
            "success": True,
            "data": [{"round": 1, "boutId": "bout-1", "fighterSlug": "a"}],
        }
        calls = []

        def get(url, *, headers, timeout):
            calls.append((url, headers, timeout))
            return response(payload)

        with TemporaryDirectory() as folder:
            directory = Path(folder)
            self.assertEqual(collect_one("bout-1", directory, "secret", get), (1, True))
            saved = json.loads((directory / "bout-1.json").read_text())
            self.assertEqual(saved["source"], "cito")
            self.assertEqual(saved["source_bout_id"], "bout-1")
            self.assertEqual(saved["response"], payload)
            self.assertNotIn("secret", str(saved))
            self.assertEqual(
                collect_one("bout-1", directory, "secret", get), (1, False)
            )
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0][0].endswith("/bouts/bout-1/rounds"))
            self.assertEqual(calls[0][1], {"x-api-key": "secret"})
            self.assertEqual(calls[0][2], 20)

    def test_access_denied_stops_without_saving_or_printing_message(self):
        payload = {
            "error": {
                "code": "HISTORY_WINDOW_EXCEEDED",
                "message": "Your key secret cannot fetch this bout.",
            }
        }
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            with self.assertRaisesRegex(
                RoundDownloadError, "HISTORY_WINDOW_EXCEEDED"
            ) as error:
                collect_one(
                    "bout-1", directory, "secret",
                    lambda *a, **k: response(payload, 403),
                )
            self.assertNotIn("secret", str(error.exception))
            self.assertFalse((directory / "bout-1.json").exists())

    def test_unknown_shape_and_corrupt_cache_stop_before_false_completion(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            invalid = response({"success": True, "data": {"surprise": [1]}})
            with self.assertRaisesRegex(RoundDownloadError, "unknown data shape"):
                collect_one("bout-1", directory, "secret", lambda *a, **k: invalid)
            self.assertEqual(list(directory.iterdir()), [])

            (directory / "bout-1.json").write_text("not JSON", encoding="utf-8")
            with self.assertRaisesRegex(
                RoundDownloadError, "Existing round file is invalid"
            ):
                collect_one(
                    "bout-1", directory, "secret",
                    lambda *a, **k: self.fail(
                        "Corrupt cached data must not be skipped"
                    ),
                )

    def test_mismatched_bout_and_echoed_api_key_are_not_cached(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            for payload, message in (
                ({"data": [{"boutId": "bout-2"}]}, "different bout ID"),
                ({"data": [{"boutId": "bout-1", "note": "secret"}]}, "API key"),
            ):
                with self.subTest(message=message), self.assertRaisesRegex(
                    RoundDownloadError, message
                ):
                    collect_one(
                        "bout-1", directory, "secret",
                        lambda *a, payload=payload, **k: response(payload),
                    )
                self.assertFalse((directory / "bout-1.json").exists())

    def test_resume_caps_new_requests_and_skips_cached_bouts(self):
        calls = []
        waits = []

        def get(url, **kwargs):
            calls.append(url)
            return response({"data": {"rounds": [{"round": 1}]}})

        with TemporaryDirectory() as folder:
            directory = Path(folder)
            ids = ["bout-1", "bout-2", "bout-3"]
            first = collect_bouts(
                ids, directory, "secret", get, limit=1, sleep=waits.append
            )
            second = collect_bouts(
                ids, directory, "secret", get, limit=2, sleep=waits.append
            )
            self.assertEqual(first, {"fetched": 1, "cached": 0, "round_rows": 1})
            self.assertEqual(second, {"fetched": 2, "cached": 1, "round_rows": 3})
            self.assertEqual(len(calls), 3)
            self.assertEqual(waits, [7.0])

    def test_rejects_unsafe_or_duplicate_manifest_and_empty_rounds(self):
        for ids in ([], ["same", "same"], ["../secret"], ["bout?round=2"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                validate_bout_ids(ids)
        with TemporaryDirectory() as folder:
            manifest = Path(folder) / "bouts.txt"
            manifest.write_text("bout-1\n\nbout-2\n", encoding="utf-8")
            self.assertEqual(read_bout_ids(manifest), ["bout-1", "bout-2"])
        with self.assertRaisesRegex(RoundDownloadError, "no valid rows"):
            round_row_count({"data": []})


if __name__ == "__main__":
    unittest.main()
