import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from planovac import (
    ACTION_CLOSING,
    ACTION_POCTY,
    ACTION_SPECIAL,
    launcher_command,
    load_jobs,
    next_run_at,
    parse_job,
    previous_closing_period,
    save_jobs,
    scheduled_z17_year,
)
from stravovaci_sestava import ConfigError


class PlanovacTests(unittest.TestCase):
    def test_parses_daily_pocty_job_and_exe_command(self):
        job = parse_job(
            {
                "name": "Počty",
                "action": ACTION_POCTY,
                "path": r"C:\App\MailPilot.exe",
                "enabled": True,
                "schedule": {"type": "daily", "time": "6:30"},
            }
        )
        self.assertEqual(job.time, "06:30")
        self.assertEqual(
            launcher_command(job), [r"C:\App\MailPilot.exe", "--poctyemailem"]
        )

    def test_assigns_closing_and_special_functions_to_exe(self):
        closing_job = parse_job(
            {
                "name": "Uzávěrka",
                "action": ACTION_CLOSING,
                "path": r"C:\App\MailPilot.exe",
                "enabled": True,
                "schedule": {"type": "daily", "time": "07:00"},
            }
        )
        special_job = parse_job(
            {
                "name": "Z17",
                "action": ACTION_SPECIAL,
                "path": r"C:\App\MailPilot.exe",
                "enabled": True,
                "schedule": {"type": "daily", "time": "08:00"},
            }
        )
        reference = datetime(2026, 8, 21, 10, 0)
        self.assertEqual(previous_closing_period(reference), "072026")
        self.assertEqual(
            launcher_command(closing_job, reference=reference),
            [r"C:\App\MailPilot.exe", "--zaverka_072026"],
        )
        self.assertEqual(scheduled_z17_year(reference), 2026)
        self.assertEqual(
            launcher_command(special_job, reference=reference),
            [r"C:\App\MailPilot.exe", "--z17_2026"],
        )

    def test_rejects_duplicate_names_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planovac.json"
            path.write_text(
                '{"jobs":[{"name":"A","action":"vlastni","path":"a.bat",'
                '"schedule":{"type":"interval","minutes":5},"enabled":true},'
                '{"name":"a","action":"vlastni","path":"b.bat",'
                '"schedule":{"type":"interval","minutes":5},"enabled":true}]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "opakovat"):
                load_jobs(path)

    def test_roundtrip_save_and_next_daily_run(self):
        job = parse_job(
            {
                "name": "Ráno",
                "action": "vlastni",
                "path": "spustit_poctyemailem.bat",
                "enabled": True,
                "schedule": {"type": "daily", "time": "06:30"},
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planovac.json"
            save_jobs(path, [job])
            loaded = load_jobs(path)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "Ráno")
        reference = datetime(2026, 8, 20, 7, 0)
        nxt = next_run_at(loaded[0], reference=reference)
        self.assertEqual(nxt, datetime(2026, 8, 21, 6, 30))


if __name__ == "__main__":
    unittest.main()
