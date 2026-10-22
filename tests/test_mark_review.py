import csv
import json
import tempfile
import unittest
from pathlib import Path


class MarkReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import cv2
        cls.cv2=cv2
        root=Path(__file__).resolve().parents[1]
        cls.config=json.loads((root/'mcmark/layouts/delia-layout.json').read_text())
        cls.config['template_image']=str(root/'mcmark/layouts/delia-template.png')
        cls.q={**cls.config['questions'][0], 'answer':'C'}
        cls.blank=cv2.imread(cls.config['template_image'],0)

    def fill(self,sheet,label,color=30):
        x,y=self.q['centers'][self.q['labels'].index(label)]
        self.cv2.rectangle(sheet,(round(x-8),round(y-3)),(round(x+8),round(y+3)),color,-1)

    def test_dark_blue_pen_and_normal_fill(self):
        import numpy as np
        from mcmark.vision import detect
        sheet=self.blank.copy()
        # Typical saturated blue pen converted to grayscale.
        blue=int(self.cv2.cvtColor(np.uint8([[[190,35,25]]]),self.cv2.COLOR_BGR2GRAY)[0,0])
        self.fill(sheet,'C',blue)
        reading=detect(sheet,self.q,self.config)
        self.assertEqual(reading['selected'],['C'])
        self.assertFalse(reading['review_reasons'])

    def test_crossed_answer_kept_for_teacher(self):
        from mcmark.vision import detect
        sheet=self.blank.copy()
        self.fill(sheet,'A')
        self.fill(sheet,'C')
        x,y=map(round,self.q['centers'][0])
        self.cv2.line(sheet,(x-12,y-11),(x+12,y+11),0,2)
        self.cv2.line(sheet,(x-12,y+11),(x+12,y-11),0,2)
        reading=detect(sheet,self.q,self.config)
        self.assertEqual(reading['selected'],['A','C'])
        self.assertIn('possible_cross_out',reading['review_reasons'])
        self.assertEqual(reading['suggested_selected'],['C'])

    def test_faint_and_stray_marks_require_review(self):
        from mcmark.vision import detect
        sheet=self.blank.copy()
        self.fill(sheet,'C')
        x,y=map(round,self.q['centers'][0])
        self.cv2.rectangle(sheet,(x-6,y-1),(x-3,y+1),90,-1)
        reading=detect(sheet,self.q,self.config)
        self.assertIn('faint_or_partial_mark',reading['review_reasons'])
        self.cv2.line(sheet,(x-12,y+10),(x+10,y+7),0,2)
        reading=detect(sheet,self.q,self.config)
        self.assertIn('stray_ink_or_cancellation',reading['review_reasons'])

    def test_review_correction_regrades_and_preserves_reading(self):
        from mcmark.vision import detect
        from mcmark.core import grade,export
        from mcmark.review import save_question_crop,write_review,apply_corrections,refresh_review
        sheet=self.blank.copy()
        self.fill(sheet,'A');self.fill(sheet,'C')
        reading=detect(sheet,self.q,self.config)
        config={**self.config,'questions':[self.q]}
        with tempfile.TemporaryDirectory() as tmp:
            reading['review_crop']=save_question_crop(sheet,self.q,Path(tmp)/'review/questions/1.png')
            row=dict(file='/scans/student.png',page=1,sheet_review_issues=[],**grade([reading],config))
            refresh_review(row)
            self.assertTrue(row['score_is_provisional'])
            write_review([row],tmp)
            queue=Path(tmp)/'review_queue.csv'
            with queue.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            rows[0]['decision']='C';rows[0]['note']='A crossed out'
            with queue.open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
            apply_corrections([row],config,queue)
            self.assertEqual(row['score'],1)
            self.assertFalse(row['score_is_provisional'])
            self.assertFalse(row['review_required'])
            self.assertEqual(row['responses'][0]['raw_selected'],['A','C'])
            self.assertEqual(row['responses'][0]['teacher_review']['note'],'A crossed out')
            export([row],config,tmp,[])
            write_review([row],tmp)
            self.assertIn('reviewed',(Path(tmp)/'review.html').read_text())
            # Metadata issues stay pending even when answer review is complete.
            row['sheet_review_issues']=['metadata_unrecognized']
            refresh_review(row)
            self.assertTrue(row['review_required'])
