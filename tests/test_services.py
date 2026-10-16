from decimal import Decimal
import unittest

from services import (
    calculate_balances,
    calculate_equal_shares,
    calculate_net_balances,
    suggest_settlements,
)


class EqualShareTests(unittest.TestCase):
    def test_divisible_amount_is_shared_equally(self):
        self.assertEqual(
            calculate_equal_shares(Decimal("1200.00"), [1, 2, 3]),
            {1: Decimal("400.00"), 2: Decimal("400.00"), 3: Decimal("400.00")},
        )

    def test_extra_paise_go_to_lowest_user_ids(self):
        self.assertEqual(
            calculate_equal_shares(Decimal("100.00"), [30, 10, 20]),
            {10: Decimal("33.34"), 20: Decimal("33.33"), 30: Decimal("33.33")},
        )

    def test_small_amount_can_leave_zero_shares(self):
        self.assertEqual(
            calculate_equal_shares(Decimal("0.02"), [1, 2, 3]),
            {1: Decimal("0.01"), 2: Decimal("0.01"), 3: Decimal("0.00")},
        )

    def test_one_member_receives_the_full_share(self):
        self.assertEqual(
            calculate_equal_shares(Decimal("123.45"), [7]),
            {7: Decimal("123.45")},
        )

    def test_cannot_split_without_members(self):
        with self.assertRaises(ValueError):
            calculate_equal_shares(Decimal("100.00"), [])

    def test_shares_preserve_total_and_differ_by_at_most_one_paisa(self):
        for amount in ("0.01", "0.05", "10.01", "100.00", "9999999999.99"):
            for member_count in (1, 2, 3, 7, 20):
                with self.subTest(amount=amount, member_count=member_count):
                    shares = calculate_equal_shares(
                        Decimal(amount), list(range(1, member_count + 1))
                    )
                    self.assertEqual(sum(shares.values()), Decimal(amount))
                    self.assertGreaterEqual(min(shares.values()), Decimal("0.00"))
                    self.assertLessEqual(
                        max(shares.values()) - min(shares.values()), Decimal("0.01")
                    )


class BalanceTests(unittest.TestCase):
    def test_empty_history_has_no_debts(self):
        self.assertEqual(calculate_balances([]), {})

    def test_payer_does_not_owe_themselves(self):
        self.assertEqual(calculate_balances([(1, 1, Decimal("400.00"))]), {})

    def test_repeated_expenses_add_to_the_same_debt(self):
        self.assertEqual(
            calculate_balances([(1, 2, Decimal("400.00")), (1, 2, Decimal("100.00"))]),
            {(2, 1): Decimal("500.00")},
        )

    def test_opposite_debts_are_offset(self):
        self.assertEqual(
            calculate_balances([(1, 2, Decimal("600.00")), (2, 1, Decimal("250.00"))]),
            {(2, 1): Decimal("350.00")},
        )

    def test_equal_opposite_debts_cancel(self):
        self.assertEqual(
            calculate_balances([(1, 2, Decimal("400.00")), (2, 1, Decimal("400.00"))]),
            {},
        )

    def test_larger_reverse_debt_changes_who_owes_whom(self):
        self.assertEqual(
            calculate_balances([(1, 2, Decimal("100.00")), (2, 1, Decimal("250.00"))]),
            {(1, 2): Decimal("150.00")},
        )

    def test_new_member_only_shares_later_expenses(self):
        rows = [
            (1, 1, Decimal("600.00")), (1, 2, Decimal("600.00")),
            (2, 1, Decimal("250.00")), (2, 2, Decimal("250.00")),
            (3, 1, Decimal("500.00")), (3, 2, Decimal("500.00")),
            (3, 3, Decimal("500.00")),
        ]
        self.assertEqual(
            calculate_balances(rows),
            {(2, 1): Decimal("350.00"), (1, 3): Decimal("500.00"), (2, 3): Decimal("500.00")},
        )


class NetBalanceTests(unittest.TestCase):
    def test_net_positions_preserve_total_and_include_inactive_members(self):
        pairs = {(2, 1): Decimal("350.00"), (1, 3): Decimal("500.00"), (2, 3): Decimal("500.00")}
        net = calculate_net_balances(pairs, [1, 2, 3, 4])
        self.assertEqual(net, {
            1: Decimal("-150.00"), 2: Decimal("-850.00"),
            3: Decimal("1000.00"), 4: Decimal("0.00"),
        })
        self.assertEqual(sum(net.values()), Decimal("0.00"))

    def test_no_debts_gives_every_member_zero_balance(self):
        self.assertEqual(
            calculate_net_balances({}, [1, 2]),
            {1: Decimal("0.00"), 2: Decimal("0.00")},
        )


class SettlementTests(unittest.TestCase):
    def test_worked_example_reduces_three_payments_to_two(self):
        self.assertEqual(
            suggest_settlements({1: Decimal("-150.00"), 2: Decimal("-850.00"), 3: Decimal("1000.00")}),
            {(2, 3): Decimal("850.00"), (1, 3): Decimal("150.00")},
        )

    def test_zero_or_empty_balances_need_no_payments(self):
        for balances in ({}, {1: Decimal("0.00"), 2: Decimal("0.00")}):
            with self.subTest(balances=balances):
                self.assertEqual(suggest_settlements(balances), {})

    def test_rejects_net_balances_that_do_not_sum_to_zero(self):
        with self.assertRaises(ValueError):
            suggest_settlements({1: Decimal("-10.00"), 2: Decimal("9.00")})

    def test_equal_balances_use_user_id_to_break_ties(self):
        self.assertEqual(
            suggest_settlements({4: Decimal("10.00"), 2: Decimal("-10.00"), 3: Decimal("10.00"), 1: Decimal("-10.00")}),
            {(1, 3): Decimal("10.00"), (2, 4): Decimal("10.00")},
        )

    def test_suggestions_clear_each_members_net_balance(self):
        cases = [
            {1: "-0.01", 2: "0.01"},
            {1: "-100.00", 2: "60.00", 3: "40.00"},
            {1: "-8.00", 2: "-7.00", 3: "-6.00", 4: "9.00", 5: "8.00", 6: "4.00"},
        ]
        for case in cases:
            with self.subTest(case=case):
                original = {user_id: Decimal(amount) for user_id, amount in case.items()}
                remaining = original.copy()
                for (debtor, creditor), amount in suggest_settlements(original).items():
                    self.assertGreater(amount, 0)
                    self.assertLess(original[debtor], 0)
                    self.assertGreater(original[creditor], 0)
                    remaining[debtor] += amount
                    remaining[creditor] -= amount
                self.assertTrue(all(amount == 0 for amount in remaining.values()))
                self.assertEqual(original, {user_id: Decimal(amount) for user_id, amount in case.items()})
