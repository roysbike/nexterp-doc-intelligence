import frappe
from frappe.model.document import Document
import os, json


class AIDocument(Document):
    def before_save(self):
        if not self.title and self.file_attachment:
            self.title = os.path.splitext(os.path.basename(self.file_attachment))[0].replace("-", " ").replace("_", " ").title()

    def after_insert(self):
        if self.file_attachment and self.status == "Pending":
            frappe.enqueue(
                "doc_intelligence.doc_intelligence.doctype.ai_document.ai_document.process_document",
                doc_name=self.name, queue="long", timeout=900,
            )

    def on_update(self):
        # after_insert already enqueues processing for a brand-new document.
        # Frappe fires on_update as part of the same insert() call, and by
        # that point is_new() no longer reliably says "this is still the
        # initial insert" -- but self.flags.in_insert does. Without this
        # guard, a fresh upload enqueues TWO workers for the same doc_name,
        # which race on doc.save() and can stomp a successful result with
        # a stale-timestamp "Failed" status.
        if self.flags.in_insert:
            return
        if self.status == "Pending" and self.file_attachment and not self.is_new():
            frappe.enqueue(
                "doc_intelligence.doc_intelligence.doctype.ai_document.ai_document.process_document",
                doc_name=self.name, queue="long", timeout=900,
            )


def fail_stuck_processing_documents():
    """
    Safety net: if a document has been stuck in Processing for longer than
    any single processing attempt could reasonably take (well past the
    background job's own 300s timeout), the worker that was handling it
    almost certainly died or was killed mid-request without ever reaching
    the except block below to mark it Failed. Runs every 15 minutes (see
    hooks.py) and cleans up anything left stranded like that.
    """
    cutoff = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-15)
    stuck = frappe.get_all(
        "AI Document",
        filters={"status": "Processing", "modified": ["<", cutoff]},
        pluck="name",
    )
    for doc_name in stuck:
        frappe.db.set_value(
            "AI Document", doc_name, "status", "Failed",
            update_modified=True,
        )
        frappe.log_error(
            f"AI Document {doc_name} was stuck in Processing for over 15 minutes "
            f"and was auto-marked Failed by the cleanup job.",
            "AI Document stuck-processing cleanup",
        )
    if stuck:
        frappe.db.commit()  # nosemgrep: frappe-manual-commit -- scheduled job, no request-level auto-commit to rely on


def _as_text(value):
    """The LLM is asked for 'summary'/'entities' as plain strings, but it
    sometimes returns a JSON array instead (e.g. entities as a list of
    strings) despite the prompt. Frappe's Long Text fields can't store a
    list, so coerce anything non-string into readable text before it ever
    reaches doc.save()."""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "\n".join(f"- {_as_text(v)}" for v in value)
    if isinstance(value, dict):
        return "\n".join(f"- {k}: {_as_text(v)}" for k, v in value.items())
    if value is None:
        return ""
    return str(value)


def _store_usage(doc, usage, replace):
    """Write summed tokens and, when the provider priced the call, the AED cost."""
    from doc_intelligence.doc_intelligence.llm_engine import aed_per_usd
    incoming_in = int((usage or {}).get("tokens_in") or 0)
    incoming_out = int((usage or {}).get("tokens_out") or 0)
    if replace:
        doc.prompt_tokens = incoming_in
        doc.completion_tokens = incoming_out
    else:
        doc.prompt_tokens = int(doc.prompt_tokens or 0) + incoming_in
        doc.completion_tokens = int(doc.completion_tokens or 0) + incoming_out
    doc.token_count = int(doc.prompt_tokens or 0) + int(doc.completion_tokens or 0)
    if (usage or {}).get("priced"):
        added = float(usage.get("cost_usd") or 0)
        base = 0.0 if replace else float(doc.cost_usd or 0)
        doc.cost_usd = round(base + added, 6)
        doc.cost_aed = round(doc.cost_usd * aed_per_usd(), 4)
    elif replace:
        doc.cost_usd = None
        doc.cost_aed = None


def process_document(doc_name):
    from doc_intelligence.doc_intelligence.llm_engine import begin_usage, take_usage
    doc = frappe.get_doc("AI Document", doc_name)
    usage = None
    begin_usage()
    try:
        doc.status = "Processing"
        doc.save(ignore_permissions=True)
        frappe.db.commit()  # nosemgrep: frappe-manual-commit -- must be visible before the long-running LLM call, in case the job is killed mid-flight

        raw_text, source_format = extract_text(doc.file_attachment)
        doc.raw_text = raw_text
        doc.source_format = source_format

        settings = frappe.get_single("Doc Intelligence Settings")
        from doc_intelligence.doc_intelligence.llm_engine import analyse_document
        token_limit = int(settings.max_tokens_per_request or 4000)
        if token_limit < 4000:
            token_limit = 4000
        from doc_intelligence.doc_intelligence.prompts import output_language
        language = output_language(doc.owner)
        result = analyse_document(
            raw_text,
            doc.document_type or "Document",
            None,
            token_limit,
            source_format=source_format,
            output_language=language,
        )

        from doc_intelligence.doc_intelligence.accountant_summary import (
            accountant_summary,
            replace_arithmetic_warnings,
        )
        model_summary = _as_text(result.get("summary", ""))
        entities = _as_text(result.get("entities", ""))
        accounting = result.get("accounting")
        if isinstance(accounting, dict):
            accounting = replace_arithmetic_warnings(accounting, language)
        doc.summary = accountant_summary(accounting, language, model_summary) or model_summary
        if accounting:
            heading = "Invoice field check" if language == "en" else "Проверка полей счёта"
            doc.key_entities = heading + ":\n" + _as_text(accounting) + ("\n\n" + entities if entities else "")
        else:
            doc.key_entities = entities
        tables = result.get("tables", [])
        doc.extracted_table = json.dumps(tables) if tables else ""
        meta = result.get("_meta", {})
        usage = take_usage()
        _store_usage(doc, usage, replace=True)
        doc.provider_used = meta.get("provider", "")
        if meta.get("fallback_used"):
            doc.provider_used = f"{meta.get('provider')} (fallback)"
        doc.status = "Ready"
        doc.processed_on = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)
        frappe.db.commit()  # nosemgrep: frappe-manual-commit -- background job, commits its own result explicitly

    except Exception as exc:
        frappe.log_error(frappe.get_traceback(), f"AI Document processing failed: {doc_name}")
        if usage is None:
            usage = take_usage()
        failure_note = str(exc).strip().replace("\n", " ")[:500]
        # This save must never itself be allowed to fail silently — if it
        # does (a validation error, a timestamp race with another worker,
        # anything), the document is left permanently stuck instead of
        # cleanly marked Failed. Fall back to a raw, hook-bypassing update
        # as a last resort so the status change always lands no matter what.
        try:
            doc.reload()
            doc.status = "Failed"
            if failure_note:
                doc.summary = failure_note
            if usage:
                _store_usage(doc, usage, replace=True)
            doc.save(ignore_permissions=True)
            frappe.db.commit()  # nosemgrep: frappe-manual-commit -- failure path must land even if the rest of the job never committed
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"AI Document failure-handling itself failed: {doc_name}")
            frappe.db.set_value(
                "AI Document", doc_name,
                {"status": "Failed", "summary": failure_note},
                update_modified=True,
            )
            frappe.db.commit()  # nosemgrep: frappe-manual-commit -- last-resort fallback, must guarantee the status change lands


def extract_text(file_url):
    site_path = frappe.get_site_path()
    if file_url.startswith("/private/files/"):
        file_path = os.path.join(site_path, "private", "files", os.path.basename(file_url))
    else:
        file_path = os.path.join(site_path, "public", "files", os.path.basename(file_url))

    from doc_intelligence.doc_intelligence.file_text import extract_file_text
    from doc_intelligence.doc_intelligence.llm_engine import vision_extract_text
    return extract_file_text(file_path, vision_extract_text)
