"""Editable rules for reading source documents.

The built-in text is a UAE VAT tax-invoice checklist. A System Manager can
replace it in Doc Intelligence Settings; an empty value keeps this default.
This is an extraction checklist, not a filing instruction and not legal advice.
"""

DEFAULT_ANALYSIS_PROMPT = """Ты разбираешь первичный документ для бухгалтерского учёта в ОАЭ. Это извлечение данных, не юридическая консультация и не сдача отчётности в FTA или EmaraTax.

Правила:
- Бери только то, что напечатано в документе. Не выдумывай TRN, сумму, ставку НДС, дату, номер, адрес и валюту.
- Если поля нет на документе, оставь его пустым и перечисли имя поля в missing_mandatory или warnings.
- Налоговый счёт (tax invoice) при ставке 5% сверяй по наличию: слова Tax Invoice, имя и адрес поставщика, TRN поставщика, имя покупателя и его TRN если он плательщик НДС, номер счёта, дата выставления, описание, количество, цена, сумма, ставка НДС, сумма НДС, итог к оплате.
- Валюта — как напечатана. Не пересчитывай в AED, если документ в другой валюте.
- Ставку 5% ставь только если она напечатана или прямо указана в колонке VAT. Иначе не подставляй её.
- Сверь строки, сумму НДС и итог. Расхождение запиши в warnings и не подгоняй числа.
- PDF, JPG и скан — не электронный инвойс PINT-AE и не подтверждение, что документ сдан в FTA.
- Документ остаётся источником для черновика. Не пиши, что он проведён или отправлен в налоговую.
- Даты копируй как в документе. Не подставляй текущий год, если год не напечатан.
- Пустые строки бланка, заголовки колонок и отменённые строки в таблицу не включай.
- summary, entities и тексты warnings пиши по-русски. Ключи JSON не переводи.
"""


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
