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
