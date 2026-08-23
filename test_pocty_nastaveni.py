import unittest

from pocty_nastaveni import parse_client_categories, peek_client_categories
from stravovaci_sestava import ConfigError


class ClientCategoryTests(unittest.TestCase):
    def test_uses_root_list_when_pocty_block_is_missing(self):
        categories = parse_client_categories(
            {"povolene_kategorie": ["1STD", " ZAM ", "1STD"]}
        )
        self.assertEqual(categories, ("1STD", "ZAM"))

    def test_nested_pocty_list_overrides_root(self):
        categories = parse_client_categories(
            {
                "povolene_kategorie": ["1", "2", "3"],
                "poctyemailem": {"povolene_kategorie": ["ZAM", "1STD"]},
            }
        )
        self.assertEqual(categories, ("ZAM", "1STD"))

    def test_rejects_all_categories_switch(self):
        with self.assertRaisesRegex(ConfigError, "všechny kategorie"):
            parse_client_categories(
                {
                    "povolene_kategorie": ["1STD"],
                    "poctyemailem": {
                        "vsechny_kategorie": True,
                        "povolene_kategorie": ["1STD"],
                    },
                }
            )

    def test_rejects_empty_client_list(self):
        with self.assertRaisesRegex(ConfigError, "neprázdné"):
            parse_client_categories({"povolene_kategorie": []})

    def test_peek_allows_empty_selection_in_ui(self):
        self.assertEqual(peek_client_categories({}), [])
        self.assertEqual(
            peek_client_categories({"poctyemailem": {"povolene_kategorie": ["1"]}}),
            ["1"],
        )


if __name__ == "__main__":
    unittest.main()
