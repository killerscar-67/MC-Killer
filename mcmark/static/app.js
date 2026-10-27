if (document.querySelector('[data-poll]')) {
  window.setTimeout(() => window.location.reload(), 5000);
}
const picker = document.querySelector('input[name=scans]');
if (picker) picker.addEventListener('change', () => {
  const count = picker.files.length;
  picker.closest('label').querySelector('strong').textContent = count ? `${count} file${count === 1 ? '' : 's'} selected` : 'Choose your scanned sheets';
});

const rosterForm=document.getElementById('roster-assessment');
if(rosterForm){
 const file=document.getElementById('roster-file');
 const preview=document.getElementById('roster-preview');
 const status=document.getElementById('roster-status');
 const digest=document.getElementById('roster-digest');
 const confirmed=document.getElementById('roster-order-confirmed');
 const start=document.getElementById('start-roster-marking');
 const button=document.getElementById('preview-roster');
 let generation=0;
 const reset=()=>{generation++;preview.replaceChildren();digest.value='';confirmed.checked=false;start.disabled=true;status.textContent='Preview the class list, then mark absentees.';};
 file.addEventListener('change',reset);
 confirmed.addEventListener('change',()=>{start.disabled=!digest.value || !confirmed.checked;});
 button.addEventListener('click',async()=>{
  reset();const current=generation;
  if(!file.files.length){status.textContent='Choose a class-list CSV first.';return;}
  const data=new FormData();data.append('csrf',rosterForm.elements.csrf.value);data.append('roster',file.files[0]);
  button.disabled=true;
  try{
   const response=await fetch(button.dataset.url,{method:'POST',body:data});
   if(!response.headers.get('content-type')?.includes('application/json'))throw new Error('Sign in again and preview the class list.');
   const result=await response.json();if(current!==generation)return;
   if(!response.ok)throw new Error(result.error||'Cannot preview the class list.');
   digest.value=result.digest;
   const table=document.createElement('table');
   const head=document.createElement('thead');const headers=document.createElement('tr');
   ['Absent','Class','Number','Name'].forEach(text=>{const cell=document.createElement('th');cell.textContent=text;headers.append(cell);});head.append(headers);table.append(head);
   const body=document.createElement('tbody');
   const update=()=>{confirmed.checked=false;start.disabled=true;const absent=preview.querySelectorAll('input:checked').length;status.textContent=`${result.students.length} students · ${absent} absent · ${result.students.length-absent} exam sheets expected.`;};
   result.students.forEach(student=>{
    const row=document.createElement('tr');const cell=document.createElement('td');const input=document.createElement('input');
    input.type='checkbox';input.name='absent';input.value=student.student_id;input.setAttribute('aria-label',`Absent: ${student.student_id} ${student.name}`);input.addEventListener('change',update);cell.append(input);row.append(cell);
    [student.class,student.student_id,student.name].forEach(text=>{const td=document.createElement('td');td.textContent=text;row.append(td);});body.append(row);
   });table.append(body);preview.append(table);update();
  }catch(error){if(current===generation){digest.value='';status.textContent=error.message;start.disabled=true;}}
  finally{button.disabled=false;}
 });
 picker?.addEventListener('change',()=>{
  const order=document.getElementById('scan-order');order.replaceChildren();
  Array.from(picker.files).forEach(file=>{const item=document.createElement('li');item.textContent=file.name;order.append(item);});
  confirmed.checked=false;start.disabled=true;
 });
}

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
