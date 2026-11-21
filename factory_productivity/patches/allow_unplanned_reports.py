"""Refresh Report metadata after making the production plan optional."""
import frappe


def execute():
    frappe.clear_cache(doctype="Productivity Report")
