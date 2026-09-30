"""Editable rules for reading source documents.

The built-in text is a UAE VAT tax-invoice checklist. A System Manager can
replace it in Doc Intelligence Settings; an empty value keeps this default.
This is an extraction checklist, not a filing instruction and not legal advice.
"""

DEFAULT_ANALYSIS_PROMPT = """Extract a source document for UAE bookkeeping. This is data extraction, not legal advice and not an FTA or EmaraTax filing.

Rules:
- Use only text printed on the document. Do not invent TRN, amount, VAT rate, date, number, address, or currency.
- If a field is missing, leave it empty and name it in missing_mandatory or warnings.
- For a 5% tax invoice, check: Tax Invoice, supplier name and address, supplier TRN, buyer name, buyer TRN if VAT-registered, invoice number, issue date, description, quantity, price, amount, VAT rate, VAT amount, amount due.
- Keep the printed currency. Do not convert it.
- Use 5% only when that rate is printed or shown in a VAT column.
- Check lines, VAT, and the total. Put a mismatch in warnings. Do not change the figures.
- A PDF, JPG, or scan is not a PINT-AE e-invoice and not proof of filing.
- The file is a source for a draft. Do not say it was submitted or filed.
- Copy dates as printed. Do not insert the current year.
- Skip blank template rows, column headers, and cancelled lines.
"""


def output_language(user=None):
    """Language chosen in the plugin. Missing choice stays English."""
    try:
        import frappe
        value = frappe.defaults.get_user_default("doc_intelligence_language", user or frappe.session.user)
    except Exception:
        value = None
    return "ru" if value == "ru" else "en"


def language_instruction(language):
    if language == "en":
        return (
            "Write summary, entities, answers, and warning texts in English. "
            "Do not translate JSON keys. This line overrides any earlier language instruction."
        )
    return (
        "summary, entities, ответы и тексты warnings пиши по-русски. "
        "Ключи JSON не переводи. Эта строка важнее более ранних указаний о языке."
    )


def get_analysis_prompt():
    """Return the saved prompt, or the built-in checklist when the field is empty."""
    default = DEFAULT_ANALYSIS_PROMPT.strip()
    try:
        import frappe
        settings = frappe.get_single("Doc Intelligence Settings")
        custom = (settings.get("analysis_prompt") or "").strip()
    except Exception:
        custom = ""
    return custom or default
