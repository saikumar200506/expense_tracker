from decimal import Decimal


def calculate_equal_shares(
    amount: Decimal,
    member_ids: list[int],
) -> dict[int, Decimal]:
    member_ids = sorted(member_ids)

    if not member_ids:
        raise ValueError("At least one member is required.")

    total_paise = int(amount * 100)
    base_share, remaining_paise = divmod(
        total_paise, len(member_ids)
    )

    shares = {}

    for position, user_id in enumerate(member_ids):
        share_paise = base_share

        if position < remaining_paise:
            share_paise += 1

        shares[user_id] = (
            Decimal(share_paise) / Decimal("100")
        ).quantize(Decimal("0.01"))

    return shares

def calculate_balances(
    expense_shares: list[tuple[int, int, Decimal]],
) -> dict[tuple[int, int], Decimal]:
    balances = {}
    zero = Decimal("0.00")

    for payer_id, member_id, share_amount in expense_shares:
        if payer_id == member_id:
            continue

        debt = (member_id, payer_id)
        reverse = (payer_id, member_id)

        balances[debt] = balances.get(debt, zero) + share_amount
        balances[reverse] = balances.get(reverse, zero) - share_amount

    return {
        pair: amount
        for pair, amount in balances.items()
        if amount > zero
    }

def calculate_net_balances(
    pair_balances: dict[tuple[int, int], Decimal],
    member_ids: list[int],
) -> dict[int, Decimal]:
    net_balances = {
        user_id: Decimal("0.00")
        for user_id in member_ids
    }

    for (debtor_id, creditor_id), amount in pair_balances.items():
        net_balances[debtor_id] -= amount
        net_balances[creditor_id] += amount

    return net_balances

def suggest_settlements(
    net_balances: dict[int, Decimal],
) -> dict[tuple[int, int], Decimal]:
    zero = Decimal("0.00")

    if sum(net_balances.values(), zero) != zero:
        raise ValueError("Net balances must sum to zero.")

    debtors = {
        user_id: -amount
        for user_id, amount in sorted(net_balances.items())
        if amount < zero
    }

    creditors = {
        user_id: amount
        for user_id, amount in sorted(net_balances.items())
        if amount > zero
    }

    suggestions = {}

    while debtors and creditors:
        debtor_id = max(debtors, key=lambda user_id: debtors[user_id])
        creditor_id = max(creditors, key=lambda user_id: creditors[user_id])

        amount = min(
            debtors[debtor_id],
            creditors[creditor_id],
        )

        suggestions[(debtor_id, creditor_id)] = amount

        debtors[debtor_id] -= amount
        creditors[creditor_id] -= amount

        if debtors[debtor_id] == zero:
            del debtors[debtor_id]

        if creditors[creditor_id] == zero:
            del creditors[creditor_id]

    return suggestions