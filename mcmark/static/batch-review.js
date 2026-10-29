function batchReviewScope(button) {
  return button.closest(button.hasAttribute('data-batch-all') ? 'form' : 'details');
}

function batchImageAvailable(box) {
  const image = box.closest('article').querySelector('img');
  return !!(image && image.complete && image.naturalWidth);
}

function loadBatchImage(box) {
  const image = box.closest('article').querySelector('img');
  if (!image || image.complete) return Promise.resolve(batchImageAvailable(box));
  return new Promise(resolve => {
    const done = () => {
      clearTimeout(timer); image.removeEventListener('load', done); image.removeEventListener('error', done);
      resolve(batchImageAvailable(box));
    };
    const timer = setTimeout(done, 20000);
    image.addEventListener('load', done); image.addEventListener('error', done);
    image.loading = 'eager';
    if (image.complete) done();
  });
}

function prepareBatchChoices(scope, doc) {
  let count = 0; const seen = new Set();
  scope.querySelectorAll('[data-batch-choice]:checked, [data-visual-choice]:checked').forEach(box => {
    if (seen.has(box.dataset.field)) return;
    seen.add(box.dataset.field);
    const field = doc.getElementById(box.dataset.field);
    if (!field || field.disabled || !batchImageAvailable(box)) return;
    const pending = field.querySelector('input:checked');
    if (pending && pending.value === '') {
      const choice = Array.from(field.querySelectorAll('input')).find(input => input.value === box.dataset.value);
      if (choice) { choice.checked = true; count++; }
    }
  });
  return count;
}

if (typeof document !== 'undefined') {
  document.querySelectorAll('[data-visual-filter]').forEach(filter => filter.addEventListener('change', () => {
    filter.closest('details').querySelectorAll('[data-visual-card]').forEach(card => {
      card.hidden = filter.value === 'warnings' && card.dataset.automatic === 'true';
      if (card.hidden) card.querySelector('[data-visual-choice]').checked = false;
    });
  }));
  document.querySelectorAll('[data-batch-select], [data-visual-select]').forEach(button => button.addEventListener('click', async () => {
    const scope = batchReviewScope(button);
    const status = button.closest('.batch-review-tools').querySelector('[data-batch-status]');
    const visual = button.hasAttribute('data-visual-select');
    const boxes = Array.from(scope.querySelectorAll(visual ? '[data-visual-choice]' : '[data-batch-choice]'))
      .filter(box => !visual || !box.closest('[data-visual-card]').hidden);
    // Freeze both group and assessment batch controls while evidence loads.
    const controls = Array.from(button.closest('form').querySelectorAll('[data-batch-select], [data-visual-select], [data-batch-prepare], [data-visual-filter]'));
    controls.forEach(control => { control.disabled = true; });
    status.textContent = `Loading evidence for ${boxes.length} ${visual ? 'displayed' : 'eligible'} rows…`;
    try {
      const available = await Promise.all(boxes.map(loadBatchImage));
      boxes.forEach((box, index) => { box.checked = available[index]; });
      const count = available.filter(Boolean).length;
      status.textContent = `${count} rows selected${count < boxes.length ? `; ${boxes.length - count} unavailable images skipped` : ''}. Inspect before confirming.`;
    } finally { controls.forEach(control => { control.disabled = false; }); }
  }));
  document.querySelectorAll('[data-batch-prepare]').forEach(button => button.addEventListener('click', () => {
    const count = prepareBatchChoices(batchReviewScope(button), document);
    button.closest('.batch-review-tools').querySelector('[data-batch-status]').textContent =
      `${count} decisions prepared. Save to apply; existing decisions were kept.`;
  }));
}
if (typeof module !== 'undefined') module.exports = {batchReviewScope, prepareBatchChoices, loadBatchImage};
