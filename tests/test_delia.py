"""Checks calibrated coordinates against the actual blank sheet and synthetic marks."""
import json
import unittest
from pathlib import Path

class DeliaLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import cv2
        cls.cv2=cv2
        root=Path(__file__).resolve().parents[1]
        cls.config=json.loads((root/'mcmark/layouts/delia-layout.json').read_text())
        cls.config['template_image']=str(root/'mcmark/layouts/delia-template.png')
        cls.blank=cv2.imread(cls.config['template_image'],0)

    def test_all_400_boxes_are_blank(self):
        from mcmark.vision import align,detect
        registered=align(self.blank,self.config)
        self.assertEqual(len(self.config['questions']),100)
        self.assertTrue(all(not detect(registered,q,self.config)['selected'] for q in self.config['questions']))

    def test_marked_and_skewed_sheet(self):
        import numpy as np
        from mcmark.vision import align,detect
        sheet=self.blank.copy()
        expected=[]
        for i,q in enumerate(self.config['questions']):
            labels=[] if i==0 else ['A','C'] if i==1 else [q['labels'][i%4]]
            expected.append(labels)
            for label in labels:
                x,y=q['centers'][q['labels'].index(label)]
                self.cv2.rectangle(sheet,(round(x-8),round(y-3)),(round(x+8),round(y+3)),40,-1)
        h,w=sheet.shape
        matrix=self.cv2.getRotationMatrix2D((w/2,h/2),1.0,.98)
        shifted=self.cv2.warpAffine(sheet,matrix,(w,h),borderValue=255)
        registered=align(shifted,self.config)
        self.assertEqual([detect(registered,q,self.config)['selected'] for q in self.config['questions']],expected)

    def test_unrelated_image_rejected(self):
        import numpy as np
        from mcmark.vision import align
        with self.assertRaises(ValueError):
            align(np.full_like(self.blank,255),self.config)

    def test_exam_key_selects_only_used_questions(self):
        import sys
        import tempfile
        from unittest.mock import patch
        from mcmark.cli import main
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            key=Path(tmp)/'answers.json'
            key.write_text(json.dumps({'1':'B','3':'D','25':'A'}))
            with patch.object(sys,'argv',['mcmark','scans','--config',str(root/'mcmark/layouts/delia-layout.json'),'--key',str(key)]), patch('mcmark.cli.run',return_value=0) as run:
                with self.assertRaises(SystemExit) as exit:
                    main()
                self.assertEqual(exit.exception.code,0)
                config=run.call_args.args[1]
                self.assertEqual([q['id'] for q in config['questions']],['1','3','25'])
                self.assertEqual([q['answer'] for q in config['questions']],['B','D','A'])
                self.assertTrue(Path(config['template_image']).is_file())
