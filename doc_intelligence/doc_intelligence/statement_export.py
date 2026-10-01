"""Normalize AI-extracted bank statement rows and render import-ready CSV."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


SUPPORTED_TARGETS = ("zoho_books", "quickbooks", "nexterp")


def _decimal(value):
    if value in (None, ""):
        return Decimal("0")
    text = str(value).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[^\d,.\-]", "", text.strip("()"))
    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        if text.count(",") > 1 or re.search(r",\d{3}$", text):
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        amount = Decimal(text or "0")
    except InvalidOperation:
        return Decimal("0")
    return -amount if negative else amount


def _date(value):
    text = str(value or "").strip()
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%m/%d/%y",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def _money(value):
    amount = _decimal(value)
    return "" if amount == 0 else f"{abs(amount):.2f}"


def normalize_transactions(rows):
    """Return a predictable, JSON-safe representation of statement rows."""
    normalized = []
    for index, row in enumerate(rows or [], start=1):
        if not isinstance(row, dict):
            continue
        debit = abs(_decimal(row.get("debit")))
        credit = abs(_decimal(row.get("credit")))
        amount = _decimal(row.get("amount"))
        direction = str(row.get("direction") or row.get("type") or "").lower()
        if not debit and not credit and amount:
            if amount < 0 or direction in {"debit", "withdrawal", "out", "payment"}:
                debit = abs(amount)
            else:
                credit = abs(amount)

        normalized.append(
            {
                "date": _date(row.get("date")),
                "description": " ".join(str(row.get("description") or "").split()),
                "reference": str(
                    row.get("reference") or row.get("transaction_id") or ""
                ).strip(),
                "debit": float(debit),
                "credit": float(credit),
                "balance": (
                    float(_decimal(row.get("balance")))
                    if row.get("balance") not in (None, "")
                    else None
                ),
                "row_number": index,
            }
        )
    return normalized


def validate_statement(rows, opening_balance=None, closing_balance=None):
    transactions = normalize_transactions(rows)
    warnings = []
    previous_balance = (
        _decimal(opening_balance) if opening_balance not in (None, "") else None
    )

    for row in transactions:
        label = f"Row {row['row_number']}"
        if not row["date"]:
            warnings.append(f"{label}: date is missing.")
        if not row["description"]:
            warnings.append(f"{label}: description is missing.")
        if bool(row["debit"]) == bool(row["credit"]):
            warnings.append(f"{label}: exactly one of debit or credit must have a value.")

        balance = (
            Decimal(str(row["balance"])) if row["balance"] is not None else None
        )
        if previous_balance is not None and balance is not None:
            expected = (
                previous_balance
                + Decimal(str(row["credit"]))
                - Decimal(str(row["debit"]))
            )
            if abs(expected - balance) > Decimal("0.02"):
                warnings.append(
                    f"{label}: running balance differs by {abs(expected - balance):.2f}."
                )
        if balance is not None:
            previous_balance = balance

    if (
        closing_balance not in (None, "")
        and previous_balance is not None
        and abs(previous_balance - _decimal(closing_balance)) > Decimal("0.02")
    ):
        warnings.append("The final row balance does not match the closing balance.")

    return {
        "transactions": transactions,
        "row_count": len(transactions),
        "warnings": warnings,
        "is_valid": bool(transactions) and not warnings,
    }


def render_statement_csv(rows, target, currency=""):
    """Render one of the supported bank-import layouts."""
    if target not in SUPPORTED_TARGETS:
        raise ValueError(f"Unsupported CSV target: {target}")

    transactions = normalize_transactions(rows)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")

    if target == "quickbooks":
        writer.writerow(["Date", "Description", "Amount"])
        for row in transactions:
            amount = Decimal(str(row["credit"])) - Decimal(str(row["debit"]))
            writer.writerow(
                [
                    _display_date(row["date"]),
                    row["description"],
                    f"{amount:.2f}" if amount else "",
                ]
            )
    elif target == "zoho_books":
        writer.writerow(
            ["Date", "Description", "Reference Number", "Withdrawals", "Deposits"]
        )
        for row in transactions:
            writer.writerow(
                [
                    _display_date(row["date"]),
                    row["description"],
                    row["reference"],
                    _money(row["debit"]),
                    _money(row["credit"]),
                ]
            )
    else:
        writer.writerow(
            [
                "Date",
                "Description",
                "Deposit",
                "Withdrawal",
                "Reference Number",
                "Currency",
                "Balance",
            ]
        )
        for row in transactions:
            writer.writerow(
                [
                    row["date"],
                    row["description"],
                    _money(row["credit"]),
                    _money(row["debit"]),
                    row["reference"],
                    currency or "",
                    "" if row["balance"] is None else f"{row['balance']:.2f}",
                ]
            )

    # UTF-8 BOM makes Cyrillic/Arabic descriptions open correctly in Excel.
    return "\ufeff" + output.getvalue()


def _display_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return value
