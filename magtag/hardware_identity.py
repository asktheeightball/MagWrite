"""Recorded physical-hardware identity decision.

Keep this value synchronized with docs/HARDWARE_IDENTITY_REPORT.md.
"""

VALID_DECISIONS = ("COMPATIBLE", "INCOMPATIBLE", "UNCONFIRMED")
DECISION = "COMPATIBLE"


def parse_decision(value):
    decision = value.strip().upper()
    if decision not in VALID_DECISIONS:
        raise ValueError("invalid hardware compatibility decision")
    return decision
