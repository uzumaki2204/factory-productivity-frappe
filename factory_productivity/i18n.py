"""UTF-8 messages shared by API and browser."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / "i18n.json").read_text(encoding="utf-8"))


def message(key, lang=None, **values):
    if lang is None:
        try:
            import frappe
            request = getattr(frappe.local, "request", None)
            lang = request.headers.get("X-Productivity-Lang") if request else None
            lang = lang or getattr(frappe.local, "lang", None)
        except (ImportError, AttributeError):
            lang = None
    entries = catalog()
    language = (lang or "vi").split("-")[0]
    template = entries.get(language, entries["vi"]).get(key, entries["vi"]["error.invalid_input"])
    return template.format(**values)
