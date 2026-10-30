import unittest
import numpy as np
from mcmark.vision import verify_printed_anchors


class PrintedAlignmentTests(unittest.TestCase):
    def fixture(self,offset=(1,-1),pad=5):
        target=np.full((41,100),255,np.uint8)
        target[:12]=np.random.default_rng(42).integers(0,256,(12,100),dtype=np.uint8)
        window=np.full((41+2*pad,100+2*pad),255,np.uint8)
        dx,dy=offset;window[pad+dy:pad+dy+41,pad+dx:pad+dx+100]=target
        # Answer ink changes the body, never the printed anchor.
        window[pad+dy+18:pad+dy+25,pad+dx+30:pad+dx+45]=0
        return window,target

    def test_unique_anchor_agrees_without_using_answer_ink(self):
        window,target=self.fixture()
        r=verify_printed_anchors(window,target,5,[1,-1],12)
        self.assertTrue(r['verified']);self.assertGreater(r['score'],.99)
        self.assertEqual(r['offset'],[1,-1]);self.assertGreater(r['peak_margin'],.02)

    def test_disagreement_boundary_missing_and_weak_print_stay_unverified(self):
        window,target=self.fixture((3,0))
        self.assertFalse(verify_printed_anchors(window,target,5,[0,0],12)['verified'])
        window,target=self.fixture((5,0))
        self.assertFalse(verify_printed_anchors(window,target,5,[5,0],12)['verified'])
        self.assertFalse(verify_printed_anchors(window,np.full_like(target,255),5,[5,0],12)['verified'])
        window=np.random.default_rng(81).integers(0,256,window.shape,dtype=np.uint8)
        self.assertFalse(verify_printed_anchors(window,target,5,[0,0],12)['verified'])

    def test_repeated_anchor_peaks_are_rejected(self):
        pattern=np.random.default_rng(42).integers(0,256,(2,100),dtype=np.uint8)
        target=np.tile(pattern,(21,1))[:41]
        window=np.full((51,110),255,np.uint8);window[:,5:105]=np.tile(pattern,(26,1))[:51]
        r=verify_printed_anchors(window,target,5,[0,1],12)
        self.assertFalse(r['verified']);self.assertLess(r['peak_margin'],.02)
