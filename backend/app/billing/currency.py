"""Currency utilities.

Canonical money unit everywhere in the backend is the Iranian Rial (IRR),
stored as an integer. The UI may display toman; every conversion goes through
this module — never inline arithmetic scattered across the codebase.
"""
from __future__ import annotations

IRR_PER_TOMAN = 10


def toman_to_irr(toman: int) -> int:
    """Convert whole toman to IRR. ``toman`` must be an int (no floats)."""
    if not isinstance(toman, int):
        raise TypeError("toman amount must be an integer")
    return toman * IRR_PER_TOMAN


def irr_to_toman(irr: int) -> int:
    """Convert IRR to whole toman, rounding half up (banker's display)."""
    if not isinstance(irr, int):
        raise TypeError("IRR amount must be an integer")
    # Half-up rounding for display purposes only; ledger keeps IRR.
    return (irr + IRR_PER_TOMAN // 2) // IRR_PER_TOMAN if irr >= 0 else -((-irr + IRR_PER_TOMAN // 2) // IRR_PER_TOMAN)


def format_irr(irr: int) -> str:
    return f"{irr:,}"
