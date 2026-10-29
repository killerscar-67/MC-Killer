/* Plain-text clipboard input only: student data never leaves this application. */
function rosterClipboardRows(text) {
  const rows = []; let row = [], cell = '', quoted = false;
  text = text.replace(/\r\n?/g, '\n');
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"' && (quoted || !cell)) {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++; }
      else quoted = !quoted;
    } else if (!quoted && (ch === '\t' || ch === '\n')) {
      row.push(cell); cell = '';
      if (ch === '\n') { rows.push(row); row = []; }
    } else cell += ch;
  }
  if (quoted) throw new Error('The pasted cells contain an unfinished quote. Copy the cells again.');
  row.push(cell); rows.push(row);
  while (rows.length && rows[rows.length - 1].every(value => !value.trim())) rows.pop();
  return rows;
}

if (typeof document !== 'undefined') {
  const form = document.getElementById('roster-grid-form');
  if (form) {
    const grid = document.getElementById('roster-grid');
    const body = grid.querySelector('tbody');
    const status = document.getElementById('roster-grid-status');
    const columns = ['class', 'number', 'english_name', 'chinese_name', 'active'];
    const initial = JSON.parse(document.getElementById('roster-grid-initial').textContent);
    const blank = () => ({record_id: '', class: '', number: '', english_name: '', chinese_name: '', active: 'true'});
    let rows = initial.length ? initial.map(row => ({...row})) : [blank()];
    const message = text => { status.textContent = text; };
    function read() {
      [...body.rows].forEach((tr, index) => {
        columns.forEach(key => { rows[index][key] = tr.querySelector(`[data-key="${key}"]`).value; });
      });
    }
    function render() {
      body.replaceChildren();
      rows.forEach((row, index) => {
        const tr = document.createElement('tr');
        const number = document.createElement('th'); number.scope = 'row'; number.textContent = index + 1; tr.append(number);
        columns.forEach((key, col) => {
          const td = document.createElement('td');
          const input = document.createElement(key === 'active' ? 'select' : 'input');
          input.dataset.key = key; input.dataset.row = index; input.dataset.col = col;
          input.setAttribute('aria-label', `Row ${index + 1}, ${['Class', 'Class number', 'English name', 'Chinese name', 'Status'][col]}`);
          if (key === 'active') {
            for (const [value, label] of [['true', 'Active'], ['false', 'Inactive']]) {
              const option = document.createElement('option'); option.value = value; option.textContent = label; input.append(option);
            }
          } else {
            input.type = 'text'; input.autocomplete = 'off';
            if (key === 'number') input.inputMode = 'numeric';
          }
          input.value = row[key] || (key === 'active' ? 'true' : '');
          td.append(input); tr.append(td);
        });
        const td = document.createElement('td');
        if (!row.record_id) {
          const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove';
          remove.setAttribute('aria-label', `Remove new row ${index + 1}`);
          remove.addEventListener('click', () => { read(); rows.splice(index, 1); if (!rows.length) rows.push(blank()); render(); });
          td.append(remove);
        } else td.textContent = 'Saved';
        tr.append(td); body.append(tr);
      });
      message(`${rows.length} of 200 rows. Changes are saved only after preview and confirmation.`);
    }
    body.addEventListener('paste', event => {
      const target = event.target.closest('[data-col]'); if (!target) return;
      event.preventDefault();
      try {
        const text = event.clipboardData.getData('text/plain');
        if (text.length > 1024 * 1024) throw new Error('Paste up to 200 students at a time.');
        let pasted = rosterClipboardRows(text);
        const startRow = Number(target.dataset.row), startCol = Number(target.dataset.col);
        const norm = value => value.trim().toLowerCase().replace(/[ .-]+/g, '_').replace(/^_+|_+$/g, '');
        if (startCol === 0 && pasted.length && ['class', '班別'].includes(norm(pasted[0][0])) && ['number', 'class_no', 'class_number', '班號'].includes(norm(pasted[0][1] || ''))) pasted = pasted.slice(1);
        if (!pasted.length) return;
        if (startRow + pasted.length > 200 || pasted.some(row => startCol + row.length > columns.length)) throw new Error('Use up to 200 rows and four name/identity columns, plus an optional Status column.');
        // Validate the whole paste before touching any cells.
        pasted.forEach(row => row.forEach((value, col) => {
          if (startCol + col === 4 && !['true', 'false', 'active', 'inactive', 'yes', 'no', '1', '0'].includes(value.trim().toLowerCase())) throw new Error('Status must be Active or Inactive.');
        }));
        read();
        while (rows.length < startRow + pasted.length) rows.push(blank());
        pasted.forEach((row, offset) => row.forEach((value, col) => {
          const key = columns[startCol + col];
          rows[startRow + offset][key] = key === 'active' ? (['true', 'active', 'yes', '1'].includes(value.trim().toLowerCase()) ? 'true' : 'false') : value.trim();
        }));
        render(); body.rows[startRow].querySelector(`[data-col="${startCol}"]`).focus();
        message(`Pasted ${pasted.length} rows. Check the cells, then preview changes.`);
      } catch (error) { message(error.message); }
    });
    document.getElementById('roster-grid-add').addEventListener('click', () => {
      read(); if (rows.length >= 200) { message('The roster is limited to 200 students.'); return; }
      rows.push(blank()); render(); body.lastElementChild.querySelector('input').focus();
    });
    document.getElementById('roster-grid-reset').addEventListener('click', () => {
      if (!window.confirm('Discard unsaved grid edits?')) return;
      rows = initial.length ? initial.map(row => ({...row})) : [blank()]; render();
    });
    form.addEventListener('submit', () => { read(); document.getElementById('roster-grid-data').value = JSON.stringify(rows); });
    grid.hidden = false; render();
  }
}
if (typeof module !== 'undefined') module.exports = {rosterClipboardRows};
