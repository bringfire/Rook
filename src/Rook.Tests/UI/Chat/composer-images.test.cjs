const assert = require('node:assert/strict');
const path = require('node:path');

const { clipboardImageFiles, createSelectionController } = require(path.resolve(
    __dirname,
    '../../../Rook/UI/Chat/Resources/composer-images.js'));

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}

async function run() {
    const clipboard = clipboardImageFiles([
        { kind: 'string', type: 'text/plain', getAsFile: () => null },
        { kind: 'file', type: 'image/gif', getAsFile: () => ({ name: 'ignored.gif' }) },
        { kind: 'file', type: 'image/png', getAsFile: () => ({ name: 'pasted.png', type: 'image/png' }) },
    ]);
    assert.deepEqual(clipboard.map(file => file.name), ['pasted.png']);

    const reads = new Map();
    const publications = [];
    const controller = createSelectionController({
        readImage(file) {
            const pending = deferred();
            reads.set(file.name, pending);
            return pending.promise;
        },
        publish(images) {
            publications.push(images.map(image => image.fileName));
        },
    });

    const ordered = controller.replace([
        { name: 'first.png', type: 'image/png' },
        { name: 'second.png', type: 'image/png' },
    ]);
    reads.get('second.png').resolve({ fileName: 'second.png', mimeType: 'image/png', base64Data: 'Mg==' });
    reads.get('first.png').resolve({ fileName: 'first.png', mimeType: 'image/png', base64Data: 'MQ==' });
    assert.equal(await ordered, true);
    assert.deepEqual(controller.snapshot().map(image => image.fileName), ['first.png', 'second.png']);

    const stale = controller.replace([{ name: 'stale.png', type: 'image/png' }]);
    const current = controller.replace([{ name: 'current.png', type: 'image/png' }]);
    reads.get('current.png').resolve({ fileName: 'current.png', mimeType: 'image/png', base64Data: 'Yw==' });
    assert.equal(await current, true);
    reads.get('stale.png').resolve({ fileName: 'stale.png', mimeType: 'image/png', base64Data: 'cw==' });
    assert.equal(await stale, false);
    assert.deepEqual(controller.snapshot().map(image => image.fileName), ['current.png']);

    const cleared = controller.replace([{ name: 'late.png', type: 'image/png' }]);
    controller.clear();
    reads.get('late.png').resolve({ fileName: 'late.png', mimeType: 'image/png', base64Data: 'bA==' });
    assert.equal(await cleared, false);
    assert.deepEqual(controller.snapshot(), []);
    assert.deepEqual(publications.at(-1), []);
}

run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
