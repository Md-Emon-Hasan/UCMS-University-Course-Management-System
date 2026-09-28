"""
Shared schema pieces: the strict base model, reusable field types, and money helpers.

MONEY RULE
    The database stores money as INTEGER paisa (1500.50 taka -> 150050).
    - Requests send taka as a decimal number, e.g. {"amount": 1500.50}.
      taka_to_paisa() turns it into an integer before it touches the database.
    - Responses return BOTH: the raw integer (e.g. "amount": 150050), which the
      frontend formats with formatMoney(paisa), and a decimal text
      "amount_taka": "1500.50" made here in the API layer.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------
class StrictModel(BaseModel):
    """
    Base for all request bodies.
    extra="forbid" -> unknown fields are rejected (a typo like "capcity" gives 422).
    str_strip_whitespace -> "  CSE " becomes "CSE".
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Reusable field types. The Literal lists match the CHECK constraints in
# sql/01_tables.sql, so bad values are stopped here BEFORE reaching the database.
# ---------------------------------------------------------------------------
Role = Literal["admin", "teacher", "student", "accountant"]
TimeText = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["09:30"])]
Name = Annotated[str, Field(min_length=1, max_length=80)]
Phone = Annotated[str, Field(pattern=r"^\+?[0-9]{7,15}$", examples=["01712345678"])]
Password = Annotated[str, Field(min_length=8, max_length=128)]

# Taka amounts: at most 2 decimal places, as in real money
Taka = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, examples=[1500.50])]
PositiveTaka = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2, examples=[1500.50])]


# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------
def taka_to_paisa(taka: Decimal | int | float | str) -> int:
    """1500.50 taka -> 150050 paisa. Decimal avoids float surprises like 0.1 + 0.2."""
    amount = Decimal(str(taka)) * 100
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paisa_to_taka(paisa: int | None) -> str | None:
    """150050 paisa -> "1500.50" (text, so no float rounding can creep in)."""
    if paisa is None:
        return None
    return f"{Decimal(paisa) / 100:.2f}"


def add_taka_fields(row: dict, *money_fields: str) -> dict:
    """For each money field X in the row, add X_taka with the decimal text. Returns the same dict."""
    for field in money_fields:
        if field in row:
            row[f"{field}_taka"] = paisa_to_taka(row[field])
    return row
