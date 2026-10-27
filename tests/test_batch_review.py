import unittest
from mcmark.review import batch_review_eligible


class BatchReviewEligibilityTests(unittest.TestCase):
    def test_only_visual_single_choice_candidates_are_eligible(self):
        a={'selected':['B'],'review_reasons':['stray_ink_or_cancellation'],'mark_clues':{}}
        self.assertTrue(batch_review_eligible(a))
        for reason in ('multiple','blank','possible_cross_out','possible_cancellation_stroke','uncertain_local_alignment','ambiguous_thin_marks'):
            self.assertFalse(batch_review_eligible({**a,'review_reasons':[reason]}))
        self.assertFalse(batch_review_eligible({**a,'selected':['B','C']}))
        self.assertFalse(batch_review_eligible({**a,'teacher_review':{'decision':['B']}}))
        for clue in ('cross_suspected','diagonal_clue'):
            self.assertFalse(batch_review_eligible({**a,'mark_clues':{'B':{clue:True}}}))
