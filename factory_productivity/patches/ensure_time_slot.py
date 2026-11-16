"""Provision the missing Time Slot master without replacing a site-owned DocType."""
import frappe
from factory_productivity.i18n import message


REQUIRED_FIELDS = {"company", "slot_name", "start_time", "end_time", "sort_order"}


def execute():
    if frappe.db.exists("DocType", "Time Slot"):
        available = {field.fieldname for field in frappe.get_meta("Time Slot").fields}
        missing = REQUIRED_FIELDS - available
        if missing:
            frappe.throw(message("error.time_slot_schema", fields=", ".join(sorted(missing))))
        return
    frappe.get_doc({
        "doctype": "DocType",
        "name": "Time Slot",
        "module": "Factory Productivity",
        "custom": 1,
        "autoname": "format:{company}-{slot_name}",
        "allow_import": 1,
        "fields": [
            {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "reqd": 1},
            {"fieldname": "slot_name", "label": "Slot Name", "fieldtype": "Data", "reqd": 1},
            {"fieldname": "start_time", "label": "Start Time", "fieldtype": "Time", "reqd": 1},
            {"fieldname": "end_time", "label": "End Time", "fieldtype": "Time", "reqd": 1},
            {"fieldname": "sort_order", "label": "Sort Order", "fieldtype": "Int", "reqd": 1},
        ],
        "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "import": 1}],
    }).insert(ignore_permissions=True)
