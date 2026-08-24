import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import scheduler_runtime


class SchedulerRuntimeCredentialTests(unittest.TestCase):
    def setUp(self):
        self.database = {
            "host": "db",
            "port": 5432,
            "dbname": "jidelna",
            "user": "tester",
        }

    def test_system_account_requires_machine_scope_secret(self):
        with (
            mock.patch.object(
                scheduler_runtime,
                "machine_password_available",
                return_value=False,
            ),
            mock.patch.object(scheduler_runtime, "get_password", return_value="tajne"),
        ):
            ok, detail = scheduler_runtime.scheduler_credential_status(
                self.database,
                runtime_running=True,
                service_running=True,
                service_account="LocalSystem",
                runtime_identity="DOMAIN\\tester",
            )
        self.assertFalse(ok)
        self.assertIn("machine-scope", detail)

    def test_same_user_service_can_use_user_keyring(self):
        with (
            mock.patch.object(
                scheduler_runtime,
                "machine_password_available",
                return_value=False,
            ),
            mock.patch.object(scheduler_runtime, "get_password", return_value="tajne"),
        ):
            ok, detail = scheduler_runtime.scheduler_credential_status(
                self.database,
                runtime_running=True,
                service_running=True,
                service_account="DOMAIN\\tester",
                runtime_identity="OTHER\\tester",
            )
        self.assertTrue(ok)
        self.assertIn("stejným uživatelem", detail)


class SchedulerRuntimeSnapshotTests(unittest.TestCase):
    def test_snapshot_without_runtime_or_service_is_not_running(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            state_path = Path(directory) / "planovac_runtime.json"
            log_path = Path(directory) / "logy" / "mailpilot_scheduler.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            runtime_status = scheduler_runtime.RuntimeStatus(
                running=False,
                pid=None,
                detail="nebezi",
                state_path=state_path,
                log_path=log_path,
            )
            service_status = scheduler_runtime.SchedulerServiceStatus(
                installed=False,
                running=False,
                service_name="MailPilot_denniprehled",
                detail="",
            )
            with (
                mock.patch.object(
                    scheduler_runtime, "read_runtime_status", return_value=runtime_status
                ),
                mock.patch.object(
                    scheduler_runtime, "read_service_status", return_value=service_status
                ),
                mock.patch.object(
                    scheduler_runtime, "_load_json", return_value={"jobs": {}}
                ),
                mock.patch.object(
                    scheduler_runtime, "read_jobs", return_value=[]
                ),
                mock.patch.object(
                    scheduler_runtime,
                    "load_raw_config",
                    return_value={"databaze": {"host": "x", "port": 5432, "dbname": "d", "user": "u"}},
                ),
                mock.patch.object(
                    scheduler_runtime,
                    "database_parameters",
                    return_value=self._database_parameters(),
                ),
                mock.patch.object(
                    scheduler_runtime,
                    "scheduler_credential_status",
                    return_value=(True, "OK"),
                ),
            ):
                snapshot = scheduler_runtime.read_runtime_snapshot(
                    config_path, "MailPilot_denniprehled"
                )
        self.assertFalse(snapshot.running)
        self.assertEqual(snapshot.runtime_type, "not running")
        self.assertEqual(snapshot.next_run, "—")

    @staticmethod
    def _database_parameters() -> dict[str, object]:
        return {
            "host": "x",
            "port": 5432,
            "dbname": "d",
            "user": "u",
        }


if __name__ == "__main__":
    unittest.main()
