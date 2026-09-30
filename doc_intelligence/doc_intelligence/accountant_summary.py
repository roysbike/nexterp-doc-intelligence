"""Plain-language brief for a bookkeeper.

The model copies printed figures. This module counts lines and checks the
arithmetic, so a warning never calls a large gap a rounding error.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


_FIELDS = (
    ("document_kind", "Document title (Tax Invoice or other)", "Название документа (Tax Invoice или иное)"),
    ("supplier_name", "Supplier name", "Название поставщика"),
    ("supplier_address", "Supplier address", "Адрес поставщика"),
    ("supplier_trn", "Supplier TRN", "TRN поставщика"),
    ("buyer_name", "Buyer name", "Название покупателя"),
    ("buyer_trn", "Buyer TRN", "TRN покупателя"),
    ("invoice_number", "Invoice number", "Номер счёта"),
    ("invoice_date", "Invoice date", "Дата счёта"),
    ("currency", "Currency printed on the document", "Валюта, напечатанная на документе"),
    ("vat_rate_stated", "VAT rate", "Ставка НДС"),
    ("taxable_amount", "Net amount", "Сумма нетто"),
    ("vat_amount", "VAT amount", "Сумма НДС"),
    ("grand_total", "Amount due", "Сумма к оплате"),
)


def accountant_summary(accounting, language="en", model_summary=""):
    """Return the text stored as the document summary."""
    if not isinstance(accounting, dict):
        return _clean_model_text(model_summary)
    ru = language == "ru"
    lines = _charge_lines(accounting)
    parts = []
    lead = _clean_model_text(model_summary)
    if lead:
        parts.append(lead)
    parts.append(_headline(accounting, lines, ru))
    parts.append(_checklist(accounting, lines, ru))
    check = _arithmetic(accounting, lines, ru)
    if check:
        parts.append(check)
    return "\n\n".join(part for part in parts if part)


def replace_arithmetic_warnings(accounting, language="en"):
    """Drop the model's arithmetic sentence and keep the computed check."""
    if not isinstance(accounting, dict):
        return accounting
    kept = []
    for item in accounting.get("warnings") or []:
        text = str(item or "").strip()
        if text and not _looks_like_arithmetic(text):
            kept.append(text)
    note = _arithmetic(accounting, _charge_lines(accounting), language == "ru")
    if note:
        kept.append(note)
    accounting = dict(accounting)
    accounting["warnings"] = kept
    return accounting


def _headline(accounting, lines, ru):
    kind = _text(accounting.get("document_kind")) or ("Документ" if ru else "Document")
    supplier = _text(accounting.get("supplier_name"))
    buyer = _text(accounting.get("buyer_name"))
    number = _text(accounting.get("invoice_number"))
    date = _text(accounting.get("invoice_date"))
    currency = _text(accounting.get("currency"))
    count = len(lines)
    if ru:
        who = ""
        if supplier and buyer:
            who = f"Поставщик: {supplier}. Покупатель: {buyer}."
        elif supplier:
            who = f"Поставщик: {supplier}."
        elif buyer:
            who = f"Покупатель: {buyer}."
        ref = ""
        if number or date:
            ref = "Номер и дата: " + ", ".join(bit for bit in (number, date) if bit) + "."
        money = _printed_totals_sentence(accounting, currency, ru)
        return "\n".join(bit for bit in (
            f"{kind}. Распознано позиций: {count}. Это один документ, в нём {_ru_lines(count)} к проводке.",
            who,
            ref,
            money,
        ) if bit)
    who = ""
    if supplier and buyer:
        who = f"Supplier: {supplier}. Buyer: {buyer}."
    elif supplier:
        who = f"Supplier: {supplier}."
    elif buyer:
        who = f"Buyer: {buyer}."
    ref = ""
    if number or date:
        ref = "Number and date: " + ", ".join(bit for bit in (number, date) if bit) + "."
    money = _printed_totals_sentence(accounting, currency, ru)
    return "\n".join(bit for bit in (
        f"{kind}. Lines recognised: {count}. This is one document with {count} line{'' if count == 1 else 's'} to post.",
        who,
        ref,
        money,
    ) if bit)


def _printed_totals_sentence(accounting, currency, ru):
    net = _money(accounting.get("taxable_amount"))
    vat = _money(accounting.get("vat_amount"))
    total = _money(accounting.get("grand_total"))
    if net is None and vat is None and total is None:
        return ""
    unit = f" {currency}" if currency else ""
    bits = []
    if net is not None:
        bits.append(("нетто", "net", net))
    if vat is not None:
        bits.append(("НДС", "VAT", vat))
    if total is not None:
        bits.append(("к оплате", "amount due", total))
    shown = ", ".join(f"{ru_label if ru else en_label} {_fmt(amount)}{unit}" for ru_label, en_label, amount in bits)
    if ru:
        return "На бланке напечатано: " + shown + "."
    return "Printed on the form: " + shown + "."


def _checklist(accounting, lines, ru):
    title = "Что обычно нужно бухгалтеру и что распознано:" if ru else "What a bookkeeper usually needs, and what was read:"
    rows = [title]
    for key, en, rus in _FIELDS:
        label = rus if ru else en
        value = accounting.get(key)
        if _present(value):
            rows.append(f"- {label}: {_short(value)}")
        else:
            rows.append(f"- {label}: " + ("нет на документе" if ru else "not printed"))
    if lines:
        rows.append(
            f"- {'Строки (описание, количество, цена, сумма)' if ru else 'Lines (description, quantity, price, amount)'}: {len(lines)}"
        )
    else:
        rows.append("- " + ("Строки: не распознаны" if ru else "Lines: none recognised"))
    missing = [str(item).strip() for item in (accounting.get("missing_mandatory") or []) if str(item).strip()]
    if missing:
        rows.append(("Ещё не найдено: " if ru else "Also missing: ") + "; ".join(missing))
    return "\n".join(rows)


def _arithmetic(accounting, lines, ru):
    net = _money(accounting.get("taxable_amount"))
    vat = _money(accounting.get("vat_amount"))
    total = _money(accounting.get("grand_total"))
    paragraphs = []
    if net is not None and vat is not None and total is not None:
        added = net + vat
        gap = total - added
        paragraphs.append(_cross_foot(net, vat, total, added, gap, ru))
        rate_note = _vat_rate_note(accounting, net, vat, total, ru)
        if rate_note:
            paragraphs.append(rate_note)
    line_note = _line_sum_note(lines, net, vat, total, ru)
    if line_note:
        paragraphs.append(line_note)
    if not paragraphs:
        return ""
    title = "Проверка сумм. Цифры не исправлялись:" if ru else "Amount check. Figures were not changed:"
    return title + "\n" + "\n".join(paragraphs)


def _cross_foot(net, vat, total, added, gap, ru):
    if gap == 0:
        if ru:
            return f"{_fmt(net)} + {_fmt(vat)} = {_fmt(total)}. Сходится с напечатанным итогом."
        return f"{_fmt(net)} + {_fmt(vat)} = {_fmt(total)}. It matches the printed total."
    if gap.copy_abs() <= Decimal("0.05"):
        if ru:
            return (
                f"{_fmt(net)} + {_fmt(vat)} = {_fmt(added)}. "
                f"Напечатанный итог {_fmt(total)}. Разница {_fmt(gap)}. "
                "Это филисы округления, не ошибка распознавания."
            )
        return (
            f"{_fmt(net)} + {_fmt(vat)} = {_fmt(added)}. "
            f"Printed total {_fmt(total)}. Difference {_fmt(gap)}. "
            "This is fils from rounding, not a reading error."
        )
    if ru:
        return (
            f"{_fmt(net)} + {_fmt(vat)} = {_fmt(added)}. "
            f"Напечатанный итог {_fmt(total)}. "
            f"Разница {_fmt(gap)}: колонки на бланке не сходятся. "
            "Это не погрешность округления."
        )
    return (
        f"{_fmt(net)} + {_fmt(vat)} = {_fmt(added)}. "
        f"Printed total {_fmt(total)}. "
        f"Difference {_fmt(gap)}: the columns on the form do not add up. "
        "This is not a rounding error."
    )


def _vat_rate_note(accounting, net, vat, total, ru):
    implied_net = (total - vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    bits = []
    if _stated_rate_is_five(accounting):
        five = (net * Decimal("0.05")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if (vat - five).copy_abs() > Decimal("0.05"):
            if ru:
                bits.append(f"5% от нетто {_fmt(net)} = {_fmt(five)}, в колонке НДС стоит {_fmt(vat)}.")
            else:
                bits.append(f"5% of net {_fmt(net)} is {_fmt(five)}; the VAT column shows {_fmt(vat)}.")
    if (implied_net - net).copy_abs() > Decimal("0.05"):
        if ru:
            bits.append(
                f"Итог минус НДС = {_fmt(implied_net)}. "
                f"Эта база сходится с итогом и НДС, а напечатанное нетто {_fmt(net)} — нет."
            )
        else:
            bits.append(
                f"Total minus VAT is {_fmt(implied_net)}. "
                f"That base matches the total and the VAT; the printed net {_fmt(net)} does not."
            )
    return " ".join(bits)


def _line_sum_note(lines, net, vat, total, ru):
    amounts = [_money(row.get("amount")) for row in lines]
    vats = [_money(row.get("vat_amount")) for row in lines]
    amounts = [value for value in amounts if value is not None]
    vats = [value for value in vats if value is not None]
    if not amounts and not vats:
        return ""
    bits = []
    if amounts:
        summed = sum(amounts, Decimal("0.00"))
        if ru:
            bits.append(f"Сумма по {_ru_po_lines(len(amounts))}: {_fmt(summed)}.")
        else:
            bits.append(f"Sum of {len(amounts)} line amounts: {_fmt(summed)}.")
        if net is not None and (summed - net).copy_abs() <= Decimal("0.05"):
            bits.append("Совпадает с напечатанным нетто." if ru else "It matches the printed net.")
        elif total is not None and (summed - total).copy_abs() <= Decimal("0.05"):
            bits.append("Совпадает с напечатанным итогом." if ru else "It matches the printed total.")
        elif net is not None or total is not None:
            compared = []
            if net is not None:
                compared.append(("нетто", "net", net, summed - net))
            if total is not None:
                compared.append(("итогом", "total", total, summed - total))
            label_net, label_en, printed, gap = compared[0]
            if ru:
                bits.append(f"С напечатанным {label_net} {_fmt(printed)} не сходится, разница {_fmt(gap)}.")
            else:
                bits.append(f"It does not match the printed {label_en} {_fmt(printed)}; difference {_fmt(gap)}.")
    if vats:
        summed_vat = sum(vats, Decimal("0.00"))
        if ru:
            bits.append(f"Сумма НДС по строкам: {_fmt(summed_vat)}.")
        else:
            bits.append(f"Sum of line VAT: {_fmt(summed_vat)}.")
        if vat is not None and (summed_vat - vat).copy_abs() > Decimal("0.05"):
            if ru:
                bits.append(f"С напечатанным НДС {_fmt(vat)} не сходится, разница {_fmt(summed_vat - vat)}.")
            else:
                bits.append(f"It does not match the printed VAT {_fmt(vat)}; difference {_fmt(summed_vat - vat)}.")
    return " ".join(bits)


def _charge_lines(accounting):
    raw = []
    net = _money(accounting.get("taxable_amount"))
    vat = _money(accounting.get("vat_amount"))
    total = _money(accounting.get("grand_total"))
    for row in accounting.get("lines") or []:
        if not isinstance(row, dict):
            continue
        if not any(_present(row.get(key)) for key in ("description", "qty", "rate", "amount")):
            continue
        raw.append(row)
    kept = [row for row in raw if not _is_total_row(row, net, vat, total)]
    if not kept and len(raw) == 1:
        return raw
    return kept


def _is_total_row(row, net, vat, total):
    description = _text(row.get("description")).lower()
    if any(marker in description for marker in ("total", "итого", "subtotal", "amount due", "grand total")):
        return True
    amount = _money(row.get("amount"))
    row_vat = _money(row.get("vat_amount"))
    copies_header = False
    if amount is not None and row_vat is not None and vat is not None and row_vat == vat:
        if net is not None and amount == net:
            copies_header = True
        if total is not None and amount == total:
            copies_header = True
    return copies_header


def _stated_rate_is_five(accounting):
    text = _text(accounting.get("vat_rate_stated")).replace("%", "").replace(",", ".").strip()
    if not text:
        return False
    try:
        rate = Decimal(text)
    except InvalidOperation:
        return False
    return rate == Decimal("5") or rate == Decimal("0.05")


def _looks_like_arithmetic(text):
    low = text.lower()
    markers = (
        "погреш", "округл", "rounding", "net amount", "не дает", "не даёт",
        "does not equal", "doesn't equal", "do not add", "не сход", "математич",
    )
    return any(marker in low for marker in markers)


def _clean_model_text(value):
    text = _text(value)
    if not text:
        return ""
    kept = []
    for sentence in _sentences(text):
        if not _looks_like_arithmetic(sentence):
            kept.append(sentence)
    return " ".join(kept).strip()


def _sentences(text):
    restored = []
    for index, char in enumerate(text):
        if char != ".":
            restored.append(char)
            continue
        prev_digit = index > 0 and text[index - 1].isdigit()
        next_digit = index + 1 < len(text) and text[index + 1].isdigit()
        restored.append("§" if prev_digit and next_digit else ".")
    shielded = "".join(restored)
    chunk = []
    for char in shielded:
        chunk.append(char)
        if char in ".!?":
            piece = "".join(chunk).replace("§", ".").strip()
            if piece and not piece.replace(".", "").isdigit():
                yield piece
            chunk = []
    tail = "".join(chunk).replace("§", ".").strip()
    if tail and not tail.replace(".", "").isdigit():
        yield tail


def _ru_po_lines(count):
    number = abs(int(count))
    if number % 10 == 1 and number % 100 != 11:
        return f"{number} строке"
    return f"{number} строкам"


def _ru_lines(count):
    number = abs(int(count))
    if number % 10 == 1 and number % 100 != 11:
        word = "строка"
    elif number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        word = "строки"
    else:
        word = "строк"
    return f"{number} {word}"


def _present(value):
    if value is None:
        return False
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return bool(str(value).strip()) and str(value).strip().lower() not in {"null", "none", "n/a", "-"}


def _short(value):
    if isinstance(value, (list, tuple)):
        return str(len(value))
    text = _text(value)
    if len(text) > 180:
        return text[:177] + "…"
    return text


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def _money(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = str(value).strip().replace(" ", "").replace(",", "")
    if not text or text.lower() in {"null", "none", "n/a", "-"}:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _fmt(value):
    return f"{value:.2f}"
