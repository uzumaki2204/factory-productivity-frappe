"""Install checks and role permissions for the independent app."""
import frappe
from factory_productivity.i18n import message
from factory_productivity.patches.ensure_time_slot import execute as ensure_time_slot

REQUIRED_DOCTYPES = ("Company", "Factory", "Production Line", "Line Group", "Line Group Assignment", "Product", "Factory Device")
MODULE_NAME = "Factory Productivity"
APP_NAME = "factory_productivity"


def before_install():
    for doctype in REQUIRED_DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            frappe.throw(message("error.missing_doctype", doctype=doctype))
    ensure_module()
    ensure_roles()
    ensure_time_slot()


def ensure_module():
    exists = frappe.db.exists("Module Def", MODULE_NAME)
    owner = frappe.db.get_value("Module Def", MODULE_NAME, "app_name") if exists else None
    if exists and owner != APP_NAME:
        frappe.throw(message("error.module_conflict", module=MODULE_NAME), frappe.ValidationError)
    if not exists:
        frappe.get_doc({"doctype": "Module Def", "module_name": MODULE_NAME, "app_name": APP_NAME, "custom": 0}).insert(ignore_permissions=True)


def ensure_roles():
    for role in ("Productivity Manager", "Productivity Viewer"):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def after_migrate():
    ensure_module()
    ensure_roles()
    ensure_time_slot()
    frappe.clear_cache()
