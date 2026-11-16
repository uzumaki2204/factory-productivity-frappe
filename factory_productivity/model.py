"""Shared validation and naming for Productivity documents."""
import uuid
import frappe
from factory_productivity.i18n import message


def assign_id(doc):
    if not doc.get("legacy_id"):
        doc.legacy_id = str(uuid.uuid4())


def fail(key, error=frappe.ValidationError, **values):
    frappe.throw(message(key, **values), error)


def validate_scope(doc):
    factory = frappe.db.get_value("Factory", doc.factory, ["company"], as_dict=True)
    line = frappe.db.get_value("Production Line", doc.line, ["company", "factory", "line_code", "line_name"], as_dict=True)
    if not factory or not line or factory.company != doc.company or line.company != doc.company or line.factory != doc.factory:
        fail("error.master_mismatch")
    if doc.get("device"):
        device = frappe.db.get_value("Factory Device", doc.device, ["company", "factory", "line", "status", "is_active"], as_dict=True)
        if not device or device.company != doc.company or device.factory != doc.factory:
            fail("error.master_mismatch")
    if doc.get("product") and not frappe.db.exists("Product", doc.product):
        fail("error.invalid_input")
    if doc.meta.has_field("line_snapshot_code"):
        doc.line_snapshot_code = doc.get("line_snapshot_code") or line.line_code
        doc.line_snapshot_name = doc.get("line_snapshot_name") or line.line_name
        if doc.get("line_group"):
            group = frappe.db.get_value("Line Group", doc.line_group, ["group_code", "group_name", "company", "factory"], as_dict=True)
            if not group or group.company != doc.company or group.factory != doc.factory:
                fail("error.master_mismatch")
            doc.line_group_snapshot_code = doc.get("line_group_snapshot_code") or group.group_code
            doc.line_group_snapshot_name = doc.get("line_group_snapshot_name") or group.group_name
            doc.line_snapshot_type = "group"
        else:
            doc.line_snapshot_type = doc.get("line_snapshot_type") or "line"


def non_negative(*values):
    if any(value is None or float(value) < 0 for value in values):
        fail("error.quantity")
