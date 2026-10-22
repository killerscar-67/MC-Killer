import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class PipelineTests(unittest.TestCase):
    def test_synthetic_batch(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest('Install project dependencies for image tests')
        from mcmark.cli import run
        root=Path(__file__).resolve().parents[1]
        subprocess.run([sys.executable,str(root/'examples/generate.py')],check=True)
        config=json.loads((root/'examples/layout.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            code=run([root/'examples/sample-input'],config,tmp)
            self.assertEqual(code,0)
            results=json.loads((Path(tmp)/'results.json').read_text())
            self.assertEqual([r['student_id'] for r in results],['01','02'])
            self.assertEqual(results[0]['class'],'A')
            self.assertEqual(results[0]['percent'],100)
            self.assertEqual(results[1]['responses'][0]['status'],'blank')
            self.assertEqual(results[1]['responses'][1]['status'],'multiple')
            # Modest perspective displacement is corrected by registration markers.
            source=cv2.imread(str(root/'examples/sample-input/student-1.png'),0)
            matrix=cv2.getPerspectiveTransform(np.float32([[0,0],[999,0],[999,1399],[0,1399]]),np.float32([[20,15],[975,25],[990,1370],[10,1385]]))
            warped=cv2.warpPerspective(source,matrix,(1000,1400),borderValue=255)
            from mcmark.vision import align,detect
            registered=align(warped,config)
            self.assertEqual([detect(registered,q,config)['selected'] for q in config['questions']],[[q['answer']] for q in config['questions']])
