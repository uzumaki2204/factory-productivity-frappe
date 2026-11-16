"""Tablet APIs backed by Frappe DocTypes and approved Factory Device records."""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import frappe
from factory_management import device_registry
from factory_productivity.i18n import catalog, message
from factory_productivity.model import fail

PLAN = "Productivity Production Plan"
REPORT = "Productivity Report"
LINE_INFO = "Productivity Line Info"


def payload(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            fail("error.invalid_input")
    if not isinstance(value, (dict, list)):
        fail("error.invalid_input")
    return value


def device_for(device_id):
    if not device_id or not frappe.db.exists("Factory Device", str(device_id)):
        fail("error.device_missing", frappe.DoesNotExistError)
    device = frappe.get_doc("Factory Device", str(device_id))
    if not device_registry.ready(device):
        fail("error.device_pending", frappe.PermissionError)
    if not (device.company and device.factory and device.line):
        fail("error.device_scope", frappe.PermissionError)
    return device


def scope_lines(device):
    assignments = frappe.get_all(
        "Line Group Assignment",
        fields=["line_group"],
        filters={"line": device.line, "is_active": 1},
        limit_page_length=20,
    )
    lines = {device.line}
    if len(assignments) == 1:
        for row in frappe.get_all(
            "Line Group Assignment",
            fields=["line"],
            filters={"line_group": assignments[0].line_group, "is_active": 1},
            limit_page_length=200,
        ):
            if frappe.db.get_value("Production Line", row.line, "factory") == device.factory:
                lines.add(row.line)
    return sorted(lines)


def require_line(device, line):
    if line not in scope_lines(device):
        fail("error.line_scope", frappe.PermissionError)


def scoped_record(doctype, name, device):
    if not frappe.db.exists(doctype, name):
        fail("error.invalid_input", frappe.DoesNotExistError)
    doc = frappe.get_doc(doctype, name)
    if doc.company != device.company or doc.factory != device.factory or doc.line not in scope_lines(device):
        fail("error.line_scope", frappe.PermissionError)
    return doc


def _page(doctype, device, page=1, page_size=50, extra=None):
    try:
        page = max(1, int(page))
        page_size = min(200, max(1, int(page_size)))
    except (TypeError, ValueError):
        fail("error.invalid_input")
    filters = {"company": device.company, "factory": device.factory, "line": ["in", scope_lines(device)], "is_deleted": 0}
    filters.update(extra or {})
    names = frappe.get_all(
        doctype, fields=["name"], filters=filters,
        order_by="modified desc", start=(page - 1) * page_size, page_length=page_size,
    )
    return {
        "items": [frappe.get_doc(doctype, row.name).as_dict() for row in names],
        "page": page,
        "page_size": page_size,
        "total": frappe.db.count(doctype, filters=filters),
    }


def _save(doctype, device, data):
    data = payload(data)
    if not isinstance(data, dict):
        fail("error.invalid_input")
    name = str(data.get("name") or "").strip()
    if name and frappe.db.exists(doctype, name):
        doc = scoped_record(doctype, name, device)
        if doc.is_deleted:
            fail("error.invalid_input")
    else:
        doc = frappe.new_doc(doctype)
        if name:
            try:
                doc.legacy_id = str(uuid.UUID(name))
            except (TypeError, ValueError):
                fail("error.invalid_input")
    line = data.get("line") or device.line
    require_line(device, line)
    for key in ("company", "factory", "is_deleted", "legacy_id", "device"):
        data.pop(key, None)
    if doctype == PLAN:
        permitted = {"product", "line_start_date", "shipment_date", "planned_quantity", "line_group"}
    elif doctype == REPORT:
        permitted = {"production_date", "production_plan", "product", "daily_target_quantity",
                     "working_hours", "worker_count", "ironing_delivery_quantity", "time_slots", "line_group"}
    else:
        permitted = {"line_leader_name", "technical_leader_name"}
    for key in permitted:
        if key in data:
            doc.set(key, data[key])
    doc.company = device.company
    doc.factory = device.factory
    doc.line = line
    if doctype in (REPORT, LINE_INFO):
        doc.device = device.name
    if doctype == REPORT:
        plan = scoped_record(PLAN, doc.production_plan, device)
        if plan.is_deleted:
            fail("error.plan_missing")
        if plan.closed_production_date and str(doc.production_date) > str(plan.closed_production_date):
            fail("error.plan_closed")
    if doctype == LINE_INFO:
        doc.updated_by_device_name = device.device_name
    if not doc.is_new():
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
    return doc.as_dict()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def translations(lang="vi"):
    return catalog().get(str(lang).split("-")[0], catalog()["vi"])


@frappe.whitelist(allow_guest=True, methods=["POST"])
def check_device(device_id=None):
    device = device_for(device_id)
    return {
        "id": device.name, "name": device.device_name, "company": device.company,
        "factory": device.factory, "line": device.line, "scope_lines": scope_lines(device),
    }


@frappe.whitelist(allow_guest=True, methods=["GET"])
def bootstrap(device_id=None):
    device = device_for(device_id)
    lines = scope_lines(device)
    return {
        "device": check_device(device_id),
        "lines": frappe.get_all("Production Line", fields=["name", "line_code", "line_name"], filters={"name": ["in", lines]}, limit_page_length=200),
        "products": frappe.get_all("Product", fields=["name", "product_code", "product_name"], filters={"is_active": 1}, limit_page_length=20000),
        "time_slots": frappe.get_all("Time Slot", fields=["name", "slot_name", "start_time", "end_time", "sort_order"], filters={"company": device.company}, order_by="sort_order asc", limit_page_length=200),
    }


@frappe.whitelist(allow_guest=True, methods=["GET"])
def list_plans(device_id=None, page=1, page_size=50):
    return _page(PLAN, device_for(device_id), page, page_size)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def list_reports(device_id=None, page=1, page_size=50):
    return _page(REPORT, device_for(device_id), page, page_size)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def current_line_info(device_id=None, line=None):
    device = device_for(device_id)
    line = line or device.line
    require_line(device, line)
    names = frappe.get_all(LINE_INFO, fields=["name"], filters={"line": line, "is_deleted": 0},
                           order_by="modified desc", page_length=1)
    return frappe.get_doc(LINE_INFO, names[0].name).as_dict() if names else None


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save_plan(device_id=None, values=None):
    return {"data": _save(PLAN, device_for(device_id), values), "notice": message("ok.saved")}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save_report(device_id=None, values=None):
    return {"data": _save(REPORT, device_for(device_id), values), "notice": message("ok.saved")}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save_line_info(device_id=None, values=None):
    return {"data": _save(LINE_INFO, device_for(device_id), values), "notice": message("ok.saved")}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def change_plan_state(device_id=None, name=None, action=None, closed_date=None):
    device = device_for(device_id)
    plan = scoped_record(PLAN, name, device)
    if action == "finish":
        plan.closed_production_date = closed_date or frappe.utils.today()
        plan.closed_at = frappe.utils.now()
        plan.closed_by = device.device_name
    elif action == "reopen":
        plan.closed_production_date = None
        plan.closed_at = None
        plan.closed_by = None
    elif action == "delete":
        plan.is_deleted = 1
    else:
        fail("error.invalid_input")
    plan.save(ignore_permissions=True)
    return {"data": plan.as_dict(), "notice": message("ok.saved")}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def delete_report(device_id=None, name=None):
    doc = scoped_record(REPORT, name, device_for(device_id))
    doc.is_deleted = 1
    doc.save(ignore_permissions=True)
    return {"name": name, "notice": message("ok.deleted")}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def sync_state(device_id=None):
    device = device_for(device_id)
    lines = scope_lines(device)
    versions = {}
    for key, doctype in (("plan", PLAN), ("report", REPORT), ("line_info", LINE_INFO)):
        rows = frappe.get_all(doctype, fields=["modified"], filters={"company": device.company, "line": ["in", lines]},
                              order_by="modified desc", page_length=1)
        versions[key] = str(rows[0].modified) if rows else ""
    token = hashlib.sha256(json.dumps(lines, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"scope_lines": lines, "scope_token": token, "versions": versions, "server_utc": datetime.now(timezone.utc).isoformat()}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def sync_batch(device_id=None, operations=None):
    device = device_for(device_id)
    operations = payload(operations)
    if not isinstance(operations, list) or len(operations) > 100:
        fail("error.invalid_input")
    actions = {"save_plan": lambda x: _save(PLAN, device, x),
               "save_report": lambda x: _save(REPORT, device, x),
               "save_line_info": lambda x: _save(LINE_INFO, device, x)}
    results = []
    for item in operations:
        if not isinstance(item, dict) or item.get("action") not in actions or not item.get("operation_id"):
            fail("error.invalid_input")
        uid = hashlib.sha256((device.name + ":" + str(item["operation_id"])).encode("utf-8")).hexdigest()
        existing = frappe.db.get_value("Productivity Sync Receipt", {"operation_uid": uid}, "result_json")
        if existing:
            results.append(json.loads(existing))
            continue
        savepoint = "productivity_" + frappe.generate_hash(length=10)
        frappe.db.savepoint(savepoint)
        try:
            data = actions[item["action"]](device, item.get("values") or {})
            result = {"operation_id": item["operation_id"], "success": True, "data": data}
            frappe.get_doc({"doctype": "Productivity Sync Receipt", "operation_uid": uid,
                            "device": device.name, "target_doctype": data["doctype"],
                            "target_name": data["name"], "result_json": json.dumps(result, ensure_ascii=False)}).insert(ignore_permissions=True)
            results.append(result)
        except frappe.ValidationError as exc:
            frappe.db.rollback(save_point=savepoint)
            results.append({"operation_id": item["operation_id"], "success": False, "message": str(exc)})
    return {"results": results, "notice": message("ok.synced")}
