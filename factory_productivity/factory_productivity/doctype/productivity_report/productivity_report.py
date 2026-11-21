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
        try:
            date.fromisoformat(str(self.production_date))
        except (TypeError, ValueError):
            fail('error.date')
        product_rows = frappe.db.sql('SELECT is_active FROM `tabProduct` WHERE name = %s FOR UPDATE', (self.product,), as_dict=True)
        if not product_rows:
            fail('error.product_inactive')
        previous_product = None if self.is_new() else frappe.db.get_value(self.doctype, self.name, 'product')
        if not product_rows[0].is_active and (self.is_new() or previous_product != self.product):
            fail('error.product_inactive')
        if self.production_plan:
            if not frappe.db.exists('Productivity Production Plan', self.production_plan):
                fail('error.plan_missing')
            frappe.db.sql('SELECT name FROM `tabProductivity Production Plan` WHERE name = %s FOR UPDATE', (self.production_plan,))
            plan = frappe.get_doc('Productivity Production Plan', self.production_plan)
            if plan.is_deleted:
                fail('error.plan_missing')
            if (plan.company, plan.factory, plan.line, plan.product) != (self.company, self.factory, self.line, self.product):
                fail('error.report_plan')
        existing = frappe.db.get_value(self.doctype, {
            'company': self.company, 'factory': self.factory, 'line': self.line,
            'production_date': self.production_date, 'product': self.product,
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
