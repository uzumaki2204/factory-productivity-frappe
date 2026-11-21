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
from factory_productivity import api, merged_scope
from factory_productivity.factory_productivity.doctype.productivity_production_plan.productivity_production_plan import (
    ProductivityProductionPlan,
)
from factory_productivity.factory_productivity.doctype.productivity_report.productivity_report import (
    ProductivityReport,
)
from factory_productivity.i18n import message


class ProductivityTests(unittest.TestCase):
    def setUp(self):
        frappe.local.pop('productivity_lang', None)
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

    def test_sync_rejection_uses_explicit_page_language(self):
        from factory_productivity.model import fail
        frappe.local.lang = 'en'
        operation = {'operation_id': 'op1', 'action': 'save_plan', 'values': {'name': 'P1'}}
        try:
            with patch.object(api, 'device_for', return_value=Row(name='DEV')), patch.object(api, '_save', side_effect=lambda *_: fail('error.open_plan')), patch.object(frappe, 'generate_hash', return_value='1234567890', create=True):
                result = api.sync_batch('DEV', [operation], lang='vi')
            self.assertEqual(1, len(result['results']))
            self.assertFalse(result['results'][0]['success'])
            self.assertEqual('Chuyền đã có kế hoạch đang mở.', result['results'][0]['message'])
            frappe.db.rollback.assert_called_once()
        finally:
            frappe.local.lang = 'vi'
            frappe.local.pop('productivity_lang', None)

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
                frappe.db.get_value.side_effect=lambda dt,*a,found=found,**kw: found if dt=='Productivity Report' else original(dt,*a,**kw)
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
        scope={'line_ids':['L'],'is_merged_scope':False}
        with patch.object(api,'device_for',return_value=Row(company='C',factory='F')),patch.object(api,'_scope',return_value=scope):
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
        scope={'line_ids':['L'],'is_merged_scope':False}
        with patch.object(api,'_scope',return_value=scope),patch.object(api,'scoped_record',return_value=self.plan):
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

    def test_registered_line_and_two_line_scope_use_same_canonical_line(self):
        device = Row(name='D', device_name='Tablet', company='C', factory='F', line='B')
        lines = [Row(name='B', line_code='316', line_name='C2X3'), Row(name='A', line_code='315', line_name='C1X3')]

        def get_value(doctype, name, fields=None, **kwargs):
            if doctype == 'Production Line':
                return Row(name=name, company='C', factory='F', line_code='316' if name == 'B' else '315', line_name=name)
            if doctype == 'Line Group':
                return Row(company='C', factory='F', is_active=1)
            return None

        def get_all(doctype, **kwargs):
            if doctype == 'Production Line':
                return lines
            if doctype == 'Line Group Assignment' and 'line' in kwargs['filters']:
                return [Row(line_group='G')]
            if doctype == 'Line Group Assignment':
                return [Row(line='A'), Row(line='B')]
            return []

        with patch.object(frappe.db, 'get_value', side_effect=get_value), patch.object(frappe, 'get_all', side_effect=get_all), patch.object(api, 'device_for', return_value=device):
            actual = api.check_device('D')
        self.assertEqual('B', actual['line'])
        self.assertEqual('A', actual['canonical_line'])
        self.assertEqual(['B', 'A'], actual['scope_lines'])
        self.assertTrue(actual['is_merged_scope'])

    def test_deleted_group_is_excluded_from_merged_scope(self):
        lines = [Row(name='A', line_code='315', line_name='C1X3'), Row(name='B', line_code='316', line_name='C2X3')]

        def get_value(doctype, name, fields=None, **kwargs):
            if doctype == 'Production Line':
                return Row(name='B', company='C', factory='F', line_code='316', line_name='C2X3', is_deleted=0)
            if doctype == 'Line Group':
                return Row(company='C', factory='F', is_active=1, is_deleted=int(name == 'OLD'),
                           group_code=name, group_name=name)
            return None

        def get_all(doctype, **kwargs):
            filters = kwargs['filters']
            if doctype == 'Line Group Assignment':
                self.assertEqual(0, filters['is_deleted'])
                return ([Row(line_group='G'), Row(line_group='OLD')] if 'line' in filters
                        else [Row(line='A'), Row(line='B')])
            if doctype == 'Production Line':
                self.assertEqual(0, filters['is_deleted'])
                return lines
            return []

        with patch.object(frappe, 'get_meta', return_value=Row(has_field=lambda field: field == 'is_deleted'), create=True), \
                patch.object(frappe.db, 'get_value', side_effect=get_value), \
                patch.object(frappe, 'get_all', side_effect=get_all):
            scope = merged_scope.resolve_scope('C', 'F', 'B')
        self.assertEqual('G', scope['line_group'])
        self.assertEqual('A', scope['canonical_line'])
        self.assertEqual(['B', 'A'], scope['line_ids'])
        self.assertTrue(scope['is_merged_scope'])

    def test_multiple_active_groups_return_named_configuration_error(self):
        def get_value(doctype, name, fields=None, **kwargs):
            if doctype == 'Production Line':
                return Row(name='B', company='C', factory='F', line_code='316', line_name='C2X3')
            if doctype == 'Line Group':
                return Row(company='C', factory='F', is_active=1, group_code=name, group_name=name)
            return None

        frappe.local.response = Row()
        try:
            with patch.object(frappe.db, 'get_value', side_effect=get_value), \
                    patch.object(frappe, 'get_all', return_value=[Row(line_group='G1'), Row(line_group='G2')]), \
                    self.assertRaisesRegex(merged_scope.MultipleLineGroupsError, 'C2X3.*G1, G2'):
                merged_scope.resolve_scope('C', 'F', 'B')
            self.assertEqual('multiple_line_groups', frappe.local.response['productivity_error_code'])
        finally:
            frappe.local.pop('response', None)

    def test_plan_save_uses_pair_canonical_line_even_from_other_member(self):
        device = Row(name='D', company='C', factory='F', line='B')
        scope = {'company': 'C', 'factory': 'F', 'line_ids': ['A', 'B'], 'line_group': 'G',
                 'canonical_line': 'A', 'is_merged_scope': True}
        doc = MagicMock()
        doc.is_new.return_value = True
        doc.as_dict.return_value = {'name': 'P1', 'line': 'A'}
        with patch.object(api, '_scope', return_value=scope), patch.object(frappe.db, 'exists', return_value=False), patch.object(frappe, 'new_doc', return_value=doc, create=True):
            result = api._save(api.PLAN, device, {'name': '00000000-0000-0000-0000-000000000001',
                'line': 'B', 'product': 'X', 'line_start_date': '2026-11-01',
                'shipment_date': '2026-11-05', 'planned_quantity': 10})
        self.assertEqual('A', doc.line)
        self.assertEqual('G', doc.line_group)
        self.assertEqual('A', result['line'])
        doc.insert.assert_called_once_with(ignore_permissions=True)

    def test_two_line_repair_consolidates_conflicts_and_is_idempotent(self):
        scope = {'company': 'C', 'factory': 'F', 'line_group': 'G', 'line_ids': ['A', 'B'],
                 'canonical_line': 'A', 'is_merged_scope': True}
        plans = [
            Row(name='P1', line='A', product='X', line_start_date='2026-11-01', shipment_date='2026-11-05', closed_production_date=None, line_group='G', line_snapshot_type='group', modified='2026-11-01'),
            Row(name='P2', line='B', product='Y', line_start_date='2026-11-02', shipment_date='2026-11-04', closed_production_date=None, line_group=None, line_snapshot_type='line', modified='2026-11-02'),
            Row(name='P3', line='B', product='Z', line_start_date='2026-11-06', shipment_date='2026-11-10', closed_production_date=None, line_group=None, line_snapshot_type='line', modified='2026-11-06'),
        ]
        reports = [
            Row(name='R1', line='A', production_date='2026-11-03', production_plan='P1', product='X', line_group='G', line_snapshot_type='group', modified='2026-11-03'),
            Row(name='R2', line='B', production_date='2026-11-03', production_plan='P2', product='Y', line_group=None, line_snapshot_type='line', modified='2026-11-04'),
            Row(name='R3', line='B', production_date='2026-11-07', production_plan='P3', product='Z', line_group=None, line_snapshot_type='line', modified='2026-11-07'),
        ]
        infos = [Row(name='I1', line='A', modified='2026-11-01'), Row(name='I2', line='B', modified='2026-11-02')]
        sources = {api.PLAN: plans, api.REPORT: reports, api.LINE_INFO: infos}

        def records(doctype, *_):
            return [row for row in sources[doctype] if not row.get('is_deleted')]

        with patch.object(merged_scope, '_records', side_effect=records), patch.object(frappe.db, 'sql'), patch.object(frappe.db, 'set_value'):
            self.assertTrue(merged_scope.repair_scope(scope))
            self.assertFalse(merged_scope.repair_scope(scope))
        self.assertEqual(1, plans[1].is_deleted)
        self.assertEqual('A', plans[2].line)
        self.assertEqual(1, reports[1].is_deleted)
        self.assertEqual(('A', 'P3', 'Z'), (reports[2].line, reports[2].production_plan, reports[2].product))
        self.assertEqual(1, infos[1].is_deleted)

    def test_old_queued_plan_id_resolves_through_transitive_overlap(self):
        scope = {'company': 'C', 'factory': 'F', 'line_ids': ['A', 'B'],
                 'canonical_line': 'A', 'is_merged_scope': True}
        candidates = [
            Row(name='P1', line='A', line_start_date='2026-11-01', shipment_date='2026-11-03', closed_production_date=None, is_deleted=0, modified_by=None),
            Row(name='P2', line='B', line_start_date='2026-11-03', shipment_date='2026-11-05', closed_production_date=None, is_deleted=1, modified_by=merged_scope.REPAIR_ACTOR),
            Row(name='P3', line='B', line_start_date='2026-11-05', shipment_date='2026-11-07', closed_production_date=None, is_deleted=1, modified_by=merged_scope.REPAIR_ACTOR),
        ]
        with patch.object(frappe.db, 'get_value', return_value=candidates[2]), patch.object(frappe, 'get_all', return_value=candidates):
            self.assertEqual('P1', merged_scope.resolve_merged_alias(api.PLAN, 'P3', scope))


if __name__=='__main__':
    unittest.main()
