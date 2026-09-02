const assert = require('node:assert/strict');
const path = require('node:path');

const { canSubmit, clipboardImageFiles, createSelectionController } = require(path.resolve(
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
    const loadingStates = [];
    const controller = createSelectionController({
        readImage(file) {
            const pending = deferred();
            reads.set(file.name, pending);
            return pending.promise;
        },
        publish(images) {
            publications.push(images.map(image => image.fileName));
        },
        onLoadingChanged(loading) {
            loadingStates.push(loading);
        },
    });

    const ordered = controller.replace([
        { name: 'first.png', type: 'image/png' },
        { name: 'second.png', type: 'image/png' },
    ]);
    assert.equal(controller.isLoading(), true);
    assert.equal(canSubmit('inspect', controller.snapshot(), controller.isLoading()), false);
    assert.equal(canSubmit('', controller.snapshot(), controller.isLoading()), false);
    reads.get('second.png').resolve({ fileName: 'second.png', mimeType: 'image/png', base64Data: 'Mg==' });
    assert.equal(controller.isLoading(), true);
    reads.get('first.png').resolve({ fileName: 'first.png', mimeType: 'image/png', base64Data: 'MQ==' });
    assert.equal(await ordered, true);
    assert.equal(controller.isLoading(), false);
    assert.deepEqual(controller.snapshot().map(image => image.fileName), ['first.png', 'second.png']);
    assert.equal(canSubmit('', controller.snapshot(), controller.isLoading()), true);

    const stale = controller.replace([{ name: 'stale.png', type: 'image/png' }]);
    const current = controller.replace([{ name: 'current.png', type: 'image/png' }]);
    reads.get('current.png').resolve({ fileName: 'current.png', mimeType: 'image/png', base64Data: 'Yw==' });
    assert.equal(await current, true);
    assert.equal(controller.isLoading(), false);
    reads.get('stale.png').resolve({ fileName: 'stale.png', mimeType: 'image/png', base64Data: 'cw==' });
    assert.equal(await stale, false);
    assert.equal(controller.isLoading(), false);
    assert.deepEqual(controller.snapshot().map(image => image.fileName), ['current.png']);

    const cleared = controller.replace([{ name: 'late.png', type: 'image/png' }]);
    assert.equal(controller.isLoading(), true);
    controller.clear();
    assert.equal(controller.isLoading(), false);
    reads.get('late.png').resolve({ fileName: 'late.png', mimeType: 'image/png', base64Data: 'bA==' });
    assert.equal(await cleared, false);
    assert.deepEqual(controller.snapshot(), []);
    assert.deepEqual(publications.at(-1), []);
    assert.deepEqual(loadingStates.slice(0, 2), [true, false]);
}

run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
