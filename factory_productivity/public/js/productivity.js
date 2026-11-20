(() => {
    'use strict';
    const root = document.getElementById('productivity-app');
    if (!root) return;
    const texts = JSON.parse(document.getElementById('productivity-texts').textContent);
    const storageKey = 'factory_productivity_offline_v1';
    const blank = { device_id: '', operations: [], failed: [], plans: [], reports: [], bootstrap: {} };
    let state;
    try { state = { ...blank, ...JSON.parse(localStorage.getItem(storageKey) || '{}') }; }
    catch (_) { state = { ...blank }; }
    if (!Array.isArray(state.operations)) state.operations = [];
    if (!Array.isArray(state.failed)) state.failed = [];
    if (!Array.isArray(state.plans)) state.plans = [];
    if (!Array.isArray(state.reports)) state.reports = [];
    if (!state.bootstrap || typeof state.bootstrap !== 'object') state.bootstrap = {};
    const pages = { plans: { page: 1, total: state.plans.length }, reports: { page: 1, total: state.reports.length } };
    const rows = { plans: state.plans, reports: state.reports };
    let availablePlans = [];
    let activeReportRow = null;
    let planRequest = 0;
    let editing = { plan: null, report: null, line: null };
    let syncing = false;
    const refreshSequence = { plans: 0, reports: 0 };
    const $ = (selector, base = document) => base.querySelector(selector);
    const $$ = (selector, base = document) => Array.from(base.querySelectorAll(selector));
    const t = (key, values = {}) => (texts[key] || key).replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ''));
    const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
    const persist = () => localStorage.setItem(storageKey, JSON.stringify(state));
    const previouslyRejected = state.operations.filter(operation => operation.failed_message);
    if (previouslyRejected.length) {
        state.failed.push(...previouslyRejected);
        state.operations = state.operations.filter(operation => !operation.failed_message);
        for (const operation of previouslyRejected) {
            const kind = operation.action === 'save_plan' ? 'plans' : operation.action === 'save_report' ? 'reports' : null;
            if (kind) state[kind] = state[kind].filter(row => row.name !== operation.values.name);
        }
        persist();
    }
    const id = () => (crypto.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const n = Math.random() * 16 | 0; return (c === 'x' ? n : (n & 3 | 8)).toString(16); }));
    const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
    const allPlans = () => {
        const plans = new Map(state.plans.map(plan => [plan.name, plan]));
        state.failed.filter(operation => operation.action === 'save_plan').forEach(operation => plans.delete(operation.values.name));
        state.operations.filter(o => o.action === 'save_plan').forEach(operation => {
            plans.set(operation.values.name, operation.values);
        });
        return [...plans.values()];
    };
    const productCode = name => { const p = (state.bootstrap.products || []).find(x => x.name === name); return p ? (p.product_code || p.name) : (name || ''); };
    const lineName = name => { const l = (state.bootstrap.lines || []).find(x => x.name === name); return l ? `${l.line_code || l.name}${l.line_name ? ` · ${l.line_name}` : ''}` : (name || ''); };
    const slotTime = value => {
        const parts = String(value ?? '').match(/^(\d{1,2}):(\d{2})/);
        return parts ? `${parts[1].padStart(2, '0')}:${parts[2]}` : '';
    };
    const slotName = name => {
        const slot = (state.bootstrap.time_slots || []).find(item => item.name === name);
        if (!slot) return name || '';
        const label = slot.slot_name || slot.name;
        const start = slotTime(slot.start_time), end = slotTime(slot.end_time);
        if (!start || !end) return label;
        const plainLabel = label.replace(/\s*\(\s*\d{1,2}:\d{2}\s*[-–—]\s*\d{1,2}:\d{2}\s*\)\s*$/, '').trim();
        if (plainLabel === label && label.includes(start) && label.includes(end)) return label;
        return `${plainLabel} (${start}–${end})`;
    };
    const notice = (message, kind = 'info') => { const el = $('#notice'); el.textContent = message; el.className = `alert alert-${kind}`; el.hidden = false; clearTimeout(notice.timer); notice.timer = setTimeout(() => { el.hidden = true; }, 7000); };
    const errorMessage = error => error?.message || t('ui.operation_failed');

    async function call(method, args = {}, post = false) {
        const url = new URL(`/api/method/factory_productivity.api.${method}`, location.origin);
        if (!post) for (const [key, value] of Object.entries(args)) if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
        let response;
        try { response = await fetch(url, { method: post ? 'POST' : 'GET', credentials: 'omit', cache: 'no-store', headers: { ...(post ? { 'Content-Type': 'application/json' } : {}), 'X-Productivity-Lang': root.dataset.lang || 'vi' }, body: post ? JSON.stringify(args) : undefined }); }
        catch (_) { const error = new Error(t('ui.offline')); error.network = true; throw error; }
        let payload;
        try { payload = await response.json(); } catch (_) { throw new Error(t('ui.operation_failed')); }
        if (!response.ok || payload.exc) {
            let msg = payload._server_messages;
            try { msg = JSON.parse(msg || '[]').map(x => JSON.parse(x).message).filter(Boolean).join(' '); } catch (_) { msg = ''; }
            throw new Error(msg || payload.message || t('ui.operation_failed'));
        }
        return payload.message;
    }

    function updateStatus() {
        const online = navigator.onLine;
        $('#connection-status').textContent = t(online ? 'ui.online' : 'ui.offline');
        $('#connection-status').className = `indicator-pill ${online ? 'green' : 'orange'}`;
        $('#pending-count').textContent = state.operations.length ? `(${state.operations.length} ${t('ui.pending_label')})` : '';
        $('#failed-button').hidden = !state.failed.length;
        $('#failed-button').textContent = t('ui.failed_drafts', { count: state.failed.length });
        renderDeviceIdentity();
    }

    function renderDeviceIdentity() {
        const active = !!state.device_id;
        const name = state.bootstrap.device?.name || '';
        $('#device-name').hidden = !active || !name;
        $('#device-name').textContent = name;
        $('#device-active-info').hidden = !active;
        $('#device-help').hidden = active;
        $('#device-form').hidden = active;
        $('#device-name-value').textContent = name || t('ui.device_name_unknown');
        $('#device-id-value').textContent = state.device_id;
        $('#device-id').value = active ? state.device_id : '';
    }

    function renderFailedDrafts() {
        $('#failed-drafts-list').innerHTML = state.failed.map((operation, index) => {
            const kind = operation.action === 'save_plan' ? 'ui.plans' : operation.action === 'save_report' ? 'ui.reports' : 'ui.line_info';
            const title = operation.values.product ? productCode(operation.values.product) : lineName(operation.values.line);
            return `<div class="productivity-failed-draft"><strong>${esc(t(kind))} · ${esc(title)}</strong><p>${esc(operation.failed_message || t('ui.sync_failed'))}</p><div class="productivity-card-actions"><button class="btn btn-primary btn-sm" type="button" data-failed-index="${index}">${esc(t('ui.edit'))}</button><button class="btn btn-default btn-sm" type="button" data-discard-index="${index}">${esc(t('ui.discard_draft'))}</button></div></div>`;
        }).join('');
    }

    function setView(view) {
        $$('.productivity-view').forEach(el => { el.hidden = el.id !== `${view}-view`; });
        $$('.productivity-nav-button').forEach(el => { const selected = el.dataset.view === view; el.classList.toggle('active', selected); el.setAttribute('aria-current', selected ? 'page' : 'false'); });
        if (view === 'line-info') return loadLineInfo();
    }

    function options(target, collection, label, selected) {
        target.innerHTML = `<option value="">${esc(t('ui.select'))}</option>` + collection.map(row => `<option value="${esc(row.name)}">${esc(label(row))}</option>`).join('');
        target.value = selected || '';
    }

    function fillMasters() {
        for (const form of [$('#plan-form'), $('#report-form'), $('#line-info-form')]) options(form.elements.line, state.bootstrap.lines || [], x => lineName(x.name), form.elements.line.value || state.bootstrap.device?.line);
        updatePlanProductPicker();
        $('#plan-line-field').hidden = (state.bootstrap.lines || []).length === 1;
        $('#report-line-field').hidden = (state.bootstrap.lines || []).length === 1;
        $('#report-scope').dataset.singleLine = String($('#report-line-field').hidden);
        if ($('#plan-product-dialog').open) renderPlanProductPicker();
    }

    function updatePlanProductPicker() {
        const input = $('#plan-form').elements.product;
        const product = (state.bootstrap.products || []).find(row => row.name === input.value && row.product_code);
        if (!product) input.value = '';
        $('#plan-product-picker-value').textContent = product?.product_code || t('ui.select_product');
        if (product) $('#plan-product-picker-button').removeAttribute('aria-invalid');
    }

    function renderPlanProductPicker() {
        const products = (state.bootstrap.products || []).filter(row => row.product_code);
        const keyword = $('#plan-product-search').value.trim().toLocaleLowerCase();
        const matching = products.filter(row => row.product_code.toLocaleLowerCase().includes(keyword));
        $('#plan-product-grid').innerHTML = matching.length
            ? matching.map(row => `<button class="btn btn-default productivity-product-card" type="button" data-product-id="${esc(row.name)}" aria-pressed="${row.name === $('#plan-form').elements.product.value}">${esc(row.product_code)}</button>`).join('')
            : `<p class="productivity-empty">${esc(t(products.length ? 'ui.no_matching_products' : 'ui.no_products'))}</p>`;
    }

    function filterValues(kind) {
        const form = $(`#${kind}-filter`);
        return { from_date: form.elements.from_date.value, to_date: form.elements.to_date.value, keyword: form.elements.keyword.value.trim() };
    }

    function offlineRows(kind) {
        const f = filterValues(kind);
        const source = kind === 'plans' ? state.plans : state.reports;
        return source.filter(row => {
            const date = kind === 'plans' ? row.line_start_date : row.production_date;
            const end = kind === 'plans' ? (row.closed_production_date || row.shipment_date) : date;
            const product = (state.bootstrap.products || []).find(x => x.name === row.product);
            const words = `${row.product || ''} ${productCode(row.product)} ${product?.product_name || ''} ${row.line || ''} ${lineName(row.line)}`.toLowerCase();
            return (!f.from_date || end >= f.from_date) && (!f.to_date || date <= f.to_date) && (!f.keyword || words.includes(f.keyword.toLowerCase()));
        });
    }

    async function loadList(kind) {
        const sequence = ++refreshSequence[kind];
        const list = $(`#${kind}-list`);
        list.innerHTML = `<div class="productivity-card productivity-empty">${esc(t('ui.loading'))}</div>`;
        if (!state.device_id) { list.innerHTML = `<div class="productivity-card productivity-empty">${esc(t('ui.device_required'))}</div>`; return; }
        if (navigator.onLine) {
            try {
                const result = await call(kind === 'plans' ? 'list_plans' : 'list_reports', { device_id: state.device_id, page: pages[kind].page, page_size: 10, ...filterValues(kind) });
                if (sequence !== refreshSequence[kind]) return;
                const remote = result.items || [];
                const pending = !Object.values(filterValues(kind)).some(Boolean) && pages[kind].page === 1
                    ? [...new Map(state.operations.filter(o => o.action === (kind === 'plans' ? 'save_plan' : 'save_report'))
                        .map(o => [o.values.name, o.values])).values()]
                    : [];
                rows[kind] = [...pending, ...remote.filter(row => !pending.some(item => item.name === row.name))].slice(0, 10);
                pages[kind].total = (result.total || 0) + pending.filter(item => !remote.some(row => row.name === item.name)).length;
                if (!Object.values(filterValues(kind)).some(Boolean) && pages[kind].page === 1) {
                    state[kind] = [...pending, ...remote.filter(row => !pending.some(item => item.name === row.name))];
                    persist();
                }
            } catch (error) {
                if (sequence !== refreshSequence[kind]) return;
                notice(errorMessage(error), 'danger');
                const offline = offlineRows(kind);
                pages[kind].total = offline.length;
                rows[kind] = offline.slice((pages[kind].page - 1) * 10, pages[kind].page * 10);
            }
        } else {
            const offline = offlineRows(kind);
            pages[kind].total = offline.length;
            rows[kind] = offline.slice((pages[kind].page - 1) * 10, pages[kind].page * 10);
        }
        renderList(kind);
    }

    function field(label, value) { return `<dt>${esc(t(label))}</dt><dd>${esc(value ?? '')}</dd>`; }
    function actionButton(action, row, label, className = 'btn-default', sizeClass = 'btn-sm') { return `<button class="btn ${className} ${sizeClass}" type="button" data-action="${action}" data-name="${esc(row.name)}">${esc(t(label))}</button>`; }
    function renderList(kind) {
        const collection = rows[kind] || [];
        const list = $(`#${kind}-list`);
        if (!collection.length) list.innerHTML = `<div class="productivity-card productivity-empty">${esc(t('ui.no_records'))}</div>`;
        else list.innerHTML = collection.map(row => {
            const plan = kind === 'plans';
            const pending = [...state.operations].reverse().find(o => o.action === (plan ? 'save_plan' : 'save_report') && o.values.name === row.name);
            const status = pending ? `<span class="indicator-pill orange">${esc(t('ui.awaiting_sync'))}</span>` : '';
            const total = (row.time_slots || []).reduce((n, x) => n + Number(x.finished_quantity || 0), 0);
            const closed = !!row.closed_production_date;
            const meta = plan ? `${t('ui.line_start_date')}: ${row.line_start_date || ''} · ${t('ui.shipment_date')}: ${row.shipment_date || ''}` : `${t('ui.production_date')}: ${row.production_date || ''} · ${t('ui.finished_total')}: ${total}`;
            const details = plan ? field('ui.planned_quantity', row.planned_quantity) + field('ui.line_start_date', row.line_start_date) + field('ui.shipment_date', row.shipment_date) + field('ui.closed_date', row.closed_production_date || '') : field('ui.daily_target', row.daily_target_quantity) + field('ui.hours', row.working_hours) + field('ui.worker_count', row.worker_count) + field('ui.ironing_delivery', row.ironing_delivery_quantity);
            const buttons = pending ? actionButton(plan ? 'edit-plan' : 'edit-report', row, 'ui.edit', 'btn-primary') : plan
                ? actionButton('edit-plan', row, 'ui.edit', 'btn-primary', 'productivity-plan-action')
                    + actionButton(closed ? 'reopen-plan' : 'finish-plan', row, closed ? 'ui.reopen' : 'ui.finish', closed ? 'btn-success' : 'btn-warning', 'productivity-plan-action')
                    + (closed ? actionButton('change-date-plan', row, 'ui.change_closed_date') : '')
                    + actionButton('delete-plan', row, 'ui.delete', 'btn-danger', 'productivity-plan-action')
                : actionButton('detail-report', row, 'ui.detail') + actionButton('edit-report', row, 'ui.edit') + actionButton('delete-report', row, 'ui.delete');
            return `<details class="productivity-record"><summary><div class="productivity-record-top"><span class="productivity-record-title">${esc(productCode(row.product))}</span>${status || (plan ? `<span class="indicator-pill ${closed ? 'gray' : 'green'}">${esc(t(closed ? 'ui.closed' : 'ui.open'))}</span>` : `<strong>${esc(total)}</strong>`)}</div><div class="productivity-record-meta"><span>${esc(lineName(row.line))}</span><span>${esc(meta)}</span></div></summary><div class="productivity-record-body"><dl>${details}</dl><div class="productivity-card-actions">${buttons}</div></div></details>`;
        }).join('');
        const pg = pages[kind];
        const count = Math.max(1, Math.ceil(pg.total / 10));
        $(`#${kind}-pagination`).innerHTML = `<button class="btn btn-default btn-sm" type="button" data-page="previous" data-kind="${kind}" ${pg.page <= 1 ? 'disabled' : ''}>${esc(t('ui.previous'))}</button><span>${esc(t('ui.page_count', { page: pg.page, pages: count, total: pg.total }))}</span><button class="btn btn-default btn-sm" type="button" data-page="next" data-kind="${kind}" ${pg.page >= count ? 'disabled' : ''}>${esc(t('ui.next'))}</button>`;
    }

    async function refresh() {
        updateStatus();
        if (!state.device_id) {
            for (const kind of ['plans', 'reports']) $(`#${kind}-list`).innerHTML = `<div class="productivity-card productivity-empty">${esc(t('ui.device_required'))}</div>`;
            if (!$('#device-dialog').open) $('#device-dialog').showModal();
            return;
        }
        if (navigator.onLine) {
            try { state.bootstrap = await call('bootstrap', { device_id: state.device_id }); persist(); fillMasters(); updateStatus(); }
            catch (error) { notice(errorMessage(error), 'danger'); }
        } else { fillMasters(); updateStatus(); }
        await Promise.all([loadList('plans'), loadList('reports')]);
    }

    async function sync() {
        if (syncing || !state.operations.length || !state.device_id || !navigator.onLine) return;
        syncing = true;
        try {
            const pending = [...state.operations];
            const response = await call('sync_batch', { device_id: state.device_id, operations: pending, lang: root.dataset.lang || 'vi' }, true);
            const done = new Set((response.results || []).filter(x => x.success).map(x => x.operation_id));
            const rejected = new Map((response.results || []).filter(x => !x.success).map(x => [x.operation_id, x.message || t('ui.sync_failed')]));
            state.operations = state.operations.filter(operation => !done.has(operation.operation_id) && !rejected.has(operation.operation_id));
            for (const operation of pending.filter(item => rejected.has(item.operation_id))) {
                operation.failed_message = rejected.get(operation.operation_id);
                state.failed = state.failed.filter(item => item.action !== operation.action || item.values.name !== operation.values.name);
                state.failed.push(operation);
                const kind = operation.action === 'save_plan' ? 'plans' : operation.action === 'save_report' ? 'reports' : null;
                if (kind) state[kind] = state[kind].filter(row => row.name !== operation.values.name);
            }
            persist(); updateStatus();
            const failed = (response.results || []).find(x => !x.success);
            if (failed) notice(t('ui.sync_rejected', { reason: failed.message || t('ui.sync_failed') }), 'danger');
            else notice(t('ui.sync_done'), 'success');
            await refresh();
        } catch (error) { notice(errorMessage(error), 'danger'); }
        finally { syncing = false; }
    }

    function queue(action, values, retry = true) {
        values.name = values.name || id();
        state.failed = state.failed.filter(operation => operation.action !== action || operation.values.name !== values.name);
        state.operations = state.operations.filter(o => o.action !== action || o.values.name !== values.name);
        state.operations.push({ operation_id: id(), action, values });
        const kind = action === 'save_plan' ? 'plans' : action === 'save_report' ? 'reports' : null;
        if (kind) {
            const index = state[kind].findIndex(x => x.name === values.name);
            if (index < 0) state[kind].unshift(values);
            else state[kind][index] = { ...state[kind][index], ...values };
            pages[kind].total = Math.max(pages[kind].total, state[kind].length);
            rows[kind] = [...state[kind]].slice(0, 10);
            renderList(kind);
        }
        persist(); updateStatus();
        if (navigator.onLine && retry) sync(); else notice(t('ui.saved_offline'), 'info');
    }

    function continueReport(values, name = values.name) {
        editing.report = name;
        activeReportRow = { ...values, name };
        $('#report-form-title').textContent = t('ui.edit_report');
    }

    async function saveWithConfirmation(action, values, form) {
        const keepReportOpen = action === 'save_report';
        const dependsOnPendingPlan = action === 'save_report' && state.operations.some(operation => operation.action === 'save_plan' && operation.values.name === values.production_plan);
        const replacesPending = state.operations.some(operation => operation.action === action && operation.values.name === values.name);
        if (!navigator.onLine || dependsOnPendingPlan || replacesPending) {
            queue(action, values);
            if (keepReportOpen) continueReport(values);
            else form.hidden = true;
            return;
        }
        const button = form.querySelector('button[type="submit"]');
        button.disabled = true;
        let result;
        try {
            const operation = { operation_id: id(), action, values };
            const response = await call('sync_batch', { device_id: state.device_id, operations: [operation], lang: root.dataset.lang || 'vi' }, true);
            result = (response.results || []).find(item => item.operation_id === operation.operation_id);
        } catch (error) {
            if (error.network) {
                queue(action, values, false);
                if (keepReportOpen) continueReport(values);
                else form.hidden = true;
            } else notice(errorMessage(error), 'danger');
            return;
        } finally { button.disabled = false; }
        if (!result?.success) return notice(result?.message || t('ui.sync_failed'), 'danger');
        state.failed = state.failed.filter(operation => operation.action !== action || operation.values.name !== values.name);
        persist(); updateStatus();
        if (keepReportOpen) continueReport(values, result.data?.name || values.name);
        else form.hidden = true;
        notice(t('ok.saved'), 'success');
        await refresh();
    }

    function beginPlan(row = null) {
        if (!state.device_id) return $('#device-dialog').showModal();
        const form = $('#plan-form'); form.reset(); editing.plan = row?.name || null;
        $('#plan-form-title').textContent = t(row ? 'ui.edit_plan' : 'ui.new_plan');
        form.elements.line.value = row?.line || state.bootstrap.device?.line || '';
        form.elements.product.value = row?.product || '';
        $('#plan-product-picker-button').removeAttribute('aria-invalid');
        updatePlanProductPicker();
        form.elements.line_start_date.value = row?.line_start_date || today();
        form.elements.shipment_date.value = row?.shipment_date || '';
        form.elements.planned_quantity.value = row?.planned_quantity ?? '';
        form.hidden = false; form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function renderPlanSummary() {
        const selected = availablePlans.find(plan => plan.name === $('#report-form').elements.production_plan.value);
        const summary = $('#report-plan-summary');
        if (!selected) {
            summary.textContent = t('ui.no_open_plan');
            summary.classList.add('text-muted');
            return;
        }
        summary.classList.remove('text-muted');
        const status = selected.closed_production_date ? 'ui.closed' : 'ui.open';
        const period = selected.line_start_date && (selected.closed_production_date || selected.shipment_date)
            ? `<small>${esc(t('ui.plan_period', { from: selected.line_start_date, to: selected.closed_production_date || selected.shipment_date }))}</small>`
            : '';
        summary.innerHTML = `<div class="productivity-plan-summary__top"><strong>${esc(productCode(selected.product))}</strong><span class="indicator-pill ${selected.closed_production_date ? 'gray' : 'green'}">${esc(t(status))}</span></div>${period}`;
    }

    function selectAvailablePlan(preferred) {
        const selected = availablePlans.find(plan => plan.name === preferred) || availablePlans[0];
        $('#report-form').elements.production_plan.value = selected?.name || '';
        renderPlanSummary();
    }

    async function loadAvailablePlans() {
        const request = ++planRequest;
        const form = $('#report-form');
        const line = form.elements.line.value, day = form.elements.production_date.value;
        const original = activeReportRow?.line === line && activeReportRow?.production_date === day ? activeReportRow : null;
        const preferred = original?.production_plan || form.elements.production_plan.value;
        const local = allPlans().filter(plan => !plan.is_deleted && !plan.closed_production_date && plan.line === line && plan.line_start_date <= day && plan.shipment_date >= day);
        if (original && !local.some(plan => plan.name === original.production_plan)) {
            local.push(allPlans().find(plan => plan.name === original.production_plan) || {
                name: original.production_plan, product: original.product, line: original.line,
            });
        }
        availablePlans = local;
        selectAvailablePlan(preferred);
        if (state.device_id && navigator.onLine && line && day) {
            try {
                const remote = await call('open_plans', { device_id: state.device_id, production_date: day, line });
                if (request !== planRequest) return;
                availablePlans = [...remote, ...local.filter(plan => !remote.some(item => item.name === plan.name))];
                selectAvailablePlan(preferred);
            } catch (error) { if (request === planRequest) notice(errorMessage(error), 'danger'); }
        }
    }

    function renderTimeSlots(savedSlots = []) {
        const configured = state.bootstrap.time_slots || [];
        const quantities = new Map(savedSlots.map(row => [row.time_slot, row.finished_quantity]));
        $('#slot-rows').innerHTML = configured.length
            ? configured.map(slot => `<div class="productivity-slot-row"><label for="slot-${esc(slot.name)}">${esc(slotName(slot.name))}</label><input id="slot-${esc(slot.name)}" class="form-control productivity-slot-quantity" data-time-slot="${esc(slot.name)}" aria-label="${esc(t('ui.finished_quantity'))} · ${esc(slotName(slot.name))}" type="number" min="0" step="1" value="${esc(quantities.get(slot.name) ?? 0)}" required></div>`).join('')
            : `<p class="productivity-empty">${esc(t('ui.no_time_slots'))}</p>`;
        updateFinishedTotal();
    }

    function updateFinishedTotal() { $('#finished-total').textContent = $$('.productivity-slot-quantity').reduce((n, el) => n + Math.max(0, Number(el.value || 0)), 0); }

    async function beginReport(row = null) {
        if (!state.device_id) return $('#device-dialog').showModal();
        const form = $('#report-form'); form.reset(); editing.report = row?.name || null; activeReportRow = row;
        $('#report-form-title').textContent = t(row ? 'ui.edit_report' : 'ui.new_report');
        form.elements.production_date.value = row?.production_date || today();
        form.elements.line.value = row?.line || state.bootstrap.device?.line || '';
        await loadAvailablePlans();
        for (const key of ['daily_target_quantity', 'working_hours', 'worker_count', 'ironing_delivery_quantity']) form.elements[key].value = row?.[key] ?? '';
        renderTimeSlots(row?.time_slots || []);
        form.hidden = false; form.scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (!availablePlans.length) notice(t('ui.no_open_plan'), 'info');
    }

    async function loadLineInfo() {
        if (!state.device_id) return;
        const form = $('#line-info-form'), line = form.elements.line.value || state.bootstrap.device?.line;
        const pending = [...state.operations].reverse().find(op => op.action === 'save_line_info' && op.values?.line === line);
        if (pending) {
            editing.line = pending.values.name;
            form.elements.line_leader_name.value = pending.values.line_leader_name || '';
            form.elements.technical_leader_name.value = pending.values.technical_leader_name || '';
            return;
        }
        if (!line || !navigator.onLine) return;
        try {
            const row = await call('current_line_info', { device_id: state.device_id, line });
            editing.line = row?.name || null;
            form.elements.line_leader_name.value = row?.line_leader_name || '';
            form.elements.technical_leader_name.value = row?.technical_leader_name || '';
        } catch (error) { notice(errorMessage(error), 'danger'); }
    }

    function findRow(kind, name) { return (rows[kind] || []).find(x => x.name === name) || state[kind].find(x => x.name === name); }
    function showDetail(row) {
        if (!row) return;
        const total = (row.time_slots || []).reduce((n, x) => n + Number(x.finished_quantity || 0), 0);
        $('#detail-content').innerHTML = `<dl>${field('ui.production_date', row.production_date)}${field('ui.line', lineName(row.line))}${field('ui.product', productCode(row.product))}${field('ui.daily_target', row.daily_target_quantity)}${field('ui.hours', row.working_hours)}${field('ui.worker_count', row.worker_count)}${field('ui.ironing_delivery', row.ironing_delivery_quantity)}${field('ui.finished_total', total)}</dl><h3>${esc(t('ui.time_slots'))}</h3><dl>${(row.time_slots || []).map(x => field('ui.time_slot', `${slotName(x.time_slot)} · ${x.finished_quantity ?? 0}`)).join('')}</dl>`;
        $('#detail-dialog').showModal();
    }

    async function changeState(action, kind, row) {
        if (!navigator.onLine) return notice(t('ui.online_required'), 'warning');
        const key = action === 'finish' ? 'ui.confirm_finish' : action === 'reopen' ? 'ui.confirm_reopen' : 'ui.confirm_delete';
        if (action === 'change-date') {
            const value = window.prompt(t('ui.closed_date_prompt'), row.closed_production_date || today());
            if (value === null) return;
            if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return notice(t('error.date'), 'warning');
            try { await call('change_plan_state', { device_id: state.device_id, name: row.name, action: 'finish', closed_date: value }, true); notice(t('ok.saved'), 'success'); await loadList(kind); }
            catch (error) { notice(errorMessage(error), 'danger'); }
            return;
        }
        if (!window.confirm(t(key))) return;
        try {
            if (kind === 'plans') await call('change_plan_state', { device_id: state.device_id, name: row.name, action }, true);
            else await call('delete_report', { device_id: state.device_id, name: row.name }, true);
            notice(t(action === 'delete' ? 'ok.deleted' : 'ok.saved'), 'success');
            await loadList(kind);
        } catch (error) { notice(errorMessage(error), 'danger'); }
    }

    $$('.productivity-nav-button').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
    $('#device-button').addEventListener('click', () => { renderDeviceIdentity(); $('#device-dialog').showModal(); });
    $$('[data-close-dialog]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
    $('#device-form').addEventListener('submit', async event => {
        event.preventDefault(); const newId = $('#device-id').value.trim();
        try {
            const device = await call('check_device', { device_id: newId }, true);
            state.device_id = device.id;
            state.bootstrap = { ...state.bootstrap, device };
            persist(); updateStatus(); $('#device-dialog').close(); await refresh(); await sync();
        } catch (error) { notice(errorMessage(error), 'danger'); }
    });
    $('#clear-device-cache').addEventListener('click', async () => {
        const unsaved = state.operations.length + state.failed.length;
        if (unsaved && !window.confirm(t('ui.confirm_clear_device_cache', { count: unsaved }))) return;
        localStorage.removeItem(storageKey);
        state = { ...blank, operations: [], failed: [], plans: [], reports: [], bootstrap: {} };
        for (const kind of ['plans', 'reports']) {
            pages[kind].page = 1;
            pages[kind].total = 0;
            rows[kind] = [];
        }
        $('#device-dialog').close();
        notice(t('ui.device_cache_cleared'), 'success');
        await refresh();
    });
    $('#sync-button').addEventListener('click', sync);
    $('#failed-button').addEventListener('click', () => { renderFailedDrafts(); $('#failed-dialog').showModal(); });
    $('#failed-drafts-list').addEventListener('click', async event => {
        const discard = event.target.closest('[data-discard-index]');
        if (discard) {
            state.failed.splice(Number(discard.dataset.discardIndex), 1);
            persist(); updateStatus(); renderFailedDrafts();
            if (!state.failed.length) $('#failed-dialog').close();
            return;
        }
        const button = event.target.closest('[data-failed-index]');
        if (!button) return;
        const operation = state.failed[Number(button.dataset.failedIndex)];
        if (!operation) return;
        $('#failed-dialog').close();
        if (operation.action === 'save_plan') { setView('plans'); beginPlan(operation.values); }
        else if (operation.action === 'save_report') { setView('reports'); await beginReport(operation.values); }
        else {
            await setView('line-info');
            const form = $('#line-info-form');
            editing.line = operation.values.name;
            form.elements.line.value = operation.values.line;
            form.elements.line_leader_name.value = operation.values.line_leader_name || '';
            form.elements.technical_leader_name.value = operation.values.technical_leader_name || '';
        }
    });
    $('#new-plan').addEventListener('click', () => beginPlan());
    $('#plan-product-picker-button').addEventListener('click', () => {
        $('#plan-product-search').value = '';
        renderPlanProductPicker();
        $('#plan-product-picker-button').setAttribute('aria-expanded', 'true');
        $('#plan-product-dialog').showModal();
        $('#plan-product-search').focus();
    });
    $('#plan-product-search').addEventListener('input', renderPlanProductPicker);
    $('#plan-product-grid').addEventListener('click', event => {
        const button = event.target.closest('[data-product-id]');
        if (!button) return;
        const product = (state.bootstrap.products || []).find(row => row.name === button.dataset.productId && row.product_code);
        if (!product) return;
        $('#plan-form').elements.product.value = product.name;
        updatePlanProductPicker();
        $('#plan-product-dialog').close();
    });
    $('#plan-product-dialog').addEventListener('close', () => {
        $('#plan-product-picker-button').setAttribute('aria-expanded', 'false');
        $('#plan-product-picker-button').focus();
    });
    $('#new-report').addEventListener('click', () => beginReport());
    $$('[data-cancel]').forEach(button => button.addEventListener('click', () => { $(`#${button.dataset.cancel}-form`).hidden = true; }));
    $('#plan-form').addEventListener('submit', async event => {
        event.preventDefault(); const form = event.currentTarget;
        if (!form.elements.product.value) {
            $('#plan-product-picker-button').setAttribute('aria-invalid', 'true');
            $('#plan-product-picker-button').focus();
            return notice(t('ui.choose_product'), 'warning');
        }
        if (form.elements.shipment_date.value < form.elements.line_start_date.value) {
            form.elements.shipment_date.focus();
            return notice(t('error.plan_date_order'), 'danger');
        }
        const values = { name: editing.plan || id(), line: form.elements.line.value, product: form.elements.product.value, line_start_date: form.elements.line_start_date.value, shipment_date: form.elements.shipment_date.value, planned_quantity: Number(form.elements.planned_quantity.value) };
        if (allPlans().some(plan => plan.name !== values.name && plan.line === values.line && !plan.is_deleted && !plan.closed_production_date)) {
            return notice(t('error.open_plan'), 'danger');
        }
        await saveWithConfirmation('save_plan', values, form);
    });
    $('#report-form').elements.line.addEventListener('change', loadAvailablePlans);
    $('#report-form').elements.production_date.addEventListener('change', loadAvailablePlans);
    $('#slot-rows').addEventListener('input', updateFinishedTotal);
    $('#report-form').addEventListener('submit', async event => {
        event.preventDefault(); const form = event.currentTarget;
        const plan = availablePlans.find(x => x.name === form.elements.production_plan.value);
        if (!plan) return notice(t('ui.no_open_plan'), 'warning');
        if (form.elements.production_date.value < plan.line_start_date || form.elements.production_date.value > (plan.closed_production_date || plan.shipment_date)) {
            form.elements.production_date.focus();
            return notice(t('error.report_date'), 'danger');
        }
        const slots = $$('.productivity-slot-quantity').map(input => ({ time_slot: input.dataset.timeSlot, finished_quantity: Number(input.value) }));
        if (!slots.length) return notice(t('ui.no_time_slots'), 'warning');
        const values = { name: editing.report || id(), line: form.elements.line.value, production_date: form.elements.production_date.value, production_plan: plan.name, product: plan.product, daily_target_quantity: Number(form.elements.daily_target_quantity.value), working_hours: Number(form.elements.working_hours.value), worker_count: Number(form.elements.worker_count.value), ironing_delivery_quantity: Number(form.elements.ironing_delivery_quantity.value), time_slots: slots };
        await saveWithConfirmation('save_report', values, form);
    });
    $('#line-info-form').elements.line.addEventListener('change', loadLineInfo);
    $('#line-info-form').addEventListener('submit', event => {
        event.preventDefault(); const form = event.currentTarget;
        const values = { name: editing.line || id(), line: form.elements.line.value, line_leader_name: form.elements.line_leader_name.value.trim(), technical_leader_name: form.elements.technical_leader_name.value.trim() };
        editing.line = values.name;
        queue('save_line_info', values);
    });
    for (const kind of ['plans', 'reports']) {
        $(`#${kind}-filter`).addEventListener('submit', event => { event.preventDefault(); pages[kind].page = 1; loadList(kind); });
        $(`#${kind}-list`).addEventListener('click', event => {
            const button = event.target.closest('[data-action]'); if (!button) return;
            const row = findRow(kind, button.dataset.name); if (!row) return;
            const action = button.dataset.action;
            if (action === 'edit-plan') beginPlan(row);
            else if (action === 'edit-report') beginReport(row);
            else if (action === 'detail-report') showDetail(row);
            else changeState(action.replace('-plan', '').replace('-report', ''), kind, row);
        });
        $(`#${kind}-pagination`).addEventListener('click', event => { const button = event.target.closest('[data-page]'); if (!button) return; pages[kind].page += button.dataset.page === 'next' ? 1 : -1; loadList(kind); });
    }
    window.addEventListener('online', async () => { updateStatus(); await sync(); await refresh(); });
    window.addEventListener('offline', () => { updateStatus(); loadList('plans'); loadList('reports'); });
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/productivity-sw.js', { scope: '/productivity' }).catch(() => {});
    updateStatus(); refresh().then(sync);
})();
