"""Provide the six existing .NET default shifts for companies using devices.

Leave a company's configured Time Slots untouched.  This seeds master
configuration only; it does not import reports or other historical records.
"""

import frappe


DEFAULT_SLOTS = (
    ("Ca 1 (07:30–09:30)", "07:30:00", "09:30:00"),
    ("Ca 2 (09:30–11:30)", "09:30:00", "11:30:00"),
    ("Ca 3 (12:30–14:30)", "12:30:00", "14:30:00"),
    ("Ca 4 (14:30–16:30)", "14:30:00", "16:30:00"),
    ("Ca 5 (16:30–18:30)", "16:30:00", "18:30:00"),
    ("Ca 6 (18:30–20:30)", "18:30:00", "20:30:00"),
)


def execute():
    companies = {
        row.company
        for row in frappe.get_all(
            "Factory Device",
            fields=["company"],
            filters={"status": "Approved", "is_active": 1},
            limit_page_length=20000,
        )
        if row.company
    }
    for company in sorted(companies):
        if frappe.db.exists("Time Slot", {"company": company}):
            continue
        for order, (name, start, end) in enumerate(DEFAULT_SLOTS, start=1):
            frappe.get_doc({
                "doctype": "Time Slot", "company": company, "slot_name": name,
                "start_time": start, "end_time": end, "sort_order": order,
            }).insert(ignore_permissions=True)
