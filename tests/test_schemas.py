from decimal import Decimal
import unittest

from pydantic import ValidationError

from schemas import ExpenseCreate, GroupCreate, GroupMemberCreate, UserCreate


class NameValidationTests(unittest.TestCase):
    def test_names_have_surrounding_whitespace_removed(self):
        self.assertEqual(UserCreate(name="  Mohit  ").name, "Mohit")
        self.assertEqual(GroupCreate(name="  Trip  ", created_by=1).name, "Trip")

    def test_blank_and_long_names_are_rejected(self):
        for schema, extra in ((UserCreate, {}), (GroupCreate, {"created_by": 1})):
            for name in ("", "   ", "a" * 101):
                with self.subTest(schema=schema.__name__, name=name):
                    with self.assertRaises(ValidationError):
                        schema(name=name, **extra)

    def test_membership_and_creator_ids_must_be_positive(self):
        for invalid_id in (0, -1):
            with self.subTest(user_id=invalid_id):
                with self.assertRaises(ValidationError):
                    GroupCreate(name="Trip", created_by=invalid_id)
                with self.assertRaises(ValidationError):
                    GroupMemberCreate(user_id=invalid_id)


class ExpenseValidationTests(unittest.TestCase):
    def test_valid_amounts_are_decimal_values(self):
        for amount in ("0.01", "1200.00", "9999999999.99", 1200):
            with self.subTest(amount=amount):
                expense = ExpenseCreate(paid_by=1, amount=amount, description="Dinner")
                self.assertIsInstance(expense.amount, Decimal)
                self.assertEqual(expense.amount, Decimal(str(amount)))

    def test_invalid_amounts_are_rejected(self):
        for amount in ("0", "-1.00", "1.001", "10000000000.00", "NaN", "Infinity", "not-money"):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    ExpenseCreate(paid_by=1, amount=amount, description="Dinner")

    def test_description_is_trimmed(self):
        expense = ExpenseCreate(paid_by=1, amount="10.00", description="  Dinner  ")
        self.assertEqual(expense.description, "Dinner")

    def test_blank_description_is_rejected(self):
        for description in ("", "   "):
            with self.subTest(description=description):
                with self.assertRaises(ValidationError):
                    ExpenseCreate(paid_by=1, amount="10.00", description=description)

    def test_payer_id_must_be_positive(self):
        for payer_id in (0, -1):
            with self.subTest(payer_id=payer_id):
                with self.assertRaises(ValidationError):
                    ExpenseCreate(paid_by=payer_id, amount="10.00", description="Dinner")

    def test_expense_fields_are_required(self):
        valid = {"paid_by": 1, "amount": "10.00", "description": "Dinner"}
        for field in valid:
            with self.subTest(missing_field=field):
                with self.assertRaises(ValidationError):
                    ExpenseCreate(**{key: value for key, value in valid.items() if key != field})
