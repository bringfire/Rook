// Descriptor scalar controls. Managed normalization remains authoritative.
// Inputs retain suppliedness independently of the displayed default.
window.RookModelControls = (() => {
    const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
    const scale = 1000000n;
    function exactNumeric(raw, field) {
        const text = String(raw).trim();
        const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(text);
        if (!match) throw new Error('Enter an ordinary decimal number (up to six fractional places).');
        const fraction = (match[3] || '').replace(/0+$/, '');
        const sign = match[1] === '-' ? -1n : 1n;
        const digits = match[2].replace(/^0+/, '') || '0';
        if (digits.length > (field.type === 'integer' ? 16 : 10)) throw new Error(field.type === 'integer' ? 'Enter a safe integer.' : 'Number is outside the supported bounds.');
        const whole = BigInt(digits);
        if (field.type === 'integer') {
            if (fraction || whole > 9007199254740991n) throw new Error('Enter a safe integer between -9007199254740991 and 9007199254740991.');
        } else if (fraction.length > 6 || whole > 1000000000n || (whole === 1000000000n && fraction)) {
            throw new Error('Number must have at most six fractional places and absolute value at most 1000000000.');
        }
        return sign * (whole * scale + BigInt(fraction.padEnd(6, '0') || '0'));
    }
    function parseValue(raw, f) {
        if (f.type === 'integer' || f.type === 'number') {
            const value = exactNumeric(raw, f);
            if (own(f, 'min') && value < exactNumeric(String(f.min), f)) throw new Error(`Minimum is ${f.min}.`);
            if (own(f, 'max') && value > exactNumeric(String(f.max), f)) throw new Error(`Maximum is ${f.max}.`);
            if (own(f, 'step')) {
                const origin = own(f, 'min') ? exactNumeric(String(f.min), f) : 0n;
                const step = exactNumeric(String(f.step), f);
                if (step <= 0n || (value - origin) % step !== 0n) throw new Error(`Use step ${f.step} from ${own(f, 'min') ? f.min : 0}.`);
            }
            // Only convert after the original lexeme and exact bounds/step pass.
            return Number(String(raw).trim());
        }
        if (f.type === 'boolean') {
            if (raw !== 'true' && raw !== 'false') throw new Error('Choose true or false.');
            return raw === 'true';
        }
        if (f.type === 'enum' && !(f.values || []).includes(raw)) throw new Error('Choose a declared value.');
        if (own(f, 'max_length') && raw.length > f.max_length) throw new Error(`Maximum length is ${f.max_length}.`);
        if (own(f, 'min_length') && raw.length < f.min_length) throw new Error(`Minimum length is ${f.min_length}.`);
        return raw;
    }
    function matches(conditions, context) {
        return (conditions || []).every(c => {
            if (c.role) return (context.media || []).some(m => m.semantic_role === c.role) === c.present;
            const value = context.values[c.field];
            return c.operator === 'eq' ? value === c.value : c.operator === 'in' && (c.values || []).includes(value);
        });
    }
    function create(container, descriptor, onChange) {
        const rows = [], listeners = []; let disposed = false;
        container.replaceChildren();
        const basic = document.createElement('div'); basic.className = 'model-controls-basic';
        const advanced = document.createElement('details'); advanced.className = 'model-controls-advanced';
        const summary = document.createElement('summary'); summary.textContent = 'Advanced'; advanced.appendChild(summary);
        container.appendChild(basic);
        function listen(node, name, fn) { node.addEventListener(name, fn); listeners.push(() => node.removeEventListener(name, fn)); }
        const fields = [...(descriptor.options || [])].sort((a,b) =>
            (a.ui?.group === 'advanced') - (b.ui?.group === 'advanced') || (a.ui?.order || 0) - (b.ui?.order || 0));
        for (const f of fields) {
            const key = `${f.scope || 'options'}.${f.key}`;
            const row = document.createElement('div'); row.className = 'model-control'; row.dataset.fieldRow = key;
            const label = document.createElement('label'); label.textContent = f.label || f.key;
            const input = document.createElement(f.type === 'boolean' || f.type === 'enum' ? 'select' : f.type === 'string' ? 'textarea' : 'input');
            input.dataset.field = key; input.dataset.control = 'value'; input.dataset.type = f.type;
            if (input.tagName === 'INPUT') { input.type = 'text'; input.inputMode = f.type === 'integer' ? 'numeric' : 'decimal'; }
            if (input.tagName === 'SELECT') {
                const absent = document.createElement('option'); absent.value = ''; absent.textContent = own(f, 'default') ? `Default: ${f.default}` : 'Unset'; input.appendChild(absent);
                for (const value of f.type === 'boolean' ? ['true', 'false'] : f.values || []) {
                    const option = document.createElement('option'); option.value = value; option.textContent = value; input.appendChild(option);
                }
            }
            const reset = document.createElement('button'); reset.type = 'button'; reset.className = 'btn-text'; reset.dataset.clear = key;
            reset.textContent = own(f, 'default') ? 'Use default' : 'Unset';
            const hint = document.createElement('span'); hint.className = 'field-hint';
            const error = document.createElement('span'); error.className = 'model-field-error'; error.setAttribute('aria-live', 'polite');
            const record = { f, key, row, label, input, reset, hint, error, supplied: false };
            function resetValue() { record.supplied = false; input.value = input.tagName === 'SELECT' ? '' : own(f, 'default') ? String(f.default) : ''; }
            function changed() { if (disposed) return; error.textContent = ''; input.removeAttribute('aria-invalid'); onChange(); }
            resetValue();
            listen(input, input.tagName === 'SELECT' ? 'change' : 'input', () => {
                record.supplied = input.tagName === 'SELECT' || f.type === 'integer' || f.type === 'number' ? input.value !== '' : true;
                changed();
            });
            listen(reset, 'click', () => { resetValue(); changed(); });
            label.appendChild(input); row.appendChild(label); row.appendChild(reset); row.appendChild(hint); row.appendChild(error);
            (f.ui?.group === 'advanced' ? advanced : basic).appendChild(row); rows.push(record);
        }
        if (fields.some(f => f.ui?.group === 'advanced')) container.appendChild(advanced);
        function setValidation(errors) {
            for (const r of rows) {
                const messages = (errors || []).filter(e => e.field === r.key || e.field === r.f.key).map(e => e.message);
                r.error.textContent = messages.join(' ');
                if (messages.length) { r.input.setAttribute('aria-invalid', 'true'); r.row.hidden = false; if(r.f.ui?.group === 'advanced') advanced.open = true; }
                else r.input.removeAttribute('aria-invalid');
            }
        }
        function readOptions() {
            const values = {}, errors = [];
            for (const r of rows) if (r.supplied) {
                try { values[r.f.key] = parseValue(r.input.value, r.f); }
                catch (e) { errors.push({field:r.key, message:e.message}); }
            }
            if (errors.length) { setValidation(errors); const e = new Error(errors.map(e => `${e.field}: ${e.message}`).join(' ')); e.field_errors = errors; throw e; }
            return values;
        }
        function effectiveValues() {
            const result = {};
            for (const r of rows) {
                if (!r.supplied && own(r.f, 'default')) result[r.key] = r.f.default;
                else if (r.supplied) { try { result[r.key] = parseValue(r.input.value, r.f); } catch (_) { } }
            }
            return result;
        }
        function updateContext(context) {
            for (const r of rows) {
                const active = (descriptor.constraints || []).filter(c => c.field === r.key && matches(c.when, context));
                const inactive = active.some(c => c.kind === 'omit_when') || (descriptor.constraints || []).some(c => c.field === r.key && c.kind === 'allowed_when' && !matches(c.when, context));
                r.row.hidden = !!r.f.ui?.hidden && !r.supplied && !r.error.textContent;
                r.row.classList.toggle('model-control-inactive', inactive);
                // Explicit inactive inputs remain editable, so users can clear them.
                r.input.disabled = inactive && !r.supplied;
                const restrictions = active.filter(c => c.kind === 'allowed_values');
                if (r.f.type === 'enum') for (const item of r.input.options)
                    item.disabled = !!item.value && restrictions.some(c => !(c.values || []).includes(item.value));
                r.label.dataset.required = String(r.f.required || active.some(c => c.kind === 'required_when'));
                r.hint.textContent = [r.f.description || '', own(r.f,'min') ? `Minimum: ${r.f.min}` : '', own(r.f,'max') ? `Maximum: ${r.f.max}` : '', own(r.f,'step') ? `Step: ${r.f.step}` : '', restrictions.length ? 'Choices restricted by current settings.' : '', inactive ? r.supplied ? 'Inactive for these settings. Unset this explicit value to use managed defaults.' : 'Inactive default; managed normalization will omit it.' : '', own(r.f,'default') && !r.supplied ? `Default: ${r.f.default} (not explicitly supplied)` : ''].filter(Boolean).join(' ');
            }
        }
        updateContext({values:effectiveValues(),media:[]});
        return {readOptions, setValidation, effectiveValues, updateContext, dispose() { disposed = true; listeners.forEach(f => f()); container.replaceChildren(); }};
    }
    return {create};
})();
