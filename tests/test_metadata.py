import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class WrittenMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import cv2
        root = Path(__file__).resolve().parents[1]
        cls.config = json.loads((root/'mcmark/layouts/delia-layout.json').read_text())
        cls.config['template_image'] = str(root/'mcmark/layouts/delia-template.png')
        cls.gray = cv2.imread(cls.config['template_image'], 0)

    def test_all_five_values_and_evidence_survive_export(self):
        from mcmark.vision import metadata
        from mcmark.core import export, grade
        readings = ['CHAN Tai Man', 'CTM', '6Z', '99', 'Maths Paper 2']
        def response(value):
            return {'text': value.split(), 'conf': ['92']*len(value.split())}
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch('mcmark.ocr.recognize', side_effect=[response(v) for v in readings]) as ocr:
                profile = metadata(self.gray, self.config, lambda *a, **k: events.append((a,k)), Path(tmp)/'crops', '00001')
            self.assertEqual(ocr.call_count, 5)
            for field, value in zip(self.config['metadata'], readings):
                self.assertEqual(profile[field], value)
                detail = profile['metadata_details'][field]
                self.assertEqual(detail['confidence'], 92)
                self.assertEqual(detail['status'], 'recognized')
                self.assertTrue(Path(detail['crop']).is_file())
            # Wrong-but-readable class and number remain raw evidence; no guessed correction.
            self.assertEqual((profile['class'], profile['student_id']), ('6Z','99'))
            config = {**self.config, 'questions':[{**self.config['questions'][0], 'answer':'A'}]}
            row = dict(file='student.png',page=1,review_required=False,**profile,**grade([{'selected':['A']}],config))
            export([row],config,tmp,[])
            with (Path(tmp)/'students.csv').open(encoding='utf-8-sig') as stream:
                record = next(csv.DictReader(stream))
            for field, value in zip(self.config['metadata'], readings):
                self.assertEqual(record[field],value)
                self.assertTrue(Path(record[f'{field}_crop']).is_file())
            saved = json.loads((Path(tmp)/'results.json').read_text())[0]
            self.assertEqual(saved['metadata_details']['signature']['text'],'CTM')
            self.assertFalse(events)

    def test_low_confidence_signature_and_ocr_failure_keep_crops(self):
        from mcmark.vision import metadata
        config = {**self.config, 'metadata':{name:self.config['metadata'][name] for name in ('signature','name')}}
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            with patch('mcmark.ocr.recognize',side_effect=[{'text':['scribble'],'conf':['12']}, RuntimeError('OCR unavailable')]):
                profile=metadata(self.gray,config,lambda kind,**kw:events.append(kind),tmp)
            self.assertEqual(profile['signature'],'scribble')
            self.assertEqual(profile['metadata_details']['signature']['status'],'unrecognized')
            self.assertEqual(profile['metadata_details']['name']['status'],'error')
            self.assertEqual(profile['name'],'')
            self.assertEqual(events,['metadata_unrecognized','metadata_ocr_error'])
            for detail in profile['metadata_details'].values():
                self.assertTrue(Path(detail['crop']).is_file())
