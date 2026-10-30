import copy
import unittest
from mcmark.vision import apply_review_policy


class ReviewPolicyTests(unittest.TestCase):
    def reading(self):
        return {'selected':['B'],'densities':{'A':0,'B':.2},
                'review_reasons':['faint_or_partial_mark','thin_stroke_candidate'],
                'alignment_score':.8,'mark_clues':{
                    'A':{'new_ink_pixels':0},
                    'B':{'stroke_area':18,'stroke_span':9,'new_ink_pixels':18}}}

    def test_isolated_mark_accepted_with_diagnostic_reasons_preserved(self):
        r=apply_review_policy(self.reading(),{})
        self.assertEqual(r['selected'],['B'])
        self.assertEqual(r['review_reasons'],[])
        self.assertIn('thin_stroke_candidate',r['original_review_reasons'])

    def test_ambiguity_and_weak_evidence_remain_pending(self):
        for change in ['cross','diagonal','competing','registration','weak','density','multiple']:
            with self.subTest(change=change):
                r=self.reading()
                if change=='cross':r['review_reasons'].append('possible_cross_out')
                if change=='diagonal':r['mark_clues']['B']['diagonal_clue']=True
                if change=='competing':r['mark_clues']['A']['new_ink_pixels']=3
                if change=='registration':r['alignment_score']=.6
                if change=='weak':r['mark_clues']['B']['stroke_area']=8
                if change=='density':r['densities']['B']=.01
                if change=='multiple':r['selected']=['A','B']
                self.assertTrue(apply_review_policy(r,{})['review_reasons'])
        self.assertTrue(apply_review_policy(self.reading(),{'review_policy':'conservative'})['review_reasons'])

    def test_modest_acceptance_limits_and_minor_spill(self):
        r=self.reading();r['alignment_score']=.70;r['mark_clues']['B']['stroke_area']=10
        self.assertEqual(apply_review_policy(r,{})['review_reasons'],[])
        for field,value in [('alignment',.699),('area',9),('span',6),('density',.079)]:
            r=self.reading()
            if field=='alignment':r['alignment_score']=value
            elif field=='density':r['densities']['B']=value
            else:r['mark_clues']['B']['stroke_'+field]=value
            self.assertTrue(apply_review_policy(r,{})['review_reasons'])
        r=self.reading();r['review_reasons']=['stray_ink_or_cancellation']
        r['mark_clues']['B']['outside_ink_pixels']=16;r['mark_clues']['A']['outside_ink_pixels']=4
        accepted=apply_review_policy(copy.deepcopy(r),{})
        self.assertEqual(accepted['review_reasons'],[])
        self.assertEqual(accepted['original_review_reasons'],['stray_ink_or_cancellation'])
        self.assertEqual(accepted['auto_accept_reason'],'isolated_mark_minor_spill')
        for option,field,value in [('B','outside_ink_pixels',17),('A','outside_ink_pixels',5),('A','diagonal_clue',True),('B','cross_suspected',True)]:
            unsafe=copy.deepcopy(r);unsafe['mark_clues'][option][field]=value
            self.assertTrue(apply_review_policy(unsafe,{})['review_reasons'])
        del r['mark_clues']['A']['outside_ink_pixels']
        self.assertTrue(apply_review_policy(r,{})['review_reasons'])
