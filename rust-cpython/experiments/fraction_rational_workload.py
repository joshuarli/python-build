"""Reduce a deterministic rational ledger through public Fraction parsing."""

import argparse
from fractions import Fraction
import hashlib
import json


def run(count: int, rounds: int) -> dict[str, object]:
    rows = []
    for index in range(count):
        numerator = (index * 7919) % 100003 - 50000
        denominator = (index * 37) % 997 + 1
        canonical = f"{numerator}/{denominator}"
        kind = index % 20
        if kind == 0:
            amount = f" {canonical} "
        elif kind == 1:
            amount = f"{numerator / denominator:.6f}"
        elif kind == 2:
            amount = f"{numerator:,}".replace(",", "_") + f"/{denominator}"
        elif kind == 3:
            amount = str(numerator)
        else:
            amount = canonical
        rows.append((index % 16, amount))

    totals = [Fraction(0) for _ in range(16)]
    counts = [0] * 16
    for _ in range(rounds):
        for account, amount in rows:
            totals[account] += Fraction(amount)
            counts[account] += 1

    rendered = [(account, counts[account], str(total),
                 format(total, ".6f")) for account, total in enumerate(totals)]
    payload = json.dumps(rendered, separators=(",", ":")).encode()
    return {"count": count, "rounds": rounds, "records": count * rounds,
            "canonical_records": (count - 4 * (count // 20)) * rounds,
            "accounts": len(rendered), "digest": hashlib.sha256(payload).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20000)
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(run(args.count, args.rounds), sort_keys=True))
