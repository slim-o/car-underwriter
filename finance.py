from decimal import Decimal, ROUND_HALF_UP

D = lambda value: Decimal(str(value))
PENNY = D("0.01")

# Exclusive upper bound, buyer fee.
BUYER_B = [
    (50, 20), (100, 65), (200, 85), (300, 105),
    (350, 115), (400, 125), (450, 135), (500, 140),
    (550, 145), (600, 150), (700, 165), (800, 180),
    (900, 195), (1000, 210), (1200, 225), (1300, 245),
    (1400, 255), (1500, 265), (1600, 275), (1700, 285),
    (1800, 300), (2000, 310), (2400, 340), (2500, 365),
    (3000, 390), (3500, 425), (4000, 465), (4500, 510),
    (5000, 535), (6000, 555), (7500, 565), (10000, 590),
]

LIVE = [
    (100, 0), (500, 35), (1000, 49), (1500, 69),
    (2000, 79), (4000, 89), (6000, 99),
    (8000, 105),
]


def money(value):
    return D(value).quantize(PENNY, rounding=ROUND_HALF_UP)


def nonnegative(value, name):
    value = D(value)
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return value


def copart_fees(hammer, method="live", vat_rate="0.20"):
    hammer = nonnegative(hammer, "hammer")
    vat_rate = nonnegative(vat_rate, "fee VAT")
    if method not in {"live", "preliminary"}:
        raise ValueError("Unsupported bidding method")

    # Zero here means no purchase, not a purchased £0 vehicle.
    if hammer == 0:
        return D(0)

    buyer = next(
        (D(fee) for limit, fee in BUYER_B if hammer < D(limit)),
        money(hammer * D("0.065")),
    )

    bidding = next(
        (D(fee) for limit, fee in LIVE if hammer < D(limit)),
        D(109),
    )

    if method == "preliminary" and hammer >= 100:
        bidding -= 10

    retrieval = D(50)
    fees_ex_vat = buyer + bidding + retrieval
    return money(fees_ex_vat + money(fees_ex_vat * vat_rate))


def investment(
    hammer,
    fixed_costs,
    method="live",
    hammer_vat_rate="0",
    fee_vat_rate="0.20",
):
    hammer = nonnegative(hammer, "hammer")
    fixed_costs = nonnegative(fixed_costs, "fixed costs")
    hammer_vat_rate = nonnegative(hammer_vat_rate, "hammer VAT")

    return money(
        hammer
        + money(hammer * hammer_vat_rate)
        + copart_fees(hammer, method, fee_vat_rate)
        + fixed_costs
    )


def ceiling(
    net_exit,
    fixed_costs,
    capital_limit,
    target_roi="0.20",
    rounding_step=25,
    method="live",
    hammer_vat_rate="0",
    fee_vat_rate="0.20",
):
    net_exit = nonnegative(net_exit, "net exit")
    capital_limit = nonnegative(capital_limit, "capital limit")
    target_roi = nonnegative(target_roi, "ROI")
    fixed_costs = nonnegative(fixed_costs, "fixed costs")

    if rounding_step < 1 or int(rounding_step) != rounding_step:
        raise ValueError("Rounding step must be a positive whole pound")

    limit = min(capital_limit, net_exit / (1 + target_roi))
    best = None

    # Conservative rounding grid, NOT a claim about Copart's bid ladder.
    # Verify the actual permitted auction increment before bidding.
    for hammer in range(rounding_step, int(limit) + 1, rounding_step):
        total = investment(
            hammer, fixed_costs, method,
            hammer_vat_rate, fee_vat_rate,
        )
        if total > limit:
            break
        best = hammer

    return {
        "maximum_total_investment": float(limit),
        "provisional_hammer_ceiling": best,
        "rounding_step": rounding_step,
    }


def performance(net_exit, total):
    net_exit = D(net_exit)
    total = D(total)
    profit = money(net_exit - total)
    return {
        "investment": float(total),
        "profit": float(profit),
        "roi_percent": float(profit / total * 100) if total > 0 else None,
    }


def self_test():
    assert copart_fees(1000) == D("412.80")
    assert copart_fees(1000, "preliminary") == D("400.80")
    assert copart_fees(3600) == D("724.80")
    assert copart_fees(5800) == D("844.80")
    assert copart_fees(6000) == D("864.00")
    assert copart_fees(10000) == D("970.80")

    assert investment(1000, 2525) == D("3937.80")
    assert investment(1000, 0, hammer_vat_rate=".20") == D("1612.80")

    result = ceiling(4790, 2525, 5000)
    assert result["provisional_hammer_ceiling"] == 1050

    assert ceiling(4000, 4000, 5000)["provisional_hammer_ceiling"] is None

    print("Financial self-tests passed.")


if __name__ == "__main__":
    self_test()