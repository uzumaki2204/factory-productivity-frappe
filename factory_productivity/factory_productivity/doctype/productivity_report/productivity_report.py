import frappe
from frappe.model.document import Document
from factory_productivity.model import assign_id, fail, non_negative, validate_scope


class ProductivityReport(Document):
    def before_naming(self):
        assign_id(self)

    def validate(self):
        validate_scope(self)
        non_negative(self.daily_target_quantity, self.working_hours, self.worker_count, self.ironing_delivery_quantity)
        if not frappe.db.exists("Productivity Production Plan", self.production_plan):
            fail("error.plan_missing")
        plan = frappe.get_doc("Productivity Production Plan", self.production_plan)
        if (plan.company, plan.factory, plan.line, plan.product) != (self.company, self.factory, self.line, self.product):
            fail("error.report_plan")
        if plan.closed_production_date and self.production_date and str(self.production_date) > str(plan.closed_production_date):
            fail("error.plan_closed")
        seen = set()
        for row in self.time_slots:
            non_negative(row.finished_quantity)
            if frappe.db.get_value("Time Slot", row.time_slot, "company") != self.company:
                fail("error.master_mismatch")
            if row.time_slot in seen:
                fail("error.duplicate_slot")
            seen.add(row.time_slot)
