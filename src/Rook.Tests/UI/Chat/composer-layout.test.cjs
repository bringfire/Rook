const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { test, before, after } = require('node:test');
const { chromium } = require('playwright');

const resources = path.resolve(__dirname, '../../../Rook/UI/Chat/Resources');
const origin = 'https://app.rook.invalid';
const files = new Set(['chat.html', 'chat.css', 'composer-images.js', 'vendor/marked.min.js',
    'vendor/highlight.min.js', 'vendor/github-dark.min.css', 'vendor/github.min.css']);
let browser;
before(async () => { browser = await chromium.launch({ channel: 'msedge', headless: true }); });
after(async () => { await browser?.close(); });

async function withComposer(check) {
    const context = await browser.newContext({ serviceWorkers: 'block' });
    const errors = [];
    try {
        await context.route('**/*', async route => {
            const url = new URL(route.request().url());
            const relative = url.pathname.slice(1);
            if (url.origin !== origin || !files.has(relative)) {
                errors.push(`Unexpected request: ${url.origin}${url.pathname}`);
                return route.abort();
            }
            return route.fulfill({ body: await fs.readFile(path.join(resources, relative)),
                contentType: relative.endsWith('.css') ? 'text/css' : relative.endsWith('.js') ? 'application/javascript' : 'text/html' });
        });
        const page = await context.newPage();
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(origin + '/chat.html');
        await page.evaluate(async () => {
            window.calls = [];
            window.rookBridge = { invoke: (name, value) => {
                window.calls.push({ name, value });
                return new Promise((resolve, reject) => { window.ack = resolve; window.failAck = reject; });
            } };
            window.chatAPI.setComposerEnabled(true, true);
            document.getElementById('composer-text').value = 'submitted text';
            await readComposerFiles([new File(['synthetic old'], 'old.png', { type: 'image/png' })]);
        });
        await check(page);
        assert.deepEqual(errors, []);
    } finally { await context.close(); }
}

async function draft(page) {
    return page.evaluate(() => ({
        text: document.getElementById('composer-text').value,
        attachments: [...document.querySelectorAll('.attachment-chip')].map(e => e.textContent),
        disabled: document.getElementById('composer-send').disabled,
        calls: window.calls.length
    }));
}

for (const accepted of [false, true]) {
    test(`composer clears a submitted draft only on accepted=${accepted}`, { timeout: 30000 }, async () => {
        await withComposer(async page => {
            await page.evaluate(accepted => {
                submitComposer();
                window.chatAPI.setComposerEnabled(true, false);
                window.ack({ accepted });
            }, accepted);
            assert.deepEqual(await draft(page), {
                text: accepted ? '' : 'submitted text', attachments: accepted ? [] : ['old.png'], disabled: true, calls: 1
            });
            await page.evaluate(() => { submitComposer(); submitComposer(); });
            assert.equal((await draft(page)).calls, 1);
        });
    });
}

for (const edit of ['text', 'text-reverted', 'attachments', 'same-attachments', 'pending-attachments']) {
    test(`accepted acknowledgement preserves newer ${edit}`, { timeout: 30000 }, async () => {
        await withComposer(async page => {
            await page.evaluate(async edit => {
                submitComposer();
                const input = document.getElementById('composer-text');
                if (edit.startsWith('text')) {
                    input.value = 'new draft';
                    input.dispatchEvent(new Event('input'));
                    if (edit === 'text-reverted') {
                        input.value = 'submitted text';
                        input.dispatchEvent(new Event('input'));
                    }
                } else if (edit === 'pending-attachments') {
                    window.RealFileReader = window.FileReader;
                    window.FileReader = class {
                        readAsDataURL() { window.finishImage = () => { this.result = 'data:image/png;base64,bmV3'; this.onload(); }; }
                    };
                    window.pendingImage = readComposerFiles([new File(['new'], 'new.png', { type: 'image/png' })]);
                } else {
                    await readComposerFiles([new File(['new'], edit === 'same-attachments' ? 'old.png' : 'new.png', { type: 'image/png' })]);
                }
                window.chatAPI.setComposerEnabled(true, true);
                window.ack({ accepted: true });
            }, edit);
            if (edit === 'pending-attachments') await page.evaluate(async () => {
                window.finishImage();
                await window.pendingImage;
                window.FileReader = window.RealFileReader;
            });
            const state = await draft(page);
            assert.equal(state.text, edit === 'text' ? 'new draft' : edit === 'text-reverted' ? 'submitted text' : '');
            assert.deepEqual(state.attachments, edit.startsWith('text') ? [] : [edit === 'same-attachments' ? 'old.png' : 'new.png']);
            assert.equal(state.calls, 1);
        });
    });
}

test('pending acknowledgement blocks repeated submission even after a host enable', { timeout: 30000 }, async () => {
    await withComposer(async page => {
        await page.evaluate(() => {
            submitComposer();
            window.chatAPI.setComposerEnabled(true, true);
            submitComposer();
            submitComposer();
        });
        assert.deepEqual(await draft(page), { text: 'submitted text', attachments: ['old.png'], disabled: true, calls: 1 });
        await page.evaluate(() => window.ack({ accepted: false }));
        assert.equal((await draft(page)).calls, 1);
        assert.equal((await draft(page)).disabled, false);
        await page.evaluate(() => submitComposer());
        assert.equal((await draft(page)).calls, 2);
        await page.evaluate(() => window.ack({ accepted: true }));
    });
});

for (const kind of ['missing', 'malformed', 'rejected', 'thrown', 'nonpromise']) {
    test(`${kind} acknowledgement retains the draft and never enables replay`, { timeout: 30000 }, async () => {
        await withComposer(async page => {
            await page.evaluate(kind => {
                if (kind === 'thrown' || kind === 'nonpromise') window.rookBridge.invoke = () => {
                    window.calls.push({});
                    if (kind === 'thrown') throw new Error('synthetic acknowledgement failure');
                };
                submitComposer();
                if (kind === 'missing') window.ack(null);
                if (kind === 'malformed') window.ack({ accepted: 'false' });
                if (kind === 'rejected') window.failAck(new Error('synthetic acknowledgement failure'));
            }, kind);
            await page.evaluate(() => {
                window.chatAPI.setComposerEnabled(true, true);
                submitComposer();
                submitComposer();
            });
            assert.deepEqual(await draft(page), { text: 'submitted text', attachments: ['old.png'], disabled: true, calls: 1 });
            assert.match(await page.locator('#messages').textContent(), /acknowledgement is unconfirmed/i);
        });
    });
}

for (const [width, height] of [[697, 502], [320, 240], [360, 480], [480, 320], [1000, 800]]) {
    test(`visible composer and independently scrolling transcript at ${width}x${height}`, { timeout: 30000 }, async t => {
        const context = await browser.newContext({ viewport: { width, height }, serviceWorkers: 'block' });
        const errors = [];
        try {
            await context.route('**/*', async route => {
                const url = new URL(route.request().url());
                const relative = url.pathname.slice(1);
                if (url.origin !== origin || !files.has(relative)) {
                    errors.push(`Unexpected request: ${url.origin}${url.pathname}`);
                    await route.abort();
                    return;
                }
                await route.fulfill({ body: await fs.readFile(path.join(resources, relative)),
                    contentType: relative.endsWith('.css') ? 'text/css' :
                        relative.endsWith('.js') ? 'application/javascript' : 'text/html' });
            });
            const page = await context.newPage();
            page.on('pageerror', error => errors.push(error.message));
            await page.goto(`${origin}/chat.html`);
            await page.evaluate(() => window.chatAPI.setComposerEnabled(true, true));

            async function bounds() {
                return page.evaluate(() => Object.fromEntries(
                    ['chat-container', 'messages', 'composer', 'composer-text', 'composer-send'].map(id => {
                        const e = document.getElementById(id), r = e.getBoundingClientRect();
                        return [id, { top: r.top, bottom: r.bottom, left: r.left, right: r.right,
                            width: r.width, height: r.height, display: getComputedStyle(e).display }];
                    })));
            }
            function assertVisible(rows) {
                for (const id of ['composer', 'composer-text', 'composer-send']) {
                    const r = rows[id];
                    assert.ok(r.width > 0 && r.height > 0 && r.display !== 'none', `${id} has no visible box`);
                    assert.ok(r.top >= 0 && r.bottom <= height && r.left >= 0 && r.right <= width,
                        `${id} outside ${width}x${height}: ${JSON.stringify(r)}`);
                }
                assert.ok(rows.messages.height > 0, 'transcript has no remaining space');
                assert.ok(rows['chat-container'].bottom <= rows.composer.top, 'transcript overlaps composer');
            }

            const empty = await bounds();
            t.diagnostic(JSON.stringify({ viewport: [width, height], bounds: empty }));
            if (process.env.ROOK_LAYOUT_EVIDENCE) {
                await fs.mkdir(process.env.ROOK_LAYOUT_EVIDENCE, { recursive: true });
                await page.screenshot({ path: path.join(process.env.ROOK_LAYOUT_EVIDENCE, `${width}x${height}.png`) });
            }
            assertVisible(empty);
            await page.evaluate(() => {
                for (let i = 0; i < 60; i++) window.chatAPI.addMessage('user', `Local layout fixture ${i}\nSecond line.`);
                window.chatAPI.showTypingIndicator(true);
            });
            assertVisible(await bounds());
            const scrolled = await page.evaluate(() => {
                const e = document.getElementById('messages');
                e.scrollTop = 0;
                e.scrollTop = e.scrollHeight;
                return { scrollHeight: e.scrollHeight, clientHeight: e.clientHeight, scrollTop: e.scrollTop };
            });
            assert.ok(scrolled.scrollHeight > scrolled.clientHeight && scrolled.scrollTop > 0, 'transcript cannot scroll');
            assert.deepEqual((await bounds()).composer, empty.composer, 'transcript scrolling moved composer');
            await page.evaluate(() => window.chatAPI.setComposerEnabled(false, false));
            assert.equal((await bounds()).composer.display, 'none');
            await page.evaluate(() => window.chatAPI.setComposerEnabled(true, true));
            assertVisible(await bounds());
            assert.deepEqual(errors, []);
        } finally {
            await context.close();
        }
    });
}
