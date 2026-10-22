import json
import tempfile
import unittest
from pathlib import Path
from mcmark.core import grade, validate, export

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.config = {'page_size':[100,100], 'questions':[{'id':str(i),'labels':['A','B'],'centers':[[20,20],[40,20]],'answer':'A','weight':2 if i==3 else 1} for i in range(4)],'scoring':{'correct':1,'wrong':-.25},'pass_percent':50}
    def test_scoring(self):
        result=grade([{'selected':s} for s in [['A'],['B'],[],['A','B']]],validate(self.config))
        self.assertEqual(result['score'],.75)
        self.assertEqual(result['maximum'],5)
        self.assertEqual([a['status'] for a in result['responses']],['correct','wrong','blank','multiple'])
    def test_export(self):
        result=dict(file='=bad.png',page=1,**grade([{'selected':['A']}]*4,self.config))
        with tempfile.TemporaryDirectory() as d:
            export([result],self.config,d,[])
            self.assertIn("'=bad.png",(Path(d)/'students.csv').read_text(encoding='utf-8-sig'))
            self.assertEqual(json.loads((Path(d)/'results.json').read_text())[0]['percent'],100)
    def test_invalid_key(self):
        self.config['questions'][0]['answer']='C'
        with self.assertRaises(ValueError): validate(self.config)

if __name__=='__main__': unittest.main()
