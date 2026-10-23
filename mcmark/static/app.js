if (document.querySelector('[data-poll]')) {
  window.setTimeout(() => window.location.reload(), 5000);
}
const picker = document.querySelector('input[type=file]');
if (picker) picker.addEventListener('change', () => {
  const count = picker.files.length;
  picker.closest('label').querySelector('strong').textContent = count ? `${count} file${count === 1 ? '' : 's'} selected` : 'Choose your scanned sheets';
});

const pendingFilter=document.getElementById('pending-only');
if(pendingFilter){
 const filterAnswers=()=>document.querySelectorAll('[data-resolved]').forEach(row=>{row.hidden=pendingFilter.checked && row.dataset.resolved==='yes';});
 pendingFilter.addEventListener('change',filterAnswers);filterAnswers();
}
