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

document.querySelectorAll('[data-batch-select]').forEach(button=>button.addEventListener('click',()=>{
 const group=button.closest('details');
 group.querySelectorAll('[data-batch-choice]').forEach(box=>{const image=box.closest('article').querySelector('img');box.checked=!!(image && image.complete && image.naturalWidth);});
 group.querySelector('[data-batch-status]').textContent=group.querySelectorAll('[data-batch-choice]:checked').length+' rows selected. Inspect before confirming.';
}));
document.querySelectorAll('[data-batch-prepare]').forEach(button=>button.addEventListener('click',()=>{
 const group=button.closest('details');let count=0;
 group.querySelectorAll('[data-batch-choice]:checked').forEach(box=>{
  const field=document.getElementById(box.dataset.field);const pending=field.querySelector('input:checked');
  if(!field.disabled && pending && pending.value===''){
   const choice=Array.from(field.querySelectorAll('input')).find(input=>input.value===box.dataset.value);
   if(choice){choice.checked=true;count++;}
  }
 });
 group.querySelector('[data-batch-status]').textContent=count+' decisions prepared. Save to apply; existing decisions were kept.';
}));
