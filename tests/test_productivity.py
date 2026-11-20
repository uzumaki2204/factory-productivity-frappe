"""Business-rule regressions derived from ProductivityServices.cs; no live writes."""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class Row(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


frappe = types.ModuleType('frappe')
frappe.ValidationError = ValueError
frappe.PermissionError = PermissionError
frappe.DoesNotExistError = LookupError
frappe.local = Row(lang='vi')
frappe.throw = lambda text, error=ValueError: (_ for _ in ()).throw(error(text))
frappe.whitelist = lambda **kwargs: lambda fn: fn
frappe.utils = Row(today=lambda:'2026-11-17',now=lambda:'2026-11-17 09:30:00')
sys.modules['frappe'] = frappe
document = types.ModuleType('frappe.model.document')
document.Document = Row
sys.modules['frappe.model'] = types.ModuleType('frappe.model')
sys.modules['frappe.model.document'] = document
master = types.ModuleType('factory_management')
master.device_registry = Row(ready=lambda d:d.status=='Approved' and d.is_active)
sys.modules['factory_management'] = master
from factory_productivity import api
from factory_productivity.i18n import message
from factory_productivity.factory_productivity.doctype.productivity_production_plan.productivity_production_plan import ProductivityProductionPlan
from factory_productivity.factory_productivity.doctype.productivity_report.productivity_report import ProductivityReport


class ProductivityTests(unittest.TestCase):
    def setUp(self):
        frappe.db = MagicMock()
        frappe.db.exists.side_effect = lambda dt, name: dt in ('Productivity Production Plan','Product')
        frappe.db.get_value.side_effect = self.get_value
        self.plan = Row(name='PLAN',company='C',factory='F',line='L',product='P',line_start_date='2026-11-10',shipment_date='2026-11-21',closed_production_date=None,is_deleted=0)
        frappe.get_doc = MagicMock(return_value=self.plan)
        frappe.get_all = MagicMock(return_value=[])
        self.doc = ProductivityReport(doctype='Productivity Report',name='R',company='C',factory='F',line='L',product='P',production_plan='PLAN',production_date='2026-11-17',daily_target_quantity=400,working_hours=8,worker_count=20,ironing_delivery_quantity=4,time_slots=[Row(time_slot='S1',finished_quantity=80),Row(time_slot='S2',finished_quantity=70)])
        self.doc.meta=Row(has_field=lambda _:False)

    def get_value(self, dt, name, fields=None, **kwargs):
        if dt=='Factory': return Row(company='C')
        if dt=='Production Line': return Row(company='C',factory='F',line_code='315',line_name='C5X3')
        if dt=='Time Slot': return 'C'
        return None

    def test_valid_report_preserves_exact_quantities(self):
        self.doc.validate()
        self.assertEqual([80,70],[r.finished_quantity for r in self.doc.time_slots])
        self.assertEqual(150,sum(r.finished_quantity for r in self.doc.time_slots))

    def test_plan_rejects_reversed_dates_with_specific_vietnamese_message(self):
        plan = ProductivityProductionPlan(doctype='Productivity Production Plan', name='P1', company='C', factory='F', line='L', product='P', planned_quantity=1, line_start_date='2026-11-20', shipment_date='2026-11-17', is_deleted=0, closed_production_date=None)
        plan.meta = Row(has_field=lambda _: False)
        with self.assertRaisesRegex(ValueError, 'Ngày xuất hàng phải lớn hơn hoặc bằng ngày lên chuyền'):
            plan.validate()
        plan.shipment_date = '2026-11-20'
        plan.validate()

    def test_plan_required_and_malformed_dates_have_localized_messages(self):
        plan = ProductivityProductionPlan(doctype='Productivity Production Plan', name='P1', company='C', factory='F', line='L', product='P', planned_quantity=1, line_start_date=None, shipment_date='2026-11-21', is_deleted=0, closed_production_date=None)
        plan.meta = Row(has_field=lambda _: False)
        for start, shipment, expected in [(None, '2026-11-21', 'Vui lòng chọn ngày lên chuyền'), ('2026-11-20', None, 'Vui lòng chọn ngày xuất hàng'), ('2026-99-99', '2026-11-21', 'Ngày không hợp lệ')]:
            with self.subTest(start=start, shipment=shipment):
                plan.line_start_date, plan.shipment_date = start, shipment
                with self.assertRaisesRegex(ValueError, expected):
                    plan.validate()

    def test_requested_language_overrides_frappe_default(self):
        frappe.local.lang = 'en'
        frappe.local.request = Row(headers={'X-Productivity-Lang': 'vi'})
        try:
            self.assertEqual('Ngày xuất hàng phải lớn hơn hoặc bằng ngày lên chuyền.', message('error.plan_date_order'))
        finally:
            frappe.local.lang = 'vi'
            frappe.local.pop('request', None)

    def test_report_requires_at_least_one_time_slot_like_dotnet(self):
        self.doc.time_slots=[]
        with self.assertRaises(ValueError): self.doc.validate()

    def test_zero_target_hours_and_quantities_are_valid_like_dotnet(self):
        self.doc.update(daily_target_quantity=0,working_hours=0,worker_count=0,ironing_delivery_quantity=0,time_slots=[Row(time_slot='S1',finished_quantity=0)])
        self.doc.validate()

    def test_report_must_be_within_effective_plan_dates_inclusive(self):
        for day, valid in [('2026-11-09',False),('2026-11-10',True),('2026-11-21',True),('2026-11-22',False)]:
            with self.subTest(day=day):
                self.doc.production_date=day
                if valid: self.doc.validate()
                else:
                    with self.assertRaises(ValueError): self.doc.validate()

    def test_closed_date_replaces_shipment_date(self):
        self.plan.closed_production_date='2026-11-15'
        self.doc.production_date='2026-11-15'
        self.doc.validate()
        self.doc.production_date='2026-11-16'
        with self.assertRaises(ValueError): self.doc.validate()

    def test_duplicate_line_day_plan_report_rejected_but_self_update_allowed(self):
        original=self.get_value
        for found, valid in [('OTHER',False),('R',True),(None,True)]:
            with self.subTest(found=found):
                frappe.db.get_value.side_effect=lambda dt,*a,**kw: found if dt=='Productivity Report' else original(dt,*a,**kw)
                if valid: self.doc.validate()
                else:
                    with self.assertRaises(ValueError): self.doc.validate()

    def test_plan_scope_or_product_mismatch_rejected(self):
        for field in ('company','factory','line','product'):
            with self.subTest(field=field):
                before=self.plan[field]
                self.plan[field]='OTHER'
                with self.assertRaises(ValueError): self.doc.validate()
                self.plan[field]=before

    def test_deleted_plan_rejected(self):
        self.plan.is_deleted=1
        with self.assertRaises(ValueError): self.doc.validate()

    def test_soft_delete_can_remove_report_with_deleted_plan(self):
        self.plan.is_deleted=1
        self.doc.is_deleted=1
        self.doc.validate()

    def test_open_plan_options_are_effective_on_selected_production_day(self):
        from datetime import date
        with patch.object(api,'device_for',return_value=Row(company='C',factory='F')),patch.object(api,'scope_lines',return_value=['L']):
            api.open_plans('DEV','2026-11-17')
        filters=frappe.get_all.call_args.kwargs['filters']
        self.assertEqual(['<=',date(2026,11,17)],filters['line_start_date'])
        self.assertEqual(['>=',date(2026,11,17)],filters['shipment_date'])

    def test_duplicate_and_negative_time_slots_rejected(self):
        for slots in ([Row(time_slot='S1',finished_quantity=1),Row(time_slot='S1',finished_quantity=2)],[Row(time_slot='S1',finished_quantity=-1)]):
            with self.subTest(slots=slots):
                self.doc.time_slots=slots
                with self.assertRaises(ValueError): self.doc.validate()

    def test_wrong_company_slot_rejected(self):
        original=self.get_value
        frappe.db.get_value.side_effect=lambda dt,*a,**kw:'OTHER' if dt=='Time Slot' else original(dt,*a,**kw)
        with self.assertRaises(ValueError): self.doc.validate()

    def test_negative_report_fields_rejected(self):
        for field in ('daily_target_quantity','working_hours','worker_count','ironing_delivery_quantity'):
            with self.subTest(field=field):
                before=self.doc[field]
                self.doc[field]=-1
                with self.assertRaises(ValueError): self.doc.validate()
                self.doc[field]=before

    def test_save_report_payload_and_device_scope_are_preserved(self):
        device=Row(name='DEV',company='C',factory='F',line='L')
        doc=MagicMock()
        doc.is_new.return_value=True
        doc.as_dict.return_value={'name':'R','time_slots':[{'time_slot':'S1','finished_quantity':80}]}
        frappe.new_doc=MagicMock(return_value=doc)
        values={'name':'00000000-0000-0000-0000-000000000001','line':'L','production_plan':'PLAN','product':'P','time_slots':[{'time_slot':'S1','finished_quantity':80}], 'company':'FORGED'}
        with patch.object(api,'require_line'),patch.object(api,'scoped_record',return_value=self.plan):
            api._save(api.REPORT,device,values)
        doc.set.assert_any_call('time_slots',[{'time_slot':'S1','finished_quantity':80}])
        self.assertEqual('C',doc.company)
        doc.insert.assert_called_once_with(ignore_permissions=True)

    def test_sync_retry_returns_receipt_without_applying_mutation_again(self):
        import json
        result={'operation_id':'op1','success':True,'data':{'name':'R'}}
        frappe.db.get_value.return_value=json.dumps(result)
        frappe.db.get_value.side_effect=None
        with patch.object(api,'device_for',return_value=Row(name='DEV')),patch.object(api,'_save') as save:
            answer=api.sync_batch('DEV',[{'operation_id':'op1','action':'save_report','values':{}}])
        save.assert_not_called()
        self.assertEqual([result],answer['results'])


if __name__=='__main__':
    unittest.main()
