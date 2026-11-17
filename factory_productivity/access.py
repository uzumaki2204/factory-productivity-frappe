"""Desk shortcut visibility for Factory Productivity."""

import frappe


ALLOWED_ROLES = {"System Manager", "Productivity Manager", "Productivity Viewer"}


def can_open():
    user = frappe.session.user
    if user == "Administrator":
        return True
    if user == "Guest":
        return False
    return bool(ALLOWED_ROLES.intersection(frappe.get_roles(user)))
