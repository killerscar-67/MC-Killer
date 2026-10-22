if (document.querySelector('[data-poll]')) {
  window.setTimeout(() => window.location.reload(), 5000);
}
const picker = document.querySelector('input[type=file]');
if (picker) picker.addEventListener('change', () => {
  const count = picker.files.length;
  picker.closest('label').querySelector('strong').textContent = count ? `${count} file${count === 1 ? '' : 's'} selected` : 'Choose your scanned sheets';
});
