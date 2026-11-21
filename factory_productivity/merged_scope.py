"""Resolve productivity line groups and consolidate two-line scopes."""

from datetime import date

import frappe

from factory_productivity.model import fail

PLAN = "Productivity Production Plan"
REPORT = "Productivity Report"
LINE_INFO = "Productivity Line Info"
REPAIR_ACTOR = "system:merged-scope-repair"


class MultipleLineGroupsError(frappe.ValidationError):
    """The device line has more than one active productivity scope."""


def _active_filters(doctype, **filters):
    filters["is_active"] = 1
    get_meta = getattr(frappe, "get_meta", None)
    if get_meta and get_meta(doctype).has_field("is_deleted"):
        filters["is_deleted"] = 0
    return filters


def _not_deleted(doctype, **filters):
    get_meta = getattr(frappe, "get_meta", None)
    if get_meta and get_meta(doctype).has_field("is_deleted"):
        filters["is_deleted"] = 0
    return filters


def _line_key(row):
    return (str(row.line_code or "").casefold(), str(row.line_name or "").casefold(), row.name)


def resolve_scope(company, factory, home_line):
    home_fields = ["name", "company", "factory", "line_code", "line_name"]
    if "is_deleted" in _not_deleted("Production Line"):
        home_fields.append("is_deleted")
    home = frappe.db.get_value("Production Line", home_line, home_fields, as_dict=True)
    if not home or home.company != company or home.factory != factory or home.get("is_deleted"):
        fail("error.line_scope", frappe.PermissionError)
    candidates = {
        row.line_group for row in frappe.get_all(
            "Line Group Assignment", fields=["line_group"],
            filters=_active_filters("Line Group Assignment", line=home_line), limit_page_length=200,
        ) if row.line_group
    }
    groups = []
    group_details = {}
    group_fields = ["company", "factory", "is_active", "group_code", "group_name"]
    if "is_deleted" in _not_deleted("Line Group"):
        group_fields.append("is_deleted")
    for group in sorted(candidates):
        details = frappe.db.get_value("Line Group", group, group_fields, as_dict=True)
        if details and details.company == company and details.factory == factory and details.is_active and not details.get("is_deleted"):
            groups.append(group)
            group_details[group] = details
    if len(groups) > 1:
        response = getattr(frappe.local, "response", None)
        if response is not None:
            response["productivity_error_code"] = "multiple_line_groups"
        labels = [group_details[group].group_name or group_details[group].group_code or group for group in groups]
        fail("error.multiple_line_groups", MultipleLineGroupsError,
             line=home.line_name or home.line_code or home.name, groups=", ".join(labels))
    group = groups[0] if groups else None
    line_ids = {home_line}
    if group:
        line_ids.update(row.line for row in frappe.get_all(
            "Line Group Assignment", fields=["line"],
            filters=_active_filters("Line Group Assignment", line_group=group), limit_page_length=1000,
        ))
    lines = frappe.get_all(
        "Production Line", fields=["name", "line_code", "line_name"],
        filters=_not_deleted("Production Line", name=["in", list(line_ids)], company=company, factory=factory),
        limit_page_length=1000,
    )
    lines = sorted(lines, key=lambda row: (row.name != home_line, *_line_key(row)))
    if not lines:
        fail("error.line_scope", frappe.PermissionError)
    canonical = min(lines, key=_line_key).name
    return {"company": company, "factory": factory, "home_line": home_line, "line_group": group,
            "group_code": group_details[group].group_code if group else None,
            "group_name": group_details[group].group_name if group else None, "lines": lines,
            "line_ids": [row.name for row in lines], "canonical_line": canonical,
            "is_merged_scope": len(lines) == 2}


def _date(value):
    return date.fromisoformat(str(value))


def _preferred(rows, canonical):
    return max(rows, key=lambda row: (row.line == canonical, str(row.modified or row.creation or ""), row.name))


def _set(doctype, row, values):
    changed = {key: value for key, value in values.items() if row.get(key) != value}
    if changed:
        frappe.db.set_value(doctype, row.name, changed)
        row.update(changed)
    return bool(changed)


def _delete(doctype, row):
    frappe.db.sql(
        f"UPDATE `tab{doctype}` SET is_deleted = 1, modified = NOW(), modified_by = %s WHERE name = %s",
        (REPAIR_ACTOR, row.name),
    )
    row.is_deleted = 1


def _records(doctype, scope, fields):
    return frappe.get_all(
        doctype, fields=["name", "line", "creation", "modified", *fields],
        filters={"company": scope["company"], "factory": scope["factory"],
                 "line": ["in", scope["line_ids"]], "is_deleted": 0},
        limit_page_length=1000000,
    )


def repair_scope(scope):
    """Return whether records changed. Caller commits after a GET request."""
    if not scope["is_merged_scope"]:
        return False
    canonical = scope["canonical_line"]
    frappe.db.sql("SELECT name FROM `tabLine Group` WHERE name = %s FOR UPDATE", (scope["line_group"],))
    plans = _records(PLAN, scope, ["product", "line_start_date", "shipment_date", "closed_production_date", "line_group", "line_snapshot_type", "line_group_snapshot_code", "line_group_snapshot_name"])
    plans.sort(key=lambda row: (_date(row.line_start_date), _date(row.closed_production_date or row.shipment_date), row.name))
    groups = []
    end = None
    for plan in plans:
        plan_end = _date(plan.closed_production_date or plan.shipment_date)
        if not groups or _date(plan.line_start_date) > end:
            groups.append([plan])
            end = plan_end
        else:
            groups[-1].append(plan)
            end = max(end, plan_end)
    remap = {}
    changed = False
    for group in groups:
        winner = _preferred(group, canonical)
        for plan in group:
            if plan.name != winner.name:
                _delete(PLAN, plan)
                remap[plan.name] = winner.name
                changed = True
    survivors = {row.name: row for row in plans if not row.get("is_deleted")}
    for plan in survivors.values():
        values = {"line": canonical, "line_group": scope["line_group"], "line_snapshot_type": "group"}
        if scope.get("group_code"):
            values["line_group_snapshot_code"] = plan.get("line_group_snapshot_code") or scope["group_code"]
        if scope.get("group_name"):
            values["line_group_snapshot_name"] = plan.get("line_group_snapshot_name") or scope["group_name"]
        changed |= _set(PLAN, plan, values)

    reports = _records(REPORT, scope, ["production_date", "production_plan", "product", "line_group", "line_snapshot_type"])
    report_groups = {}
    for report in reports:
        key = ((str(report.production_date), "plan", remap.get(report.production_plan, report.production_plan))
               if report.production_plan else (str(report.production_date), "product", report.product))
        report_groups.setdefault(key, []).append(report)
    for (_, kind, value), group in report_groups.items():
        plan_name = value if kind == "plan" else None
        winner = _preferred(group, canonical)
        for report in group:
            if report.name != winner.name:
                _delete(REPORT, report)
                changed = True
        values = {"line": canonical, "production_plan": plan_name,
                  "line_group": scope["line_group"], "line_snapshot_type": "group"}
        if plan_name in survivors:
            values["product"] = survivors[plan_name].product
        changed |= _set(REPORT, winner, values)

    infos = _records(LINE_INFO, scope, [])
    if infos:
        winner = _preferred(infos, canonical)
        for info in infos:
            if info.name != winner.name:
                _delete(LINE_INFO, info)
                changed = True
        changed |= _set(LINE_INFO, winner, {"line": canonical})
    return changed


def resolve_merged_alias(doctype, name, scope):
    """Find the surviving record for a tombstone created by this repair."""
    if not scope["is_merged_scope"]:
        return None
    fields = ["name", "line", "is_deleted", "modified_by"]
    fields += (["line_start_date", "shipment_date", "closed_production_date"] if doctype == PLAN
               else ["production_date", "production_plan", "product"] if doctype == REPORT else [])
    old = frappe.db.get_value(doctype, name, fields, as_dict=True)
    if not old or not old.is_deleted or old.modified_by != REPAIR_ACTOR or old.line not in scope["line_ids"]:
        return None
    if doctype == PLAN:
        candidates = frappe.get_all(PLAN,
            fields=["name", "line", "line_start_date", "shipment_date", "closed_production_date", "is_deleted", "modified_by"],
            filters={"company": scope["company"], "factory": scope["factory"],
                     "line": ["in", scope["line_ids"]]}, limit_page_length=1000000)
        candidates = [row for row in candidates if not row.is_deleted or row.modified_by == REPAIR_ACTOR]
        candidates.sort(key=lambda row: (_date(row.line_start_date), _date(row.closed_production_date or row.shipment_date), row.name))
        groups = []
        end = None
        for row in candidates:
            row_end = _date(row.closed_production_date or row.shipment_date)
            if not groups or _date(row.line_start_date) > end:
                groups.append([row])
                end = row_end
            else:
                groups[-1].append(row)
                end = max(end, row_end)
        matches = [row.name for group in groups if any(row.name == name for row in group)
                   for row in group if not row.is_deleted and row.line == scope["canonical_line"]]
    elif doctype == REPORT:
        filters = {"company": scope["company"], "factory": scope["factory"],
                   "line": scope["canonical_line"], "production_date": old.production_date, "is_deleted": 0}
        if old.production_plan:
            filters["production_plan"] = resolve_merged_alias(PLAN, old.production_plan, scope) or old.production_plan
        else:
            filters["production_plan"] = ["is", "not set"]
            filters["product"] = old.product
        matches = frappe.get_all(REPORT, pluck="name", filters=filters, limit_page_length=2)
    else:
        matches = frappe.get_all(LINE_INFO, pluck="name", filters={"company": scope["company"],
            "factory": scope["factory"], "line": scope["canonical_line"], "is_deleted": 0}, limit_page_length=2)
    if len(matches) != 1:
        fail("error.merged_record_refresh")
    return matches[0]
