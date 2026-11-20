"""Refresh plan metadata after introducing explicit production-date validation."""
import frappe


def execute():
    frappe.clear_cache(doctype="Productivity Production Plan")
