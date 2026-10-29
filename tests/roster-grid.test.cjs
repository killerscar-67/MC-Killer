const {test} = require('node:test');
const assert = require('node:assert/strict');
const {rosterClipboardRows} = require('../mcmark/static/roster-grid.js');
test('Excel/Sheets clipboard preserves Chinese, zeroes, quoted tabs, newlines and quotes', () => {
  assert.deepEqual(rosterClipboardRows('Class\tClass No.\tEnglish Name\tChinese Name\r\n5A\t01\t"Example\tName"\t測試\r\n5B\t2\t"Two\nlines ""quoted"""\t\r\n'),
    [['Class','Class No.','English Name','Chinese Name'],['5A','01','Example\tName','測試'],['5B','2','Two\nlines "quoted"','']]);
  assert.throws(() => rosterClipboardRows('5A\t"unfinished'));
  assert.deepEqual(rosterClipboardRows(''), []);
});
