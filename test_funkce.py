import unittest

from funkce import (
    FUNCTION_CLOSING,
    FUNCTION_DAILY,
    FUNCTION_SPECIAL,
    apply_function_mails,
    load_function_mails,
)


class FunctionMailTests(unittest.TestCase):
    def test_loads_separate_recipients_per_function(self):
        mails = load_function_mails(
            {
                "mail_prijemci": ["scio@example.cz"],
                "mail_text": "Počty",
                "mail_jen_varne_dny": True,
                "uzaverka": {
                    "mail_prijemci": ["ucetni@example.cz"],
                    "mail_text": "Uzávěrka",
                },
                "z17": {"mail_prijemci": ["reditel@example.cz"], "mail_text": "Z17"},
            }
        )
        self.assertEqual(mails[FUNCTION_DAILY]["prijemci"], ["scio@example.cz"])
        self.assertTrue(mails[FUNCTION_DAILY]["jen_varne_dny"])
        self.assertEqual(mails[FUNCTION_CLOSING]["prijemci"], ["ucetni@example.cz"])
        self.assertEqual(mails[FUNCTION_SPECIAL]["prijemci"], ["reditel@example.cz"])

    def test_apply_keeps_closing_reports_and_does_not_copy_daily_mail(self):
        updated = apply_function_mails(
            {
                "uzaverka": {"sestavy": ["fksp"], "mail_prijemci": []},
                "z17": {"vystup": "vystup/z17/{rok}"},
                "mail_prijemci": ["stare@example.cz"],
            },
            {
                FUNCTION_DAILY: {
                    "prijemci": ["scio@example.cz"],
                    "text": "Počty",
                    "jen_varne_dny": False,
                },
                FUNCTION_CLOSING: {
                    "prijemci": ["ucetni@example.cz"],
                    "text": "Uzávěrka",
                    "jen_varne_dny": False,
                },
                FUNCTION_SPECIAL: {
                    "prijemci": [],
                    "text": "",
                    "jen_varne_dny": False,
                },
            },
            sender="podpora@altisima.cz",
        )
        self.assertEqual(updated["mail_prijemci"], ["scio@example.cz"])
        self.assertEqual(updated["uzaverka"]["sestavy"], ["fksp"])
        self.assertEqual(updated["uzaverka"]["mail_prijemci"], ["ucetni@example.cz"])
        self.assertNotEqual(
            updated["mail_prijemci"], updated["uzaverka"]["mail_prijemci"]
        )


if __name__ == "__main__":
    unittest.main()
