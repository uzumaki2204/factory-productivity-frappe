"""Standalone, mobile-first productivity page."""
import json

import frappe

from factory_productivity import __version__
from factory_productivity.i18n import catalog, message


def get_context(context):
    language = str(frappe.form_dict.get("lang") or "vi").split("-")[0]
    if language not in catalog():
        language = "vi"
    context.no_cache = 1
    context.title = message("ui.title", lang=language)
    context.lang = language
    context.texts = catalog()[language]
    context.texts_json = json.dumps(context.texts, ensure_ascii=False).replace("<", "\\u003c")
    context.asset_version = __version__
