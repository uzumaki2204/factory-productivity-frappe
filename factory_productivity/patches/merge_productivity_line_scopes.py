"""Normalize historical productivity records for active two-line groups."""

import frappe

from factory_productivity.i18n import message
from factory_productivity.merged_scope import repair_scope, resolve_scope


def execute():
    groups = frappe.get_all(
        "Line Group", fields=["name", "company", "factory"],
        filters={"is_active": 1}, limit_page_length=1000000,
    )
    repaired = set()
    for group in groups:
        assignments = frappe.get_all(
            "Line Group Assignment", fields=["line"],
            filters={"line_group": group.name, "is_active": 1}, limit_page_length=1000,
        )
        home_line = next((row.line for row in assignments
                          if (line := frappe.db.get_value("Production Line", row.line, ["company", "factory"], as_dict=True))
                          and line.company == group.company and line.factory == group.factory), None)
        if not home_line:
            continue
        try:
            scope = resolve_scope(group.company, group.factory, home_line)
        except (frappe.ValidationError, frappe.PermissionError) as exc:
            frappe.log_error(title=message("error.scope_repair_skipped", group=group.name), message=str(exc))
            continue
        if scope["is_merged_scope"] and scope["line_group"] == group.name:
            pair = tuple(scope["line_ids"])
            if pair not in repaired:
                repair_scope(scope)
                repaired.add(pair)
