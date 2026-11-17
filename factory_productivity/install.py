"""Install checks and role permissions for the independent app."""
import frappe
from factory_productivity.i18n import message
from factory_productivity.patches.ensure_time_slot import execute as ensure_time_slot

REQUIRED_DOCTYPES = ("Company", "Factory", "Production Line", "Line Group", "Line Group Assignment", "Product", "Factory Device")
APP_NAME = "factory_productivity"
MODULE_NAME = "Factory Productivity"


def before_install():
    for doctype in REQUIRED_DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            frappe.throw(message("error.missing_doctype", doctype=doctype))
    recover_partial_install()
    ensure_roles()
    ensure_time_slot()


def recover_partial_install():
    if APP_NAME in frappe.get_installed_apps() or not frappe.db.exists("Module Def", MODULE_NAME):
        return
    owner = frappe.db.get_value("Module Def", MODULE_NAME, "app_name")
    if owner != APP_NAME:
        frappe.throw(message("error.module_conflict", module=MODULE_NAME), frappe.ValidationError)

    doctypes = frappe.get_all("DocType", filters={"module": MODULE_NAME}, fields=["name", "custom"], limit_page_length=100)
    unexpected = [row.name for row in doctypes if row.name != "Time Slot" or not row.custom]
    if unexpected:
        frappe.throw(message("error.partial_module_cleanup", doctypes=", ".join(sorted(unexpected))), frappe.ValidationError)

    if frappe.db.exists("DocType", "Time Slot"):
        from factory_productivity.patches.ensure_time_slot import REQUIRED_FIELDS
        available = {field.fieldname for field in frappe.get_meta("Time Slot").fields}
        missing = REQUIRED_FIELDS - available
        if missing:
            frappe.throw(message("error.time_slot_schema", fields=", ".join(sorted(missing))))
        frappe.db.set_value("DocType", "Time Slot", "module", "Factory Management")

    frappe.delete_doc("Module Def", MODULE_NAME, ignore_permissions=True, force=True)
    frappe.clear_cache()


def ensure_roles():
    for role in ("Productivity Manager", "Productivity Viewer"):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def after_migrate():
    ensure_roles()
    ensure_time_slot()
    frappe.clear_cache()
