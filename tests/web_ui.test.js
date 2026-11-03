// Runs the page's script against a small stand-in for the browser.
// Run with: node --test tests/web_ui.test.js
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'scheduler_ui.html'), 'utf8');
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];

function jsonResponse(status, body) {
    return {
        ok: status >= 200 && status < 300,
        status,
        headers: { get: () => 'application/json' },
        json: async () => body,
    };
}

function loadPage({ search = '', hostname = 'printer', protocol = 'http:', port = '', fetchImpl } = {}) {
    const elements = {};
    const element = (id) => {
        elements[id] = elements[id] || {
            id, value: '', innerHTML: '', checked: false, style: {},
            classList: { add() {}, remove() {} },
            appendChild() {},
        };
        return elements[id];
    };
    const alerts = [];
    const context = {
        URL, URLSearchParams, console: { log() {}, warn() {}, error() {} },
        JSON, Object, Array, parseInt, Date, encodeURIComponent,
        window: {
            location: {
                search, hostname, protocol,
                origin: protocol === 'file:' ? 'null' : `${protocol}//${hostname}${port ? ':' + port : ''}`,
            },
        },
        document: {
            addEventListener() {},
            getElementById: element,
            querySelectorAll: () => [],
            createElement: () => ({}),
        },
        fetch: fetchImpl || (async () => jsonResponse(200, { result: { schedules: [] } })),
        alert: (message) => alerts.push(message),
        confirm: () => true,
    };
    vm.createContext(context);
    vm.runInContext(script, context);
    return {
        context, alerts, element,
        run: (code) => vm.runInContext(code, context),
    };
}

const MALICIOUS = '<img src=x onerror=alert(1)>';

function schedule(overrides = {}) {
    return {
        id: 1, name: 'n', macro: 'M', schedule_type: 'daily', time: '06:00',
        params: {}, enabled: true, next_run: '2026-11-03T06:00:00', ...overrides,
    };
}

function renderWith(page, schedules) {
    page.context.__schedules = schedules;
    page.run('schedules = __schedules; renderSchedules();');
    return page.element('schedules-container').innerHTML;
}

test('schedule fields are escaped when rendered', () => {
    for (const overrides of [
        { name: MALICIOUS },
        { macro: MALICIOUS },
        { params: { A: MALICIOUS } },
        { last_status: 'failed', last_error: MALICIOUS },
        { schedule_type: 'cron', cron_expression: MALICIOUS },
        { time: MALICIOUS },
    ]) {
        const out = renderWith(loadPage(), [schedule(overrides)]);
        assert.ok(!out.includes('<img'), JSON.stringify(overrides));
        assert.ok(out.includes('&lt;img'), JSON.stringify(overrides));
    }
});

test('a non-numeric id cannot break out of the button handler', () => {
    const out = renderWith(loadPage(), [schedule({ id: '1);alert(1' })]);
    assert.ok(!out.includes('alert(1'));
});

test('load error text is escaped', async () => {
    const page = loadPage({ fetchImpl: async () => { throw new Error(MALICIOUS); } });
    await page.run('loadSchedules()');
    const out = page.element('schedules-container').innerHTML;
    assert.ok(!out.includes('<img'));
});

test('every schedule type has a readable description', () => {
    const page = loadPage();
    page.context.__s = schedule({ schedule_type: 'interval', interval_minutes: 15 });
    assert.match(page.run('formatScheduleTime(__s)'), /15 min/);
    page.context.__s = schedule({ schedule_type: 'cron', cron_expression: '0 9 * * 1' });
    assert.match(page.run('formatScheduleTime(__s)'), /0 9 \* \* 1/);
    page.context.__s = schedule({ schedule_type: 'weekly', days: [0, 6] });
    assert.match(page.run('formatScheduleTime(__s)'), /Mon.*Sun/);
    page.context.__s = schedule({ schedule_type: 'daily' });
    assert.match(page.run('formatScheduleTime(__s)'), /Daily at 06:00/);
});

test('last result is shown', () => {
    const out = renderWith(loadPage(), [schedule({ last_status: 'skipped', last_error: 'Printer was printing' })]);
    assert.ok(out.includes('skipped'));
    assert.ok(out.includes('Printer was printing'));
});

test('an auth failure is reported instead of an empty list', async () => {
    const page = loadPage({
        fetchImpl: async () => jsonResponse(401, { error: { code: 401, message: 'Unauthorized' } }),
    });
    await page.run('loadSchedules()');
    const out = page.element('schedules-container').innerHTML;
    assert.ok(!out.includes('No schedules yet'));
    assert.match(out, /trusted_clients|log in|authoriz/i);
});

test('a reachable Moonraker that requires auth is not reported as unreachable', async () => {
    const page = loadPage({
        fetchImpl: async () => jsonResponse(401, { error: { code: 401, message: 'Unauthorized' } }),
    });
    await page.run('checkStatus()');
    const out = page.element('schedules-container').innerHTML;
    assert.ok(!out.includes('Cannot connect'));
});

test('a missing component shows the setup steps', async () => {
    const page = loadPage({ fetchImpl: async () => jsonResponse(404, { error: { code: 404, message: 'Not Found' } }) });
    await page.run('loadSchedules()');
    assert.match(page.element('schedules-container').innerHTML, /moonraker\.conf/);
});

test('api_base is limited to the page host', () => {
    assert.strictEqual(
        loadPage({ search: '?api_base=http://evil.example:7125' }).run('apiCandidates.join()').includes('evil'),
        false,
    );
    assert.strictEqual(
        loadPage({ search: '?api_base=javascript:alert(1)' }).run('apiCandidates.join()').includes('javascript'),
        false,
    );
    assert.strictEqual(
        loadPage({ search: '?api_base=http://printer:7125', port: '81' }).run('apiCandidates[0]'),
        'http://printer:7125',
    );
});

test('api_base can name any host when the page is opened from a local file', () => {
    assert.strictEqual(
        loadPage({ search: '?api_base=http://voron:7125', protocol: 'file:', hostname: '' }).run('apiCandidates[0]'),
        'http://voron:7125',
    );
});

for (const action of ['toggleSchedule', 'deleteSchedule']) {
    test(`${action} reports a failed response`, async () => {
        const page = loadPage({
            fetchImpl: async () => jsonResponse(400, { error: { code: 400, message: 'Nope' } }),
        });
        await page.run(`${action}(1)`);
        assert.strictEqual(page.alerts.length, 1);
        assert.match(page.alerts[0], /Nope/);
    });
}

test('new schedules send the per-schedule settings', async () => {
    const sent = [];
    const page = loadPage({
        fetchImpl: async (url, options) => {
            if (options) sent.push(JSON.parse(options.body));
            return jsonResponse(200, { result: { schedules: [] } });
        },
    });
    page.element('scheduleName').value = 'n';
    page.element('scheduleMacro').value = 'M';
    page.element('scheduleType').value = 'daily';
    page.element('scheduleParams').value = '{}';
    page.element('scheduleTime').value = '06:00';
    page.element('scheduleMissed').value = 'run';
    page.element('scheduleSkipPrinting').checked = false;
    await page.run('addSchedule()');
    assert.strictEqual(sent[0].missed_run_policy, 'run');
    assert.strictEqual(sent[0].skip_if_printing, false);
});

test('the form has the per-schedule settings', () => {
    assert.ok(html.includes('id="scheduleMissed"'));
    assert.ok(html.includes('id="scheduleSkipPrinting"'));
});
