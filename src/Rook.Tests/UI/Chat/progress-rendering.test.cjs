const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { test } = require('node:test');
const { chromium } = require('playwright');

const resources = path.resolve(__dirname, '../../../Rook/UI/Chat/Resources');
const origin = 'https://app.rook.invalid';
const files = new Set(['chat.html', 'chat.css', 'composer-images.js', 'vendor/marked.min.js',
    'vendor/highlight.min.js', 'vendor/github-dark.min.css', 'vendor/github.min.css']);

for (const outcome of ['settled', 'cancelled', 'incomplete']) {
    test(`real panel commands render distinct progress segments after ${outcome}`, { timeout: 30000 }, async () => {
        assert.ok(process.env.ROOK_PROGRESS_TEST_OUTPUT, 'Run AgentChatProgressTests with a fresh trace directory first.');
        const scripts = JSON.parse(await fs.readFile(path.join(process.env.ROOK_PROGRESS_TEST_OUTPUT, outcome + '.json'), 'utf8'));
        assert.ok(scripts.length > 0 && scripts.length < 100);
        const browser = await chromium.launch({ channel: 'msedge', headless: true });
        try {
            const context = await browser.newContext({ serviceWorkers: 'block' });
            const errors = [];
            await context.route('**/*', async route => {
                const url = new URL(route.request().url());
                const relative = url.pathname.slice(1);
                if (url.origin !== origin || !files.has(relative)) {
                    errors.push(`Unexpected request: ${url.origin}${url.pathname}`);
                    return route.abort();
                }
                await route.fulfill({ body: await fs.readFile(path.join(resources, relative)),
                    contentType: relative.endsWith('.css') ? 'text/css' : relative.endsWith('.js') ? 'application/javascript' : 'text/html' });
            });
            const page = await context.newPage();
            page.on('pageerror', error => errors.push(error.message));
            await page.goto(origin + '/chat.html');
            await page.evaluate(() => { window.finalizedForTest = []; });
            for (const script of scripts) {
                await page.evaluate(script);
                // Previous finalized DOM nodes must survive every subsequent update.
                assert.equal(await page.evaluate(() => {
                    const unchanged = window.finalizedForTest.every(row => row.node.isConnected && row.node.innerHTML === row.html);
                    window.finalizedForTest = [...document.querySelectorAll('.assistant-message:not(#streaming-message)')]
                        .map(node => ({ node, html: node.innerHTML }));
                    return unchanged;
                }), true, `Finalized bubble changed after ${script}`);
            }
            assert.deepEqual(await page.locator('.assistant-message').allTextContents(),
                ['alpha repeat.\n', 'beta repeat.\n', 'repeat.\n', 'next\n']);
            assert.deepEqual(await page.locator('#messages > *').evaluateAll(nodes => nodes.map(node =>
                node.classList.contains('tool-card') ? node.getAttribute('data-tool-call-id') : node.textContent.trim())),
                ['alpha repeat.', 't1', 't2', 'beta repeat.', 't3', 'repeat.', 'next']);
            assert.equal(await page.locator('#streaming-message').count(), 0);
            assert.equal(await page.locator('[data-tool-call-id="t1"]').getAttribute('data-state'), 'done-success');
            assert.equal(await page.locator('[data-tool-call-id="t2"]').getAttribute('data-state'), 'failed');
            assert.deepEqual(errors, []);
        } finally {
            await browser.close();
        }
    });
}
