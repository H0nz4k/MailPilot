import json
import tempfile
import threading
import unittest
from pathlib import Path

from stravovaci_gui import StravovaciApp, database_parameters, load_ui_config


class GuiHelperTests(unittest.TestCase):
    def test_database_parameters_never_add_password(self):
        result = database_parameters(
            {
                "databaze": {
                    "host": "10.0.0.5",
                    "port": 5433,
                    "dbname": "vyvoj",
                    "user": "technik",
                    "password": "legacy",
                }
            }
        )
        self.assertNotIn("password", result)
        self.assertEqual(result["port"], 5433)

    def test_load_ui_config_reads_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                json.dumps({"databaze": {"host": "db"}}), encoding="utf-8"
            )
            self.assertEqual(load_ui_config(path)["databaze"]["host"], "db")

    def test_background_error_survives_delayed_tk_callback(self):
        callback_ready = threading.Event()
        callbacks = []

        class FakeRoot:
            def after(self, _delay, callback):
                callbacks.append(callback)
                callback_ready.set()

        app = StravovaciApp.__new__(StravovaciApp)
        app.root = FakeRoot()
        received = []

        def fail_worker():
            raise RuntimeError("skutečná chyba PDF")

        app._run_background(fail_worker, lambda _result: None, received.append)
        self.assertTrue(callback_ready.wait(2))
        callbacks[0]()
        self.assertEqual(str(received[0]), "skutečná chyba PDF")


if __name__ == "__main__":
    unittest.main()
