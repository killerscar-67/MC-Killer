const {test} = require('node:test');
const assert = require('node:assert/strict');
const {batchReviewScope, prepareBatchChoices, loadBatchImage} = require('../mcmark/static/batch-review.js');

test('assessment scope covers all groups while question scope stays local', () => {
  const form = {}, details = {};
  const button = all => ({hasAttribute: () => all, closest: selector => selector === 'form' ? form : details});
  assert.equal(batchReviewScope(button(true)), form);
  assert.equal(batchReviewScope(button(false)), details);
});

test('cross-question preparation preserves manual decisions and excludes unavailable images', () => {
  const fields = {}, choices = [];
  const box = (id, current, pending, complete = true, naturalWidth = 100) => {
    const choice = {value:current, checked:false}; choices.push(choice);
    fields[id] = {querySelector: () => ({value:pending}), querySelectorAll: () => [choice]};
    return {dataset:{field:id, value:current}, closest: () => ({querySelector: () => ({complete, naturalWidth})})};
  };
  const boxes = [box('s0q1','A',''), box('s1q2','B',''), box('s2q3','C','D'), box('s3q4','A','',true,0)];
  assert.equal(prepareBatchChoices({querySelectorAll: () => boxes}, {getElementById: id => fields[id]}), 2);
  assert.deepEqual(choices.map(choice => choice.checked), [true,true,false,false]);
});

test('eligible lazy images load before selection; missing images are skipped', async () => {
  const listeners = {};
  const image = {complete:false,naturalWidth:0,addEventListener:(type,callback) => {listeners[type]=callback;},removeEventListener:type => {delete listeners[type];},
    set loading(value) {assert.equal(value,'eager'); this.complete=true; this.naturalWidth=100; listeners.load();}};
  assert.equal(await loadBatchImage({closest: () => ({querySelector: () => image})}),true);
  assert.equal(await loadBatchImage({closest: () => ({querySelector: () => null})}),false);
});

test('compact and detailed selections refer to one logical decision', () => {
  const choice = {value:'B',checked:false};
  const entry = {dataset:{field:'decision-s0q1',value:'B'},closest:() => ({querySelector:() => ({complete:true,naturalWidth:100})})};
  const field = {querySelector:() => ({value:''}),querySelectorAll:() => [choice]};
  assert.equal(prepareBatchChoices({querySelectorAll:() => [entry,entry]}, {getElementById:() => field}),1);
});
