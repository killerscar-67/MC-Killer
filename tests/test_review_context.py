import copy
import unittest
import cv2
import numpy as np
from mcmark.vision import apply_review_policy, surrounding_ink, verify_choice_stability, stroke_features


class ReviewContextTests(unittest.TestCase):
    def fixture(self):
        ref=np.full((100,100),255,np.uint8)
        grid={'sample_box':[14,4],'labels':['A','B','C','D'],
              'centers':[[20,50],[40,50],[60,50],[80,50]]}
        for x,y in grid['centers']:cv2.rectangle(ref,(x-9,y-4),(x+9,y+4),0,1)
        sheet=ref.copy();cv2.rectangle(sheet,(33,48),(47,52),30,-1)
        return ref,sheet,grid

    def reading(self):
        return {'selected':['B'],'densities':{'A':0,'B':.9,'C':0,'D':0},
                'alignment_score':.65,'printed_alignment':{'verified':True,'score':.9},
                'choice_stability':{'verified':True},'review_reasons':['stray_ink_or_cancellation'],
                'mark_clues':{o:dict(new_ink_pixels=0,outside_ink_pixels=0,detached_spill_pixels=0)
                              for o in 'ABCD'}}

    def test_remote_component_never_enters_box_safety_margin(self):
        ref=np.full((100,100),255,np.uint8);sheet=ref.copy()
        cv2.line(sheet,(63,57),(65,60),0,1)
        clue=surrounding_ink(sheet,ref,{'sample_box':[14,4]},(50,50),{})
        self.assertGreater(clue['remote_outside_ink_pixels'],0)
        self.assertEqual(clue['remote_outside_ink_pixels'],clue['outside_ink_pixels'])
        # Extending the same component into the safety margin revokes exclusion.
        cv2.line(sheet,(57,51),(65,60),0,1)
        clue=surrounding_ink(sheet,ref,{'sample_box':[14,4]},(50,50),{})
        self.assertEqual(clue['remote_outside_ink_pixels'],0)
        self.assertGreater(clue['outside_ink_pixels'],0)

    def test_remote_blank_option_ink_requires_stability_and_keeps_evidence(self):
        r=self.reading();r['mark_clues']['B'].update(stroke_area=30,stroke_span=14,compact_fill=True)
        r['mark_clues']['D'].update(outside_ink_pixels=20,detached_spill_pixels=20,remote_outside_ink_pixels=20)
        a=apply_review_policy(copy.deepcopy(r),{})
        self.assertFalse(a['review_reasons']);self.assertEqual(a['remote_ink_excluded_options'],['D'])
        self.assertEqual(a['mark_clues']['D']['outside_ink_pixels'],20)
        self.assertEqual(a['original_review_reasons'],['stray_ink_or_cancellation'])
        for change in ('unstable','near_box','competing','cross','diagonal','conservative'):
            with self.subTest(change=change):
                v=copy.deepcopy(r)
                if change=='unstable':v['choice_stability']['verified']=False
                if change=='near_box':v['mark_clues']['D']['remote_outside_ink_pixels']=0
                if change=='competing':v['mark_clues']['D']['new_ink_pixels']=3
                if change=='cross':v['mark_clues']['D']['cross_suspected']=True
                if change=='diagonal':v['mark_clues']['D']['diagonal_clue']=True
                self.assertTrue(apply_review_policy(v,{'review_policy':'conservative'} if change=='conservative' else {})['review_reasons'])

    def test_selected_option_remote_spill_is_never_subtracted(self):
        r=self.reading();r['mark_clues']['B'].update(stroke_area=30,stroke_span=14,
            outside_ink_pixels=30,detached_spill_pixels=30,remote_outside_ink_pixels=30)
        self.assertTrue(apply_review_policy(r,{})['review_reasons'])

    def test_horizontal_fill_requires_stability_alignment_and_no_diagonals(self):
        r=self.reading();r['mark_clues']['B'].update(stroke_area=30,stroke_span=14,
            horizontal_fill=True,outside_ink_pixels=12,detached_spill_pixels=12)
        a=apply_review_policy(copy.deepcopy(r),{})
        self.assertFalse(a['review_reasons']);self.assertEqual(a['auto_accept_reason'],'isolated_horizontal_fill')
        for change in ('unstable','no_anchor','low_anchor','diagonal','extended_cross','competing','unresolved'):
            with self.subTest(change=change):
                v=copy.deepcopy(r)
                if change=='unstable':v['choice_stability']['verified']=False
                if change=='no_anchor':v['printed_alignment']['verified']=False
                if change=='low_anchor':v['printed_alignment']['score']=.699
                if change=='diagonal':v['mark_clues']['B']['diagonal_clue']=True
                if change=='extended_cross':v['mark_clues']['B']['extended_cross_clue']=True
                if change=='competing':v['mark_clues']['C']['new_ink_pixels']=3
                if change=='unresolved':v['review_reasons'].append('unresolved_competing_ink')
                self.assertTrue(apply_review_policy(v,{})['review_reasons'])

    def test_stability_checks_template_subtraction_at_fifteen_variants(self):
        ref,sheet,g=self.fixture();a=verify_choice_stability(sheet,g,['B'],{},ref)
        self.assertTrue(a['verified']);self.assertEqual(a['trials'],15)
        self.assertEqual(a['maximum_other_ink_coverage'],0)
        cv2.rectangle(sheet,(53,48),(67,52),170,-1)
        self.assertFalse(verify_choice_stability(sheet,g,['B'],{},ref)['verified'])

    def test_stability_rejects_faint_and_empty_marks_and_out_of_bounds(self):
        ref,sheet,g=self.fixture()
        self.assertFalse(verify_choice_stability(ref,g,['B'],{},ref)['verified'])
        cv2.rectangle(sheet,(33,48),(47,52),170,-1)
        self.assertFalse(verify_choice_stability(sheet,g,['B'],{},ref)['verified'])
        g['centers'][0]=[1,1]
        self.assertFalse(verify_choice_stability(sheet,g,['B'],{},ref)['verified'])

    def test_horizontal_body_is_not_a_vertical_or_clipped_stroke(self):
        ref,sheet,g=self.fixture();v=stroke_features(sheet,ref,g,(40,50),{})
        self.assertTrue(v['horizontal_fill'])
        vertical=ref.copy();cv2.rectangle(vertical,(38,40),(42,60),0,-1)
        self.assertFalse(stroke_features(vertical,ref,g,(40,50),{})['horizontal_fill'])
        clipped=ref.copy();cv2.rectangle(clipped,(20,48),(60,52),0,-1)
        self.assertFalse(stroke_features(clipped,ref,g,(40,50),{})['horizontal_fill'])
