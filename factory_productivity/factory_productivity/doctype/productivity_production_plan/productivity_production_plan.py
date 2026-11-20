from datetime import date

import frappe
from frappe.model.document import Document
from factory_productivity.model import assign_id, fail, non_negative, validate_scope


class ProductivityProductionPlan(Document):
    def before_naming(self):
        assign_id(self)

    def validate(self):
        validate_scope(self)
        non_negative(self.planned_quantity)
        if not self.line_start_date:
            fail("error.line_start_date_required")
        if not self.shipment_date:
            fail("error.shipment_date_required")
        try:
            line_start_date = date.fromisoformat(str(self.line_start_date))
            shipment_date = date.fromisoformat(str(self.shipment_date))
        except (TypeError, ValueError):
            fail("error.date")
        if line_start_date > shipment_date:
            fail("error.plan_date_order")
        if not self.is_deleted and not self.closed_production_date:
            existing = frappe.db.get_value(
                self.doctype,
                {"company": self.company, "factory": self.factory, "line": self.line, "is_deleted": 0, "closed_production_date": ["is", "not set"]},
                "name",
            )
            if existing and existing != self.name:
                fail("error.open_plan")
