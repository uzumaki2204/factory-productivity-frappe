"""Invalidate metadata cached before the report parity validation update."""
import frappe


def execute():
    frappe.clear_cache(doctype='Productivity Report')
