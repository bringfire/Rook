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
