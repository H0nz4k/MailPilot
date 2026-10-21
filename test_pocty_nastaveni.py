import unittest

from pocty_nastaveni import (
    all_client_categories,
    parse_client_categories,
    peek_client_categories,
)
from stravovaci_sestava import ConfigError


class ClientCategoryTests(unittest.TestCase):
    def test_default_is_all_even_if_old_root_list_excludes_school(self):
        raw = {"povolene_kategorie": ["ZAM"]}
        self.assertTrue(all_client_categories(raw))
        self.assertEqual(parse_client_categories(raw), ())

    def test_nested_old_list_does_not_restrict_without_admin_opt_in(self):
        raw = {
            "povolene_kategorie": ["1", "2", "3"],
            "poctyemailem": {"povolene_kategorie": ["ZAM", "1STD"]},
        }
        self.assertEqual(parse_client_categories(raw), ())

    def test_explicit_admin_selection_overrides_legacy_root(self):
        raw = {
            "povolene_kategorie": ["1", "2", "3"],
            "poctyemailem": {
                "vsechny_kategorie": False,
                "povolene_kategorie": ["ZAM", " 1STD ", "ZAM"],
            },
        }
        self.assertFalse(all_client_categories(raw))
        self.assertEqual(parse_client_categories(raw), ("ZAM", "1STD"))

    def test_explicit_admin_all_overrides_old_selected_list(self):
        raw = {
            "poctyemailem": {
                "vsechny_kategorie": True,
                "povolene_kategorie": ["ZAM"],
            }
        }
        self.assertEqual(parse_client_categories(raw), ())

    def test_rejects_empty_explicit_selection(self):
        with self.assertRaisesRegex(ConfigError, "alespoň jednu"):
            parse_client_categories({
                "povolene_kategorie": [],
                "poctyemailem": {"vsechny_kategorie": False},
            })

    def test_rejects_invalid_switch(self):
        with self.assertRaisesRegex(ConfigError, "true/false"):
            parse_client_categories({
                "poctyemailem": {"vsechny_kategorie": "false"},
            })

    def test_peek_allows_empty_selection_in_ui(self):
        self.assertEqual(peek_client_categories({}), [])
        self.assertEqual(
            peek_client_categories({"poctyemailem": {"povolene_kategorie": ["1"]}}),
            ["1"],
        )


if __name__ == "__main__":
    unittest.main()
