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

    def test_isolated_thin_strokes_keep_evidence_and_faint_strokes_stay_pending(self):
        from mcmark.vision import detect
        for color in (30,170):
            sheet=self.blank.copy()
            x,y=map(round,self.q['centers'][0])
            self.cv2.line(sheet,(x-5,y),(x+5,y),color,1)
            result=detect(sheet,self.q,self.config)
            self.assertEqual(result['selected'],['A'])
            self.assertEqual(result['suggested_selected'],['A'])
            self.assertIn('thin_stroke_candidate',result['original_review_reasons'])
            if color==30:
                self.assertEqual(result['review_reasons'],[])
                self.assertEqual(result['auto_accept_reason'],'isolated_registered_stroke')
            else:self.assertIn('thin_stroke_candidate',result['review_reasons'])
            self.assertNotIn('blank',result['review_reasons'])
            self.assertEqual(result['raw_selected'],[])

    def test_loops_and_circles_are_not_crossed_choices(self):
        from mcmark.vision import detect
        for axes in ((7,4),(10,8),(12,10)):
            for thickness in (1,2):
                with self.subTest(axes=axes,thickness=thickness):
                    sheet=self.blank.copy()
                    x,y=map(round,self.q['centers'][1])
                    self.cv2.ellipse(sheet,(x,y),axes,0,0,360,0,thickness)
                    result=detect(sheet,self.q,self.config)
                    self.assertNotIn('possible_cross_out',result['review_reasons'])
                    self.assertNotEqual(result['mark_clues']['B'].get('state'),'likely_cancelled')

    def test_looped_selection_does_not_cancel_another_choice(self):
        from mcmark.vision import detect
        sheet=self.blank.copy();self.fill(sheet,'A')
        x,y=map(round,self.q['centers'][1])
        self.cv2.ellipse(sheet,(x,y),(7,4),0,0,360,0,2)
        result=detect(sheet,self.q,self.config)
        self.assertIn('A',result['selected'])
        self.assertIn('B',result['selected'])
        self.assertIn('multiple',result['review_reasons'])
        self.assertIsNone(result['suggested_selected'])

    def test_cross_over_loop_still_needs_review(self):
        from mcmark.vision import detect
        sheet=self.blank.copy();self.fill(sheet,'A')
        x,y=map(round,self.q['centers'][1])
        self.cv2.ellipse(sheet,(x,y),(7,4),0,0,360,0,1)
        self.cv2.line(sheet,(x-10,y-9),(x+10,y+9),0,2)
        self.cv2.line(sheet,(x-10,y+9),(x+10,y-9),0,2)
        result=detect(sheet,self.q,self.config)
        self.assertIn('possible_cross_out',result['review_reasons'])
        self.assertEqual(result['suggested_selected'],['A'])

    def test_compact_cross_and_cross_over_fill_suggest_other_answer(self):
        from mcmark.vision import detect
        for filled in (False,True):
            sheet=self.blank.copy(); self.fill(sheet,'A')
            if filled: self.fill(sheet,'C')
            x,y=map(round,self.q['centers'][2])
            self.cv2.line(sheet,(x-7,y-6),(x+7,y+6),0,1)
            self.cv2.line(sheet,(x-7,y+6),(x+7,y-6),0,1)
            result=detect(sheet,self.q,self.config)
            self.assertEqual(result['suggested_selected'],['A'])
            self.assertEqual(result['mark_clues']['C']['state'],'likely_cancelled')
            self.assertIn('possible_cross_out',result['review_reasons'])
            if filled: self.assertEqual(result['raw_selected'],['A','C'])

    def test_single_slash_requires_review_without_discard(self):
        from mcmark.vision import detect
        sheet=self.blank.copy();self.fill(sheet,'A');self.fill(sheet,'C')
        x,y=map(round,self.q['centers'][2])
        self.cv2.line(sheet,(x-8,y-7),(x+8,y+7),0,1)
        result=detect(sheet,self.q,self.config)
        self.assertEqual(result['selected'],['A','C'])
        self.assertIsNone(result['suggested_selected'])
        self.assertIn('possible_cancellation_stroke',result['review_reasons'])

    def test_blank_speck_and_registration_shift_have_no_thin_candidates(self):
        from mcmark.vision import detect
        import numpy as np
        for dx,dy in ((0,0),(1,0),(0,1),(-1,-1)):
            sheet=self.cv2.warpAffine(self.blank,np.float32([[1,0,dx],[0,1,dy]]),
                                      (self.blank.shape[1],self.blank.shape[0]),borderValue=255)
            x,y=map(round,self.q['centers'][0]);sheet[y,x]=0
            result=detect(sheet,self.q,self.config)
            self.assertEqual(result['thin_candidates'],[])
            self.assertFalse(any(v['compact_cross_suspected'] for v in result['mark_clues'].values()))

    def test_detection_does_not_depend_on_answer_key(self):
        from mcmark.vision import detect
        sheet=self.blank.copy();self.fill(sheet,'A');self.fill(sheet,'C')
        x,y=map(round,self.q['centers'][2])
        self.cv2.line(sheet,(x-7,y-6),(x+7,y+6),0,1)
        self.cv2.line(sheet,(x-7,y+6),(x+7,y-6),0,1)
        self.assertEqual(detect(sheet,{**self.q,'answer':'A'},self.config),
                         detect(sheet,{**self.q,'answer':'C'},self.config))

    def test_multiple_weak_strokes_are_not_promoted_to_selections(self):
        from mcmark.vision import detect
        sheet=self.blank.copy()
        for x,y in self.q['centers']:
            x,y=round(x),round(y)
            self.cv2.line(sheet,(x-5,y),(x+5,y),30,1)
        result=detect(sheet,self.q,self.config)
        self.assertEqual(result['selected'],[])
        self.assertEqual(len(result['thin_candidates']),4)
        self.assertIn('ambiguous_thin_marks',result['review_reasons'])
        self.assertIsNone(result['suggested_selected'])

    def test_local_row_alignment_recovers_shifted_thin_mark(self):
        from mcmark.vision import detect
        import numpy as np
        sheet=self.blank.copy();x,y=map(round,self.q['centers'][0])
        self.cv2.line(sheet,(x-5,y),(x+5,y),30,1)
        shifted=self.cv2.warpAffine(sheet,np.float32([[1,0,2],[0,1,-3]]),
                                    (sheet.shape[1],sheet.shape[0]),borderValue=255)
        result=detect(shifted,self.q,self.config)
        self.assertEqual(result['selected'],['A'])
        self.assertEqual(result['local_offset'],[2,-3])
        self.assertIn('thin_stroke_candidate',result['original_review_reasons'])
        self.assertEqual(result['auto_accept_reason'],'isolated_registered_stroke')

    def test_failed_local_registration_suppresses_weak_candidates(self):
        from mcmark.vision import detect
        from unittest.mock import patch
        import numpy as np
        sheet=self.blank.copy();x,y=map(round,self.q['centers'][0])
        self.cv2.line(sheet,(x-5,y),(x+5,y),30,1)
        with patch('mcmark.vision.cv2.matchTemplate',return_value=np.zeros((11,11),np.float32)):
            result=detect(sheet,self.q,self.config)
        self.assertEqual(result['selected'],[])
        self.assertIn('uncertain_local_alignment',result['review_reasons'])

    def test_lone_cross_candidate_is_ambiguous_not_discarded(self):
        from mcmark.vision import detect
        sheet=self.blank.copy();x,y=map(round,self.q['centers'][0])
        self.cv2.line(sheet,(x-7,y-6),(x+7,y+6),0,1)
        self.cv2.line(sheet,(x-7,y+6),(x+7,y-6),0,1)
        result=detect(sheet,self.q,self.config)
        self.assertEqual(result['selected'],['A'])
        self.assertEqual(result['mark_clues']['A']['state'],'ambiguous')
        self.assertIn('possible_cross_out',result['review_reasons'])
        self.assertIsNone(result['suggested_selected'])

    def test_bounded_local_retry_recovers_residual_drift(self):
        from mcmark.vision import detect
        import numpy as np
        for dx,dy in ((6,-7),(-7,6),(8,0),(0,5),(0,9),(0,12)):
            with self.subTest(offset=(dx,dy)):
                sheet=self.blank.copy();self.fill(sheet,'C')
                shifted=self.cv2.warpAffine(sheet,np.float32([[1,0,dx],[0,1,dy]]),(sheet.shape[1],sheet.shape[0]),borderValue=255)
                result=detect(shifted,self.q,self.config)
                self.assertEqual(result['selected'],['C'])
                self.assertEqual(result['local_offset'],[dx,dy])
                self.assertIn(result['local_search_radius'],(9,14))
                self.assertIn('alignment_recovery',result)
                self.assertNotIn('uncertain_local_alignment',result['review_reasons'])

    def test_retry_search_boundary_still_requires_review(self):
        from mcmark.vision import detect
        import numpy as np
        sheet=self.blank.copy();self.fill(sheet,'C')
        shifted=self.cv2.warpAffine(sheet,np.float32([[1,0,0],[0,1,14]]),(sheet.shape[1],sheet.shape[0]),borderValue=255)
        result=detect(shifted,self.q,self.config)
        self.assertIn('uncertain_local_alignment',result['review_reasons'])
        self.assertFalse(result.get('auto_accept_reason'))

    def test_equal_offset_retry_tolerates_match_score_roundoff(self):
        from mcmark.vision import detect
        from unittest.mock import patch
        import numpy as np
        sheet=self.blank.copy();self.fill(sheet,'C')
        shifted=self.cv2.warpAffine(sheet,np.float32([[1,0,0],[0,1,5]]),(sheet.shape[1],sheet.shape[0]),borderValue=255)
        original=self.cv2.matchTemplate
        def rounded(window,target,method):
            scores=original(window,target,method)
            return scores-0.0001 if scores.shape[0]>11 else scores
        with patch('mcmark.vision.cv2.matchTemplate',side_effect=rounded):result=detect(shifted,self.q,self.config)
        self.assertEqual(result['selected'],['C'])
        self.assertNotIn('uncertain_local_alignment',result['review_reasons'])
        self.assertEqual(result['local_offset'],[0,5])

    def test_small_partial_mark_is_provisional_but_nearby_speck_is_not(self):
        from mcmark.vision import detect
        x,y=map(round,self.q['centers'][3])
        for offset,expected in ((-2,['D']),(-3,[])):
            sheet=self.blank.copy()
            self.cv2.rectangle(sheet,(x,y+offset),(x+2,y+offset+2),0,-1)
            result=detect(sheet,self.q,self.config)
            self.assertEqual(result['selected'],expected)
            self.assertTrue(result['review_reasons'])
            self.assertFalse(result.get('auto_accept_reason'))

    def test_extended_diagonal_never_discards_current_choices(self):
        from mcmark.vision import detect
        sheet=self.blank.copy();self.fill(sheet,'A');self.fill(sheet,'C')
        x,y=map(round,self.q['centers'][2])
        self.cv2.line(sheet,(x-10,y-10),(x+10,y+10),0,2)
        result=detect(sheet,self.q,self.config)
        self.assertEqual(result['selected'],['A','C'])
        self.assertIn('multiple',result['review_reasons'])
        self.assertFalse(result.get('auto_accept_reason'))

    def test_registration_retries_without_relaxing_geometry(self):
        from mcmark.vision import align
        from unittest.mock import patch
        original=self.cv2.findHomography
        calls=[]
        def fail_first(*args,**kwargs):
            calls.append(1)
            return (None,None) if len(calls)==1 else original(*args,**kwargs)
        with patch('mcmark.vision.cv2.findHomography',side_effect=fail_first):
            result=align(self.blank,self.config)
        self.assertEqual(len(calls),2)
        self.assertEqual(result.shape,self.blank.shape)
