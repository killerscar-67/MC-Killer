"""Previously accepted shallow crossings must abstain, never guess intent."""
import itertools
import json
import math
import unittest
from pathlib import Path

import cv2
import numpy as np
from mcmark.vision import detect


class CancellationRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.config=json.loads((root/'mcmark/layouts/delia-layout.json').read_text())
        cls.config['template_image']=str(root/'mcmark/layouts/delia-template.png')
        cls.grid=cls.config['questions'][0]
        cls.blank=cv2.imread(cls.config['template_image'],0)

    def crossed(self,kind,angle,color,thickness,radius,grid=None,label='B'):
        grid=grid or self.grid
        image=self.blank.copy();x,y=map(round,grid['centers'][grid['labels'].index(label)])
        if kind=='fill':cv2.rectangle(image,(x-8,y-3),(x+8,y+3),30,-1)
        else:cv2.ellipse(image,(x,y),(7,4),0,0,360,30,1)
        overlay=np.full_like(image,255)
        for theta in (angle,180-angle):
            dx=round(radius*math.cos(math.radians(theta)))
            dy=round(radius*math.sin(math.radians(theta)))
            cv2.line(overlay,(x-dx,y-dy),(x+dx,y+dy),color,thickness)
        return np.minimum(image,overlay)

    def require_review(self,image):
        reading=detect(image,self.grid,self.config)
        self.assertTrue(reading['review_reasons'])
        self.assertFalse(reading.get('auto_accept_reason'))
        self.assertIn('B',reading['selected'])
        return reading

    def test_twelve_short_shallow_crosses_over_fill(self):
        for angle,color,thickness in itertools.product((25,30),(0,100,170),(1,2)):
            with self.subTest(angle=angle,color=color,thickness=thickness):
                self.require_review(self.crossed('fill',angle,color,thickness,9))

    def test_four_short_shallow_crosses_over_loop(self):
        for angle,color in itertools.product((25,30),(0,100)):
            with self.subTest(angle=angle,color=color):
                self.require_review(self.crossed('loop',angle,color,2,9))

    def test_long_faint_cross_over_loop(self):
        self.require_review(self.crossed('loop',25,170,1,14))

    def test_cancellation_veto_preserves_other_marked_answer(self):
        image=self.crossed('fill',25,170,1,9)
        x,y=map(round,self.grid['centers'][0])
        cv2.rectangle(image,(x-8,y-3),(x+8,y+3),30,-1)
        reading=self.require_review(image)
        self.assertIn('A',reading['selected'])
        self.assertEqual(reading['raw_selected'],['A','B'])

    def test_reported_patterns_across_fractional_centres_and_answer_positions(self):
        cases=[('fill',a,c,w,9) for a,c,w in itertools.product((25,30),(0,100,170),(1,2))]
        cases += [('loop',a,c,2,9) for a,c in itertools.product((25,30),(0,100))]
        cases.append(('loop',25,170,1,14))
        for index in (0,1,24,25,49,74,99):
            grid=self.config['questions'][index]
            for label in grid['labels']:
                for kind,angle,color,thickness,radius in cases:
                    with self.subTest(question=index+1,label=label,kind=kind,angle=angle,color=color,thickness=thickness):
                        image=self.crossed(kind,angle,color,thickness,radius,grid,label)
                        self.assertTrue(detect(image,grid,self.config)['review_reasons'])

    def test_ordinary_fills_at_same_layout_positions_do_not_trigger_shallow_veto(self):
        for index in (0,1,24,25,49,74,99):
            grid=self.config['questions'][index]
            for label,(x,y) in zip(grid['labels'],grid['centers']):
                with self.subTest(question=index+1,label=label):
                    x,y=round(x),round(y);image=self.blank.copy()
                    cv2.rectangle(image,(x-8,y-3),(x+8,y+3),30,-1)
                    reading=detect(image,grid,self.config)
                    self.assertEqual(reading['selected'],[label])
                    self.assertFalse(reading['review_reasons'])
