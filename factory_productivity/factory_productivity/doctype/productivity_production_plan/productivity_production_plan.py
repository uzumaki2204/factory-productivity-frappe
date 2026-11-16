import frappe
from frappe.model.document import Document
from factory_productivity.model import assign_id, fail, non_negative, validate_scope


class ProductivityProductionPlan(Document):
    def before_naming(self):
        assign_id(self)

    def validate(self):
        validate_scope(self)
        non_negative(self.planned_quantity)
        if not self.line_start_date or not self.shipment_date:
            fail("error.date")
        if self.line_start_date > self.shipment_date:
            fail("error.date")
        if not self.is_deleted and not self.closed_production_date:
            existing = frappe.db.get_value(
                self.doctype,
                {"company": self.company, "factory": self.factory, "line": self.line, "is_deleted": 0, "closed_production_date": ["is", "not set"]},
                "name",
            )
            if existing and existing != self.name:
                fail("error.open_plan")
