from frappe.model.document import Document
from factory_productivity.model import assign_id, validate_scope


class ProductivityLineInfo(Document):
    def before_naming(self):
        assign_id(self)

    def validate(self):
        validate_scope(self)
