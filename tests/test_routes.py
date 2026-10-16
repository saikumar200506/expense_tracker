from datetime import datetime, timezone
from decimal import Decimal
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from schemas import ExpenseCreate, SettlementMessageResponse


# Importing database.py builds an engine but does not connect. Temporary test
# settings keep these unit tests independent of a developer's .env file.
with patch.dict(os.environ, {
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "1",
    "DB_NAME": "expense_tracker_tests",
    "DB_USER": "test_user",
    "DB_PASSWORD": "test_password",
}):
    from models import Expense, ExpenseSplit, Group, User
    from routers.expenses import create_expense
    from routers.groups import get_settlement_suggestions


class ExpenseCreationTests(unittest.TestCase):
    def setUp(self):
        # Fail immediately if a regression accidentally opens a real connection.
        guard = patch("sqlalchemy.engine.Engine.connect", side_effect=AssertionError("Unit test attempted a database connection"))
        guard.start()
        self.addCleanup(guard.stop)
        self.db = MagicMock(spec=Session)
        self.records = {
            (Group, 1): Group(id=1, name="Trip", created_by=1),
            (User, 1): User(id=1, name="saikumar"),
        }
        self.db.get.side_effect = lambda model, record_id: self.records.get((model, record_id))
        self.db.scalars.return_value = [3, 1, 2]
        self.added = []
        self.db.add.side_effect = self.added.append
        self.db.flush.side_effect = self.assign_generated_fields
        self.next_id = 1

    def assign_generated_fields(self):
        for record in self.added:
            if isinstance(record, Expense) and record.id is None:
                record.id = self.next_id
                record.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
                self.next_id += 1

    def create(self, amount="100.00"):
        return create_expense(
            group_id=1,
            expense_data=ExpenseCreate(paid_by=1, amount=amount, description="Dinner"),
            db=self.db,
        )

    def test_creates_expense_and_exact_shares_for_all_current_members(self):
        response = self.create()
        expenses = [row for row in self.added if isinstance(row, Expense)]
        splits = [row for row in self.added if isinstance(row, ExpenseSplit)]
        self.assertEqual(len(expenses), 1)
        self.assertEqual(response.id, expenses[0].id)
        self.assertEqual(response.group_id, 1)
        self.assertEqual(response.paid_by, 1)
        self.assertEqual(response.payer_name, "saikumar")
        self.assertEqual(response.amount, Decimal("100.00"))
        self.assertEqual(response.split_type, "equal")
        self.assertEqual({row.user_id: row.share_amount for row in splits}, {
            1: Decimal("33.34"), 2: Decimal("33.33"), 3: Decimal("33.33"),
        })
        self.assertTrue(all(row.expense_id == response.id for row in splits))
        self.assertEqual(sum(row.share_amount for row in splits), response.amount)
        self.db.commit.assert_called_once()
        self.db.rollback.assert_not_called()

    def test_adding_a_member_does_not_change_previous_expense_shares(self):
        self.db.scalars.side_effect = [[1, 2], [1, 2, 3]]
        first = self.create("1200.00")
        second = self.create("1500.00")
        first_shares = {row.user_id: row.share_amount for row in self.added
                        if isinstance(row, ExpenseSplit) and row.expense_id == first.id}
        second_shares = {row.user_id: row.share_amount for row in self.added
                         if isinstance(row, ExpenseSplit) and row.expense_id == second.id}
        self.assertEqual(first_shares, {1: Decimal("600.00"), 2: Decimal("600.00")})
        self.assertEqual(second_shares, {1: Decimal("500.00"), 2: Decimal("500.00"), 3: Decimal("500.00")})

    def test_missing_group_is_rejected_before_writing(self):
        del self.records[(Group, 1)]
        with self.assertRaises(HTTPException) as caught:
            self.create()
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail, "Group not found.")
        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_missing_payer_is_rejected_before_writing(self):
        del self.records[(User, 1)]
        with self.assertRaises(HTTPException) as caught:
            self.create()
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail, "Payer user not found.")
        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_payer_outside_group_is_rejected_before_writing(self):
        self.db.scalars.return_value = [2, 3]
        with self.assertRaises(HTTPException) as caught:
            self.create()
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail, "Payer must be a member of this group.")
        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_split_save_failure_rolls_back_the_expense(self):
        def fail_on_second_share(record):
            if isinstance(record, ExpenseSplit) and record.user_id == 2:
                raise SQLAlchemyError("Simulated split save failure")
            self.added.append(record)

        self.db.add.side_effect = fail_on_second_share
        with self.assertRaises(SQLAlchemyError):
            self.create()
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()
        self.db.refresh.assert_not_called()

    def test_commit_failure_rolls_back(self):
        self.db.commit.side_effect = SQLAlchemyError("Simulated commit failure")
        with self.assertRaises(SQLAlchemyError):
            self.create()
        self.db.rollback.assert_called_once()
        self.db.refresh.assert_not_called()


class SettlementSuggestionTests(unittest.TestCase):
    def setUp(self):
        guard = patch("sqlalchemy.engine.Engine.connect", side_effect=AssertionError("Unit test attempted a database connection"))
        guard.start()
        self.addCleanup(guard.stop)
        self.db = MagicMock(spec=Session)
        self.db.get.return_value = Group(id=1, name="Trip", created_by=1)
        self.db.scalars.return_value.all.return_value = [
            User(id=1, name="saikumar"), User(id=2, name="mohit"), User(id=3, name="rahul"),
        ]

    def test_returns_payment_counts_and_names_for_an_improved_plan(self):
        self.db.execute.return_value = [
            (1, 2, Decimal("600.00")), (2, 1, Decimal("250.00")),
            (3, 1, Decimal("500.00")), (3, 2, Decimal("500.00")),
        ]
        result = get_settlement_suggestions(group_id=1, db=self.db)
        self.assertEqual(result.original_payment_count, 3)
        self.assertEqual(result.suggested_payment_count, 2)
        self.assertEqual(result.payments_saved, 1)
        self.assertEqual(result.suggestions["saikumar"].pay, {"rahul": Decimal("150.00")})
        self.assertEqual(result.suggestions["mohit"].pay, {"rahul": Decimal("850.00")})
        self.assertEqual(result.suggestions["rahul"].pay, {})
        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_same_payment_count_returns_no_meaningful_suggestions(self):
        self.db.execute.return_value = [(1, 2, Decimal("400.00")), (1, 3, Decimal("400.00"))]
        result = get_settlement_suggestions(group_id=1, db=self.db)
        self.assertIsInstance(result, SettlementMessageResponse)
        self.assertEqual(result.message, "No meaningful settlement suggestions found.")

    def test_higher_payment_count_returns_no_meaningful_suggestions(self):
        self.db.scalars.return_value.all.return_value = [User(id=i, name=f"User {i}") for i in range(1, 7)]
        # These four debts produce a five-payment greedy candidate.
        self.db.execute.return_value = [
            (5, 1, Decimal("8.00")), (4, 2, Decimal("7.00")),
            (6, 3, Decimal("4.00")), (4, 3, Decimal("2.00")),
        ]
        result = get_settlement_suggestions(group_id=1, db=self.db)
        self.assertIsInstance(result, SettlementMessageResponse)
        self.assertEqual(result.message, "No meaningful settlement suggestions found.")

    def test_no_expenses_returns_no_meaningful_suggestions(self):
        self.db.execute.return_value = []
        result = get_settlement_suggestions(group_id=1, db=self.db)
        self.assertIsInstance(result, SettlementMessageResponse)
        self.assertEqual(result.message, "No meaningful settlement suggestions found.")

    def test_circular_debts_with_zero_net_positions_need_no_payments(self):
        self.db.execute.return_value = [
            (1, 2, Decimal("10.00")), (2, 3, Decimal("10.00")), (3, 1, Decimal("10.00")),
        ]
        result = get_settlement_suggestions(group_id=1, db=self.db)
        self.assertEqual(result.original_payment_count, 3)
        self.assertEqual(result.suggested_payment_count, 0)
        self.assertEqual(result.payments_saved, 3)
        self.assertTrue(all(not member.pay for member in result.suggestions.values()))

    def test_missing_group_returns_404(self):
        self.db.get.return_value = None
        with self.assertRaises(HTTPException) as caught:
            get_settlement_suggestions(group_id=1, db=self.db)
        self.assertEqual(caught.exception.status_code, 404)
        self.db.execute.assert_not_called()
