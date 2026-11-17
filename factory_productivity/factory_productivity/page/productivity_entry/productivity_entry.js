frappe.pages['productivity-entry'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Productivity Entry'), single_column: true });
    const storage = 'factory_productivity_offline_v1';
    const state = JSON.parse(localStorage.getItem(storage) || '{"device_id":"","operations":[],"plans":[],"reports":[],"bootstrap":{}}');
    const persist = () => localStorage.setItem(storage, JSON.stringify(state));
    const device = page.add_field({ fieldtype: 'Data', fieldname: 'device_id', label: __('Device ID'), default: state.device_id, change: refresh });
    const area = $('<div></div>').appendTo(page.body);
    const status = $('<p class="text-muted"></p>').appendTo(area);
    const actions = $('<div class="mb-3"></div>').appendTo(area);
    const records = $('<div></div>').appendTo(area);
    $('<button class="btn btn-primary mr-2"></button>').text(__('New Plan')).on('click', newPlan).appendTo(actions);
    $('<button class="btn btn-default mr-2"></button>').text(__('New Report')).on('click', newReport).appendTo(actions);
    $('<button class="btn btn-default"></button>').text(__('Sync')).on('click', sync).appendTo(actions);
    page.set_primary_action(__('Refresh'), refresh);
    window.addEventListener('online', sync);
    if ('serviceWorker' in navigator) {
        const manifest = document.createElement('link');
        manifest.rel = 'manifest';
        manifest.href = '/assets/factory_productivity/productivity.webmanifest';
        document.head.appendChild(manifest);
        navigator.serviceWorker.register('/productivity-sw.js', { scope: '/app/productivity-entry' }).catch(() => {});
    }

    function render() {
        status.text(`${navigator.onLine ? __('Online') : __('Offline')} · ${__('Pending operations')}: ${state.operations.length}`);
        records.empty();
        for (const [title, rows, columns] of [
            [__('Plans'), state.plans, ['line', 'product', 'planned_quantity', 'shipment_date']],
            [__('Reports'), state.reports, ['line', 'product', 'production_date', 'daily_target_quantity']]
        ]) {
            const section = $('<div class="frappe-card p-3 mb-3"></div>').appendTo(records);
            $('<h4></h4>').text(title).appendTo(section);
            const table = $('<table class="table table-bordered"><thead></thead><tbody></tbody></table>').appendTo(section);
            const head = $('<tr></tr>').appendTo(table.find('thead'));
            for (const key of columns) $('<th></th>').text(__(key)).appendTo(head);
            for (const row of rows) {
                const tr = $('<tr></tr>').appendTo(table.find('tbody'));
                for (const key of columns) $('<td></td>').text(row[key] == null ? '' : row[key]).appendTo(tr);
            }
        }
    }

    async function call(method, args) {
        const result = await frappe.call({ method: `factory_productivity.api.${method}`, args });
        return result.message;
    }

    async function refresh() {
        state.device_id = device.get_value() || '';
        persist();
        render();
        if (!state.device_id || !navigator.onLine) return;
        try {
            state.bootstrap = await call('bootstrap', { device_id: state.device_id });
            const [plans, reports] = await Promise.all([
                call('list_plans', { device_id: state.device_id, page_size: 200 }),
                call('list_reports', { device_id: state.device_id, page_size: 200 })
            ]);
            state.plans = plans.items;
            state.reports = reports.items;
            persist(); render();
        } catch (error) {
            frappe.msgprint(__('Could not load data.'));
        }
    }

    function queue(action, values) {
        const operation_id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
        values.name = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16); });
        state.operations.push({ operation_id, action, values });
        if (action === 'save_plan') state.plans.unshift(values);
        if (action === 'save_report') state.reports.unshift(values);
        persist(); render();
        if (navigator.onLine) sync();
    }

    async function sync() {
        if (!navigator.onLine || !state.device_id || !state.operations.length) return;
        try {
            const response = await call('sync_batch', { device_id: state.device_id, operations: state.operations });
            const succeeded = new Set(response.results.filter(row => row.success).map(row => row.operation_id));
            state.operations = state.operations.filter(row => !succeeded.has(row.operation_id));
            persist(); render();
            if (!state.operations.length) await refresh();
        } catch (error) {
            frappe.msgprint(__('Could not sync data.'));
        }
    }

    function newPlan() {
        const dialog = new frappe.ui.Dialog({ title: __('New Plan'), fields: [
            { fieldtype: 'Select', fieldname: 'line', label: __('Production Line'), options: (state.bootstrap.lines || []).map(row => row.name).join('\n'), reqd: 1, default: state.bootstrap.device?.line },
            { fieldtype: 'Select', fieldname: 'product', label: __('Product'), options: (state.bootstrap.products || []).map(row => row.name).join('\n'), reqd: 1 },
            { fieldtype: 'Date', fieldname: 'line_start_date', label: __('Line Start Date'), reqd: 1, default: frappe.datetime.get_today() },
            { fieldtype: 'Date', fieldname: 'shipment_date', label: __('Shipment Date'), reqd: 1 },
            { fieldtype: 'Int', fieldname: 'planned_quantity', label: __('Planned Quantity'), reqd: 1 }
        ], primary_action_label: __('Save'), primary_action(values) { queue('save_plan', values); dialog.hide(); } });
        dialog.show();
    }

    function newReport() {
        const dialog = new frappe.ui.Dialog({ title: __('New Report'), fields: [
            { fieldtype: 'Select', fieldname: 'line', label: __('Production Line'), options: (state.bootstrap.lines || []).map(row => row.name).join('\n'), reqd: 1, default: state.bootstrap.device?.line },
            { fieldtype: 'Select', fieldname: 'production_plan', label: __('Production Plan'), options: state.plans.map(row => row.name).join('\n'), reqd: 1 },
            { fieldtype: 'Select', fieldname: 'product', label: __('Product'), options: (state.bootstrap.products || []).map(row => row.name).join('\n'), reqd: 1 },
            { fieldtype: 'Date', fieldname: 'production_date', label: __('Production Date'), reqd: 1, default: frappe.datetime.get_today() },
            { fieldtype: 'Int', fieldname: 'daily_target_quantity', label: __('Daily Target Quantity'), reqd: 1 },
            { fieldtype: 'Float', fieldname: 'working_hours', label: __('Working Hours'), reqd: 1 },
            { fieldtype: 'Int', fieldname: 'worker_count', label: __('Worker Count'), reqd: 1 },
            { fieldtype: 'Int', fieldname: 'ironing_delivery_quantity', label: __('Ironing Delivery Quantity'), reqd: 1 },
            { fieldtype: 'Table', fieldname: 'time_slots', label: __('Time Slots'),
              fields: [{ fieldtype: 'Select', fieldname: 'time_slot', label: __('Time Slot'), options: (state.bootstrap.time_slots || []).map(row => row.name).join('\n'), in_list_view: 1, reqd: 1 },
                       { fieldtype: 'Int', fieldname: 'finished_quantity', label: __('Finished Quantity'), in_list_view: 1, reqd: 1 }] }
        ], primary_action_label: __('Save'), primary_action(values) { queue('save_report', values); dialog.hide(); } });
        dialog.show();
    }

    render();
    if (navigator.onLine && state.device_id) refresh().then(sync);
};
