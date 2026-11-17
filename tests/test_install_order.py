"""Regression test for Frappe's before_install/module synchronization order."""
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

frappe = types.ModuleType("frappe")
frappe.ValidationError = type("ValidationError", (Exception,), {})
frappe.throw = lambda text, error=frappe.ValidationError: (_ for _ in ()).throw(error(text))
sys.modules["frappe"] = frappe

from factory_productivity import install  # noqa: E402


class FakeDB:
    def __init__(self, module_owner=None):
        self.module_owner = module_owner

    def exists(self, doctype, name):
        if doctype == "DocType":
            return name != "Time Slot"
        if doctype == "Module Def":
            return self.module_owner is not None
        return False

    def get_value(self, doctype, name, field):
        return self.module_owner if doctype == "Module Def" else None


class InstallOrderTests(unittest.TestCase):
    def test_module_exists_before_time_slot_is_inserted(self):
        events = []
        frappe.db = FakeDB()

        class Doc:
            def __init__(self, values):
                self.values = values

            def insert(self, **_):
                events.append(self.values["doctype"])

        frappe.get_doc = Doc
        install.before_install()
        self.assertLess(events.index("Module Def"), events.index("DocType"))

    def test_conflicting_module_owner_is_rejected(self):
        frappe.db = FakeDB(module_owner="another_app")
        with self.assertRaises(frappe.ValidationError):
            install.ensure_module()


if __name__ == "__main__":
    unittest.main()
