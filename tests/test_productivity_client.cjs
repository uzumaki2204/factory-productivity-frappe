const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const texts = JSON.parse(fs.readFileSync(path.join(root, 'factory_productivity/i18n.json'), 'utf8')).vi;
const script = fs.readFileSync(path.join(root, 'factory_productivity/public/js/productivity.js'), 'utf8')
    .replace('updateStatus(); refresh().then(sync);', 'globalThis.appUnderTest = { state, sync, saveWithConfirmation, slotName, editing, refresh };');

function start(initial, reply) {
    const elements = new Map();
    const storage = { current: JSON.stringify(initial) };
    const field = () => ({ value: '', addEventListener() {} });
    function element(selector) {
        if (!elements.has(selector)) {
            const fields = new Map();
            elements.set(selector, {
                textContent: '', innerHTML: '', hidden: selector === '#reports-view' || selector === '#line-info-view' || selector === '#line-info-form', open: false, dataset: {},
                classList: { add() {}, remove() {}, toggle() {} },
                elements: new Proxy({}, { get(_, name) { if (!fields.has(name)) fields.set(name, field()); return fields.get(name); } }),
                handlers: {},
                addEventListener(type, handler) { this.handlers[type] = handler; },
                removeAttribute() {}, setAttribute() {}, showModal() {}, close() {}, focus() {},
            });
        }
        return elements.get(selector);
    }
    const context = {
        document: {
            getElementById(id) {
                if (id === 'productivity-app') return { dataset: { lang: 'vi' } };
                if (id === 'productivity-texts') return { textContent: JSON.stringify(texts) };
                return element(`#${id}`);
            },
            querySelector: element,
            querySelectorAll: () => [],
        },
        localStorage: {
            getItem(key) { return key === 'factory_productivity_offline_v1' ? storage.current : storage[key] ?? null; },
            setItem(key, value) { if (key === 'factory_productivity_offline_v1') storage.current = value; else storage[key] = value; },
        },
        navigator: { onLine: true },
        location: { origin: 'http://test.local' },
        window: { addEventListener() {} },
        crypto: { randomUUID: () => 'generated-id' },
        URL,
        setTimeout: () => 1,
        clearTimeout() {},
        fetch: async (url, options) => {
            const result = reply(url.pathname.split('.').pop(), options);
            return result?.__error
                ? { ok: false, json: async () => result.payload || ({ exc: result.exc, exc_type: result.exc_type,
                    productivity_error_code: result.code, message: result.message }) }
                : { ok: true, json: async () => ({ message: result }) };
        },
    };
    vm.createContext(context);
    vm.runInContext(script, context);
    return { app: context.appUnderTest, element, storage, navigator: context.navigator };
}

test('online validation failure keeps the form open and creates no pending record', async () => {
    const { app, element } = start({ device_id: 'DEV', operations: [], plans: [], reports: [], bootstrap: {} }, (method, options) => {
        assert.equal(method, 'sync_batch');
        const request = JSON.parse(options.body);
        assert.equal(request.lang, 'vi');
        return { results: [{ operation_id: request.operations[0].operation_id, success: false, message: 'Chuyền đã có kế hoạch đang mở.' }] };
    });
    const submit = { disabled: false };
    const form = { hidden: false, querySelector: () => submit };
    await app.saveWithConfirmation('save_plan', { name: 'DRAFT', line: 'L', product: 'BAD' }, form);
    assert.equal(form.hidden, false);
    assert.equal(submit.disabled, false);
    assert.equal(app.state.operations.length, 0);
    assert.equal(app.state.plans.length, 0);
    assert.equal(element('#notice').textContent, 'Chuyền đã có kế hoạch đang mở.');
});

test('an existing open plan blocks a second plan before it reaches the queue', async () => {
    const existing = { name: 'EXISTING', line: 'L', product: 'GOOD', closed_production_date: null, is_deleted: 0 };
    const { app, element } = start({ device_id: 'DEV', operations: [], plans: [existing], reports: [], bootstrap: {} }, () => {
        throw new Error('The server should not be called for a known conflict');
    });
    const form = element('#plan-form');
    form.elements.product.value = 'BAD';
    form.elements.line.value = 'L';
    form.elements.line_start_date.value = '2026-11-20';
    form.elements.shipment_date.value = '2026-11-30';
    form.elements.planned_quantity.value = '100';
    await form.handlers.submit({ preventDefault() {}, currentTarget: form });
    assert.equal(app.state.operations.length, 0);
    assert.equal(app.state.plans.length, 1);
    assert.equal(form.hidden, false);
    assert.equal(element('#notice').textContent, 'Chuyền đã có kế hoạch đang mở.');
});

test('rejected offline plan leaves the queue and server list immediately', async () => {
    const draft = { name: 'DRAFT', line: 'L', product: 'BAD', line_start_date: '2026-11-20', shipment_date: '2026-11-30' };
    const existing = { name: 'EXISTING', line: 'L', product: 'GOOD', line_start_date: '2026-11-20', shipment_date: '2026-11-30', planned_quantity: 100 };
    const { app, element, storage } = start({ device_id: 'DEV', operations: [{ operation_id: 'OP1', action: 'save_plan', values: draft }], plans: [draft], reports: [], bootstrap: {} }, method => {
        if (method === 'sync_batch') return { results: [{ operation_id: 'OP1', success: false, message: 'Chuyền đã có kế hoạch đang mở.' }] };
        if (method === 'bootstrap') return { device: { line: 'L' }, lines: [], products: [], time_slots: [] };
        if (method === 'list_plans') return { items: [existing], total: 1 };
        if (method === 'list_reports') return { items: [], total: 0 };
        throw new Error(`Unexpected method: ${method}`);
    });
    await app.sync();
    assert.equal(app.state.operations.length, 0);
    assert.equal(app.state.failed.length, 1);
    assert.equal(app.state.plans.length, 1);
    assert.equal(app.state.plans[0].name, 'EXISTING');
    assert.equal(element('#pending-count').textContent, '');
    assert.equal(element('#failed-button').title, '1 cần sửa');
    assert.match(element('#plans-list').innerHTML, /GOOD/);
    assert.doesNotMatch(element('#plans-list').innerHTML, /BAD/);
    assert.equal(JSON.parse(storage.current).operations.length, 0);
});

test('previously rejected operations are migrated out of the queue', () => {
    const draft = { name: 'DRAFT', line: 'L', product: 'BAD' };
    const { app, storage } = start({ device_id: 'DEV', operations: [{ operation_id: 'OP1', action: 'save_plan', values: draft, failed_message: 'Chuyền đã có kế hoạch đang mở.' }], plans: [draft], reports: [], bootstrap: {} }, () => {
        throw new Error('Rejected operations must not be retried automatically');
    });
    assert.equal(app.state.operations.length, 0);
    assert.equal(app.state.failed.length, 1);
    assert.equal(app.state.plans.length, 0);
    assert.equal(JSON.parse(storage.current).operations.length, 0);
});

test('time slot labels show the configured start and end without duplicating existing hours', () => {
    const slots = [
        { name: 'S1', slot_name: 'Ca 1', start_time: '07:30:00', end_time: '09:30:00' },
        { name: 'S2', slot_name: 'Ca 2 (09:30-11:30)', start_time: '09:30:00', end_time: '11:30:00' },
        { name: 'S3', slot_name: 'Ca 3', start_time: '', end_time: '' },
    ];
    const { app } = start({ device_id: 'DEV', operations: [], plans: [], reports: [], bootstrap: { time_slots: slots } }, () => {});
    assert.equal(app.slotName('S1'), 'Ca 1 (07:30–09:30)');
    assert.equal(app.slotName('S2'), 'Ca 2 (09:30–11:30)');
    assert.equal(app.slotName('S3'), 'Ca 3');
});

test('scope conflict blocks stale rows and recovers to the merged line display', async () => {
    let conflict = true;
    const initial = { device_id: 'DEV', operations: [], failed: [],
        plans: [{ name: 'OLD', line: 'B', product: 'P' }], reports: [],
        bootstrap: { device: { line: 'B', is_merged_scope: true, scope_lines: ['A', 'B'] },
            lines: [{ name: 'A', line_name: 'C1X3' }, { name: 'B', line_name: 'C2X3' }] } };
    const { app, element } = start(initial, method => {
        if (method === 'bootstrap') {
            return conflict
                ? { __error: true, code: 'multiple_line_groups', message: 'Chuyền C2X3 đang thuộc nhóm G1, G2.' }
                : { device: { name: 'Tablet', line: 'B', canonical_line: 'A',
                    scope_lines: ['B', 'A'], is_merged_scope: true },
                    lines: [{ name: 'A', line_name: 'C1X3' }, { name: 'B', line_name: 'C2X3' }],
                    products: [], time_slots: [] };
        }
        if (method === 'list_plans' || method === 'list_reports') return { items: [], total: 0 };
        throw new Error(`Unexpected method: ${method}`);
    });
    element('#plans-list').innerHTML = 'stale';
    await app.refresh();
    assert.equal(element('#scope-error').hidden, false);
    assert.match(element('#scope-error').textContent, /G1, G2/);
    assert.equal(element('#plans-list').innerHTML, '');
    assert.equal(element('#new-plan').disabled, true);
    assert.equal(element('#line-info-form').hidden, true);
    assert.equal(app.state.plans[0].name, 'OLD');

    conflict = false;
    await app.refresh();
    assert.equal(element('#scope-error').hidden, true);
    assert.equal(element('#new-plan').disabled, false);
    assert.equal(element('#line-info-form').hidden, false);
    assert.match(element('#device-scope-value').value, /C2X3 \+ C1X3/);
    assert.equal(element('#plan-line-field').hidden, true);
});

for (const [responseName, payload] of [
    ['Frappe v1', { exc_type: 'MultipleLineGroupsError',
        _server_messages: JSON.stringify([JSON.stringify({ message: 'Chuyền C2X1 thuộc G1, G2.' })]) }],
    ['Frappe v2', { errors: [{ type: 'MultipleLineGroupsError', message: 'Chuyền C2X1 thuộc G1, G2.' }] }],
    ['server error without a code', { message: 'Không tải được phạm vi chuyền.' }],
]) {
    test(`${responseName} blocks forms and pending writes when bootstrap fails`, async () => {
        const { app, element } = start({ device_id: 'DEV', operations: [], plans: [], reports: [], bootstrap: {} }, method => {
            assert.equal(method, 'bootstrap');
            return { __error: true, payload };
        });
        await app.refresh();
        assert.equal(element('#scope-error').hidden, false);
        assert.equal(element('#line-info-form').hidden, true);
        assert.equal(element('#new-plan').disabled, true);
        element('#line-info-form').handlers.submit({ preventDefault() {}, currentTarget: element('#line-info-form') });
        assert.equal(app.state.operations.length, 0);
    });
}

test('saving a report online keeps it open for updates to the same record', async () => {
    const sentNames = [];
    const { app, element } = start({ device_id: 'DEV', operations: [], plans: [], reports: [], bootstrap: {} }, (method, options) => {
        if (method === 'sync_batch') {
            const operation = JSON.parse(options.body).operations[0];
            sentNames.push(operation.values.name);
            return { results: [{ operation_id: operation.operation_id, success: true, data: { name: operation.values.name } }] };
        }
        if (method === 'bootstrap') return { device: { line: 'L' }, lines: [], products: [], time_slots: [] };
        if (method === 'list_plans' || method === 'list_reports') return { items: [], total: 0 };
        throw new Error(`Unexpected method: ${method}`);
    });
    const form = { hidden: false, querySelector: () => ({ disabled: false }) };
    const report = { name: 'REPORT1', line: 'L', product: 'P', production_date: '2026-11-20', time_slots: [{ time_slot: 'S1', finished_quantity: 10 }] };
    await app.saveWithConfirmation('save_report', report, form);
    assert.equal(form.hidden, false);
    assert.equal(app.editing.report, 'REPORT1');
    assert.equal(element('#report-form-title').textContent, 'Sửa báo cáo');
    await app.saveWithConfirmation('save_report', { ...report, time_slots: [{ time_slot: 'S1', finished_quantity: 10 }, { time_slot: 'S2', finished_quantity: 15 }] }, form);
    assert.deepEqual(sentNames, ['REPORT1', 'REPORT1']);
    assert.equal(app.state.operations.length, 0);
});

test('repeated offline report saves update one pending operation and keep the form open', async () => {
    const { app, navigator } = start({ device_id: 'DEV', operations: [], plans: [], reports: [], bootstrap: {} }, () => {
        throw new Error('Offline saves must not call the server');
    });
    navigator.onLine = false;
    const form = { hidden: false };
    const report = { name: 'REPORT1', line: 'L', product: 'P', production_date: '2026-11-20', time_slots: [{ time_slot: 'S1', finished_quantity: 10 }] };
    await app.saveWithConfirmation('save_report', report, form);
    assert.equal(form.hidden, false);
    assert.equal(app.editing.report, 'REPORT1');
    await app.saveWithConfirmation('save_report', { ...report, time_slots: [{ time_slot: 'S1', finished_quantity: 10 }, { time_slot: 'S2', finished_quantity: 15 }] }, form);
    assert.equal(app.state.operations.length, 1);
    assert.equal(app.state.operations[0].values.time_slots[1].finished_quantity, 15);
    assert.equal(form.hidden, false);
});

test('report product picker filters active codes by customer and season without a plan', () => {
    const products = [
        { name: 'P1', product_code: '217H001B', customer: 'C1', production_season: 'S1' },
        { name: 'P2', product_code: '217H002B', customer: 'C1', production_season: 'S2' },
        { name: 'P3', product_code: '317H001A', customer: 'C2', production_season: 'S1' },
    ];
    const { element, storage } = start({ device_id: 'DEV', operations: [], plans: [], reports: [], bootstrap: {
        products, customers: [{ name: 'C1', customer_code: 'UNIQLO' }, { name: 'C2', customer_code: 'OTHER' }],
        seasons: [{ name: 'S1', season_code: '2027SS' }, { name: 'S2', season_code: '2027FW' }],
    } }, () => {});
    element('#report-product-picker-button').handlers.click();
    assert.match(element('#report-customer-filters').innerHTML, /UNIQLO/);
    assert.match(element('#report-season-filters').innerHTML, /2027SS/);
    const selectFilter = value => ({ target: { closest: () => ({ dataset: { filterValue: value } }) } });
    element('#report-customer-filters').handlers.click(selectFilter('C1'));
    element('#report-season-filters').handlers.click(selectFilter('S1'));
    assert.match(element('#report-product-grid').innerHTML, /217H001B/);
    assert.doesNotMatch(element('#report-product-grid').innerHTML, /217H002B|317H001A/);
    element('#report-product-grid').handlers.click({ target: { closest: () => ({ dataset: { productId: 'P1' } }) } });
    assert.equal(element('#report-form').elements.product.value, 'P1');
    assert.equal(element('#report-form').elements.production_plan.value, '');
    assert.equal(element('#report-product-picker-value').textContent, '217H001B');
    assert.deepEqual(JSON.parse(storage.factory_productivity_recent_products_DEV), ['P1']);
});
