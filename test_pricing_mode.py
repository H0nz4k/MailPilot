import unittest
from unittest import mock

from services import pricing_mode


class PricingModeTests(unittest.TestCase):
    def test_normalize_pricing_mode_handles_common_representations(self):
        self.assertEqual(pricing_mode.normalize_pricing_mode(0), pricing_mode.PRICING_MODE_SAZBY)
        self.assertEqual(pricing_mode.normalize_pricing_mode(1), pricing_mode.PRICING_MODE_CENIK)
        self.assertEqual(pricing_mode.normalize_pricing_mode(False), pricing_mode.PRICING_MODE_SAZBY)
        self.assertEqual(pricing_mode.normalize_pricing_mode(True), pricing_mode.PRICING_MODE_CENIK)
        self.assertEqual(pricing_mode.normalize_pricing_mode("0"), pricing_mode.PRICING_MODE_SAZBY)
        self.assertEqual(pricing_mode.normalize_pricing_mode("true"), pricing_mode.PRICING_MODE_CENIK)
        self.assertIsNone(pricing_mode.normalize_pricing_mode("unknown"))

    def test_detect_pricing_mode_prefers_db_function(self):
        cursor = mock.Mock()
        cursor.fetchone.return_value = (1,)
        info = pricing_mode.detect_pricing_mode_info(cursor)
        self.assertEqual(info.mode, pricing_mode.PRICING_MODE_CENIK)
        self.assertEqual(info.source, "public.pouzivatcenik()")
        self.assertIn("pouzivatcenik", cursor.execute.call_args.args[0].lower())

    def test_detect_pricing_mode_falls_back_to_parametry(self):
        cursor = mock.Mock()
        cursor.connection = mock.Mock()
        cursor.execute.side_effect = [Exception("missing function"), None]
        cursor.fetchone.return_value = ("0",)
        info = pricing_mode.detect_pricing_mode_info(cursor)
        self.assertEqual(info.mode, pricing_mode.PRICING_MODE_SAZBY)
        self.assertIn("parametry", info.source)
        cursor.connection.rollback.assert_called()

    def test_detect_pricing_mode_returns_unknown_when_both_queries_fail(self):
        cursor = mock.Mock()
        cursor.connection = mock.Mock()
        cursor.execute.side_effect = [Exception("x"), Exception("y")]
        info = pricing_mode.detect_pricing_mode_info(cursor)
        self.assertIsNone(info.mode)
        self.assertEqual(info.source, "unknown")


if __name__ == "__main__":
    unittest.main()
