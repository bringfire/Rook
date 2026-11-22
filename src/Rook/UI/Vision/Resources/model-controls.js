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
    // Display text only. The value submitted for a choice is always the definition's own spelling.
    function displayName(value, type) {
        if (type === 'boolean') return value === true || value === 'true' ? 'On' : 'Off';
        const text = String(value).replace(/_/g, ' ');
        return text.charAt(0).toUpperCase() + text.slice(1);
    }
    function formatExact(units) {
        const negative = units < 0n, magnitude = negative ? -units : units;
        const fraction = (magnitude % scale).toString().padStart(6, '0').replace(/0+$/, '');
        return `${negative ? '-' : ''}${magnitude / scale}${fraction ? '.' + fraction : ''}`;
    }
    // Next value on the declared step grid, by exact arithmetic, kept inside the declared bounds.
    function steppedValue(raw, f, direction) {
        const step = exactNumeric(String(f.step), f), origin = own(f, 'min') ? exactNumeric(String(f.min), f) : 0n;
        let current = null;
        try { if (String(raw).trim() !== '') current = exactNumeric(raw, f); } catch (_) { }
        let next;
        if (current === null) next = own(f, 'default') ? exactNumeric(String(f.default), f) : origin;
        else if (current < origin) next = origin;
        else {
            const offset = current - origin;
            next = direction > 0 ? origin + (offset / step) * step + step : origin + ((offset + step - 1n) / step) * step - step;
        }
        if (own(f, 'max')) { const max = exactNumeric(String(f.max), f); if (next > max) next = origin + ((max - origin) / step) * step; }
        if (next < origin) next = origin;
        return formatExact(next);
    }
    function rangeText(f) {
        if (f.type !== 'integer' && f.type !== 'number') return '';
        const range = own(f, 'min') && own(f, 'max') ? `${f.min} to ${f.max}` : own(f, 'min') ? `At least ${f.min}` : own(f, 'max') ? `At most ${f.max}` : '';
        const steps = own(f, 'step') && !(f.type === 'integer' && Number(f.step) === 1) ? `in steps of ${f.step}` : '';
        return range && steps ? `${range}, ${steps}.` : range ? `${range}.` : steps ? `${steps.charAt(0).toUpperCase()}${steps.slice(1)}.` : '';
    }
    function create(container, descriptor, onChange) {
        const rows = [], listeners = []; let disposed = false;
        const make = (tag, className) => { const node = document.createElement(tag); if (className) node.className = className; return node; };
        container.replaceChildren();
        const basic = make('div', 'model-controls-basic');
        const advanced = make('details', 'model-controls-advanced');
        const summary = make('summary'); summary.textContent = 'Advanced'; advanced.appendChild(summary);
        container.appendChild(basic);
        function listen(node, name, fn) { node.addEventListener(name, fn); listeners.push(() => node.removeEventListener(name, fn)); }
        const fields = [...(descriptor.options || [])].sort((a,b) =>
            (a.ui?.group === 'advanced') - (b.ui?.group === 'advanced') || (a.ui?.order || 0) - (b.ui?.order || 0));
        for (const f of fields) {
            const key = `${f.scope || 'options'}.${f.key}`;
            const row = make('div', 'model-control'); row.dataset.fieldRow = key;
            const label = make('label');
            const name = make('span', 'select-label model-control-name'); name.textContent = f.label || f.key; label.appendChild(name);
            const input = document.createElement(f.type === 'boolean' || f.type === 'enum' ? 'select' : f.type === 'string' ? 'textarea' : 'input');
            input.dataset.field = key; input.dataset.control = 'value'; input.dataset.type = f.type;
            if (input.tagName === 'INPUT') { input.type = 'text'; input.inputMode = f.type === 'integer' ? 'numeric' : 'decimal'; if (!own(f, 'default')) input.placeholder = 'Not set'; }
            if (input.tagName === 'TEXTAREA') input.rows = f.key === 'prompt' ? 4 : 2;
            if (input.tagName === 'SELECT') {
                const absent = document.createElement('option'); absent.value = ''; absent.textContent = own(f, 'default') ? `Default (${displayName(f.default, f.type)})` : 'Not set'; input.appendChild(absent);
                for (const value of f.type === 'boolean' ? ['true', 'false'] : f.values || []) {
                    const option = document.createElement('option'); option.value = value; option.textContent = displayName(value, f.type); input.appendChild(option);
                }
            }
            const reset = make('button', 'btn-text model-control-reset'); reset.type = 'button'; reset.dataset.clear = key;
            reset.textContent = own(f, 'default') ? 'Reset' : 'Clear';
            const hint = make('span', 'option-hint field-hint');
            const error = make('span', 'model-field-error'); error.setAttribute('aria-live', 'polite');
            const record = { f, key, row, label, name, input, reset, hint, error, supplied: false };
            // Reset is offered only where it changes something: a control the user has set.
            function sync() { reset.hidden = !record.supplied || (f.required === true && !own(f, 'default')); }
            function resetValue() { record.supplied = false; input.value = input.tagName === 'SELECT' ? '' : own(f, 'default') ? String(f.default) : ''; sync(); }
            function changed() { if (disposed) return; error.textContent = ''; input.removeAttribute('aria-invalid'); onChange(); }
            resetValue();
            listen(input, input.tagName === 'SELECT' ? 'change' : 'input', () => {
                record.supplied = input.tagName === 'SELECT' || f.type === 'integer' || f.type === 'number' ? input.value !== '' : true;
                sync(); changed();
            });
            listen(reset, 'click', () => { resetValue(); changed(); });
            label.appendChild(input);
            if (input.tagName === 'INPUT' && own(f, 'step')) {
                for (const [direction, text, title] of [[-1, '−', 'Decrease'], [1, '+', 'Increase']]) {
                    const button = make('button', 'model-control-step'); button.type = 'button'; button.textContent = text;
                    button.dataset.step = key; button.dataset.direction = direction > 0 ? 'up' : 'down'; button.setAttribute('aria-label', `${title} ${f.label || f.key}`);
                    listen(button, 'click', () => {
                        try { input.value = steppedValue(input.value, f, direction); } catch (_) { return; }
                        record.supplied = true; sync(); changed();
                    });
                    label.appendChild(button);
                }
            }
            const foot = make('div', 'model-control-foot'); foot.appendChild(hint); foot.appendChild(reset);
            row.appendChild(label); row.appendChild(foot); row.appendChild(error);
            (f.ui?.group === 'advanced' ? advanced : basic).appendChild(row); rows.push(record);
        }
        if (fields.some(f => f.ui?.group === 'advanced')) container.appendChild(advanced);
        const every = () => true;
        function setValidation(errors, include = every) {
            for (const r of rows.filter(include)) {
                const messages = (errors || []).filter(e => e.field === r.key || e.field === r.f.key).map(e => e.message);
                r.error.textContent = messages.join(' ');
                if (messages.length) { r.input.setAttribute('aria-invalid', 'true'); r.row.hidden = false; if(r.f.ui?.group === 'advanced') advanced.open = true; }
                else r.input.removeAttribute('aria-invalid');
            }
        }
        function readOptions(include = every) {
            const values = {}, errors = [];
            for (const r of rows.filter(include)) if (r.supplied) {
                try { values[r.f.key] = parseValue(r.input.value, r.f); }
                catch (e) { errors.push({field:r.key, message:e.message}); }
            }
            if (errors.length) { setValidation(errors, include); const e = new Error(errors.map(e => `${e.field}: ${e.message}`).join(' ')); e.field_errors = errors; throw e; }
            return values;
        }
        function effectiveValues(include = every) {
            const result = {};
            for (const r of rows.filter(include)) {
                if (!r.supplied && own(r.f, 'default')) result[r.key] = r.f.default;
                else if (r.supplied) { try { result[r.key] = parseValue(r.input.value, r.f); } catch (_) { } }
            }
            return result;
        }
        // One rendered list can hold common request fields and provider options; callers read each scope separately.
        function scope(name) {
            const include = r => (r.f.scope || 'options') === name;
            return { readOptions: () => readOptions(include), effectiveValues: () => effectiveValues(include) };
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
                r.label.dataset.required = r.name.dataset.required = String(r.f.required || active.some(c => c.kind === 'required_when'));
                r.reset.hidden = !r.supplied || (r.f.required === true && !own(r.f, 'default'));
                r.hint.textContent = [r.f.description || '', rangeText(r.f),
                    restrictions.length ? 'Some choices are unavailable with the current settings.' : '',
                    inactive ? r.supplied ? 'Not used with the current settings. Reset it to continue.' : 'Not used with the current settings.' : '',
                    own(r.f,'default') && r.supplied ? `Default ${r.f.type === 'boolean' || r.f.type === 'enum' ? displayName(r.f.default, r.f.type) : r.f.default}.` : ''].filter(Boolean).join(' ');
            }
        }
        updateContext({values:effectiveValues(),media:[]});
        return {readOptions: () => readOptions(), setValidation: errors => setValidation(errors), effectiveValues: () => effectiveValues(), updateContext, scope,
            dispose() { disposed = true; listeners.forEach(f => f()); container.replaceChildren(); }};
    }
    return {create, displayName};
})();
