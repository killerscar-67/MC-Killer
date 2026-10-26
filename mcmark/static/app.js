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

document.querySelectorAll('[data-review-target]').forEach(button=>button.addEventListener('click',()=>{
 const field=document.getElementById(button.dataset.reviewTarget);
 if(field && !field.disabled){
  const choice=Array.from(field.querySelectorAll('input[type=radio]')).find(input=>input.value===button.dataset.reviewValue);
  if(choice){choice.checked=true;const details=choice.closest('details');if(details)details.open=true;}
 }
}));
document.querySelectorAll('.multiple-choices input').forEach(input=>input.addEventListener('change',()=>{input.closest('details').open=true;}));
