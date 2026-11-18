from datetime import date

import frappe
from frappe.model.document import Document
from factory_productivity.model import assign_id, fail, non_negative, validate_scope


class ProductivityReport(Document):
    def before_naming(self):
        assign_id(self)

    def validate(self):
        validate_scope(self)
        non_negative(self.daily_target_quantity, self.working_hours, self.worker_count, self.ironing_delivery_quantity)
        if self.is_deleted:
            return
        if not frappe.db.exists("Productivity Production Plan", self.production_plan):
            fail("error.plan_missing")
        # Serialize writers to this plan before reading effective dates and checking duplicates.
        frappe.db.sql('SELECT name FROM `tabProductivity Production Plan` WHERE name = %s FOR UPDATE', (self.production_plan,))
        plan = frappe.get_doc("Productivity Production Plan", self.production_plan)
        if plan.is_deleted:
            fail("error.plan_missing")
        if (plan.company, plan.factory, plan.line, plan.product) != (self.company, self.factory, self.line, self.product):
            fail("error.report_plan")
        try:
            production_day = date.fromisoformat(str(self.production_date))
            start = date.fromisoformat(str(plan.line_start_date))
            end = date.fromisoformat(str(plan.closed_production_date or plan.shipment_date))
        except (TypeError, ValueError):
            fail('error.date')
        if not start <= production_day <= end:
            fail('error.report_date')
        existing = frappe.db.get_value(self.doctype, {
            'company': self.company, 'factory': self.factory, 'line': self.line,
            'production_date': self.production_date, 'production_plan': self.production_plan,
            'is_deleted': 0, 'name': ['!=', self.name or ''],
        }, 'name')
        if existing and existing != self.name:
            fail('error.duplicate_report')
        if not self.time_slots:
            fail('error.no_slots')
        seen = set()
        for row in self.time_slots:
            non_negative(row.finished_quantity)
            if frappe.db.get_value("Time Slot", row.time_slot, "company") != self.company:
                fail("error.master_mismatch")
            if row.time_slot in seen:
                fail("error.duplicate_slot")
            seen.add(row.time_slot)
