(function(root, factory) {
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    root.RookComposerImages = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
    function defaultReadImage(file, index) {
        return new Promise(function(resolve, reject) {
            var reader = new FileReader();
            reader.onload = function() {
                var value = String(reader.result || '');
                var comma = value.indexOf(',');
                if (comma < 0) { reject(new Error('Image could not be read.')); return; }
                resolve({
                    fileName: file.name || ('pasted-image-' + (index + 1)),
                    mimeType: file.type,
                    base64Data: value.substring(comma + 1)
                });
            };
            reader.onerror = function() { reject(new Error('Image could not be read.')); };
            reader.readAsDataURL(file);
        });
    }

    function createSelectionController(options) {
        options = options || {};
        var readImage = options.readImage || defaultReadImage;
        var publish = options.publish || function() {};
        var reportError = options.reportError || function() {};
        var maxImages = options.maxImages || 8;
        var generation = 0;
        var images = [];

        function snapshot() {
            return images.map(function(image) {
                return {
                    fileName: image.fileName,
                    mimeType: image.mimeType,
                    base64Data: image.base64Data
                };
            });
        }

        function clear() {
            generation += 1;
            images = [];
            publish(snapshot());
        }

        function replace(files) {
            var currentGeneration = ++generation;
            var selected = Array.prototype.slice.call(files || []);
            images = [];
            publish(snapshot());
            if (selected.length > maxImages) {
                reportError('At most ' + maxImages + ' images may be attached.');
                return Promise.resolve(false);
            }
            return Promise.all(selected.map(function(file, index) {
                return readImage(file, index);
            })).then(function(nextImages) {
                if (currentGeneration !== generation) return false;
                images = nextImages;
                publish(snapshot());
                return true;
            }).catch(function() {
                if (currentGeneration !== generation) return false;
                images = [];
                publish(snapshot());
                reportError('Image could not be read.');
                return false;
            });
        }

        return { replace: replace, clear: clear, snapshot: snapshot };
    }

    function clipboardImageFiles(items) {
        return Array.prototype.slice.call(items || []).filter(function(item) {
            return item.kind === 'file' && /^(image\/png|image\/jpeg|image\/webp)$/.test(item.type || '');
        }).map(function(item) { return item.getAsFile(); }).filter(Boolean);
    }

    return {
        clipboardImageFiles: clipboardImageFiles,
        createSelectionController: createSelectionController
    };
});
