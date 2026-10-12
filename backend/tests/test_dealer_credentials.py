import unittest

from pydantic import ValidationError
from schemas.dealer import DealerCredentials


class DealerCredentialsTests(unittest.TestCase):
    def test_accepts_valid_passwords(self):
        valid_passwords = ["Dealer123", "GasQ@2026", "Password123!"]

        for password in valid_passwords:
            with self.subTest(password=password):
                credentials = DealerCredentials(username="dealer_1", password=password)
                self.assertEqual(credentials.password, password)

    def test_rejects_password_missing_digit(self):
        with self.assertRaises(ValidationError):
            DealerCredentials(username="dealer_1", password="password")

    def test_rejects_password_missing_letter(self):
        with self.assertRaises(ValidationError):
            DealerCredentials(username="dealer_1", password="12345678")

    def test_rejects_short_password(self):
        with self.assertRaises(ValidationError):
            DealerCredentials(username="dealer_1", password="Ab1")

    def test_rejects_unsupported_password_character(self):
        with self.assertRaises(ValidationError):
            DealerCredentials(username="dealer_1", password="Password123:")

    def test_preserves_username_validation(self):
        with self.assertRaises(ValidationError):
            DealerCredentials(username="1bad", password="Dealer123")


if __name__ == "__main__":
    unittest.main()
