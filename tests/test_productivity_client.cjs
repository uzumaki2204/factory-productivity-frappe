const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const texts = JSON.parse(fs.readFileSync(path.join(root, 'factory_productivity/i18n.json'), 'utf8')).vi;
const script = fs.readFileSync(path.join(root, 'factory_productivity/public/js/productivity.js'), 'utf8')
    .replace('updateStatus(); refresh().then(sync);', 'globalThis.appUnderTest = { state, sync, saveWithConfirmation };');

function start(initial, reply) {
    const elements = new Map();
    const storage = { current: JSON.stringify(initial) };
    const field = () => ({ value: '', addEventListener() {} });
    function element(selector) {
        if (!elements.has(selector)) {
            const fields = new Map();
            elements.set(selector, {
                textContent: '', innerHTML: '', hidden: false, open: false, dataset: {},
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
        localStorage: { getItem: () => storage.current, setItem(_, value) { storage.current = value; } },
        navigator: { onLine: true },
        location: { origin: 'http://test.local' },
        window: { addEventListener() {} },
        crypto: { randomUUID: () => 'generated-id' },
        URL,
        setTimeout: () => 1,
        clearTimeout() {},
        fetch: async (url, options) => ({ ok: true, json: async () => ({ message: reply(url.pathname.split('.').pop(), options) }) }),
    };
    vm.createContext(context);
    vm.runInContext(script, context);
    return { app: context.appUnderTest, element, storage };
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
    assert.equal(element('#failed-button').textContent, '1 cần sửa');
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
