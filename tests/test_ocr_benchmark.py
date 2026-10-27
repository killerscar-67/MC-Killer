import json
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from mcmark.ocr import field_settings,recognize
from mcmark.ocr_benchmark import crop_original,summarize
from mcmark.vision import align


class OCRBenchmarkTests(unittest.TestCase):
    def test_existing_alignment_api_and_original_coordinate_transform(self):
        image=np.full((80,100),255,np.uint8);image[20:40,30:60]=0
        config={'page_size':[50,40]}
        legacy=align(image,config);registered,matrix=align(image,config,return_transform=True)
        np.testing.assert_array_equal(legacy,registered)
        np.testing.assert_allclose(matrix,np.diag([.5,.5,1]))
        crop=crop_original(image,matrix,[15,10,15,10],[50,40])
        self.assertEqual(crop.shape,(20,30));self.assertLess(crop.mean(),1)

    def test_native_crop_accounts_for_translation_and_rejects_bad_bounds(self):
        image=np.full((80,100),255,np.uint8);image[20:40,30:60]=0
        matrix=np.array([[.5,0,2],[0,.5,3],[0,0,1.]])
        crop=crop_original(image,matrix,[17,13,15,10],[50,40])
        self.assertLess(crop.mean(),1)
        for box in ([-1,0,10,10],[40,0,20,10],[0,0,0,10],[float('nan'),0,2,2]):
            with self.assertRaises(ValueError):crop_original(image,matrix,box,[50,40])
        with self.assertRaises(ValueError):crop_original(image,np.zeros((3,3)),[0,0,10,10],[50,40])

    def test_field_settings_leave_legacy_defaults_unchanged(self):
        self.assertEqual(field_settings('student_id')['psm'],7)
        self.assertIsNone(field_settings('class')['whitelist'])
        self.assertEqual(field_settings('student_id','field_v1')['whitelist'],'0123456789')
        self.assertIn('A',field_settings('class','field_v1')['whitelist'])
        self.assertEqual(field_settings('name','field_v1')['language'],'multilingual')
        with self.assertRaises(ValueError):field_settings('name','unknown')

    def test_raw_identity_survives_format_checks_and_low_confidence(self):
        result=summarize({'text':['5',' a'],'conf':['92','91']},'class')
        self.assertEqual(result['raw_text'],'5  a');self.assertEqual(result['normalized_text'],'5A')
        self.assertEqual(result['status'],'recognized')
        for value,conf in [('SA','99'),('5A','45'),('','99')]:
            result=summarize({'text':[value],'conf':[conf]},'class')
            self.assertEqual(result['status'],'unrecognized')
        result=summarize({'text':['O1'],'conf':['99']},'student_id')
        self.assertEqual(result['normalized_text'],'O1');self.assertEqual(result['status'],'unrecognized')

    def test_tesseract_field_config_and_timeout(self):
        with patch('pytesseract.get_languages',return_value=['eng','chi_tra']),patch('pytesseract.image_to_data',return_value={'text':['1'],'conf':['90']}) as call:
            result=recognize(np.full((20,50),255,np.uint8),'tesseract',field='student_id',profile='field_v1')
        self.assertEqual(call.call_args.kwargs['lang'],'eng')
        self.assertIn('tessedit_char_whitelist=0123456789',call.call_args.kwargs['config'])
        self.assertEqual(call.call_args.kwargs['timeout'],30)

    def test_native_tesseract_tsv_has_no_header(self):
        import sys,types
        from unittest.mock import MagicMock
        api=MagicMock();api.__enter__.return_value=api
        api.GetTSVText.return_value='5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t91.5\t5A\n'
        backend=types.SimpleNamespace(get_languages=lambda *a:('/tmp',['eng','chi_tra']),PyTessBaseAPI=MagicMock(return_value=api),tesseract_version=lambda:'tesseract test')
        with patch.dict(sys.modules,{'tesserocr':backend}):
            r=recognize(np.full((20,50),255,np.uint8),'tesserocr',field='class',profile='field_v1',tessdata='/tmp')
        self.assertEqual(r['text'],['5A']);self.assertEqual(r['conf'],['91.5'])
        self.assertEqual(r['psm'],8)

    def test_paddle_rejects_missing_model_and_crop_path_escape(self):
        import tempfile
        from mcmark.paddle_benchmark import local_crop,run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'inside.png').write_bytes(b'private crop')
            self.assertEqual(local_crop(root,'inside.png'),(root/'inside.png').resolve())
            with self.assertRaises(ValueError):local_crop(root,'../outside.png')
            with self.assertRaises(ValueError):run(root/'missing.json',root,root/'result.json')

    def test_paddle_offline_result_preserves_text_and_records_model_hashes(self):
        import tempfile,sys,types
        from mcmark.paddle_benchmark import run
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);model_dir=root/'model';model_dir.mkdir()
            for name in ('inference.json','inference.pdiparams','inference.yml'):(model_dir/name).write_bytes(b'model')
            (root/'crop.png').write_bytes(b'crop')
            baseline=root/'baseline.json'
            baseline.write_text(json.dumps({'source_sha256':'source','layout_sha256':'layout','readings':[{'page':1,'field':'class','variant':'native_field','crop':'crop.png','crop_size':[50,20]}]}))
            model=MagicMock();model.predict.return_value=[types.SimpleNamespace(json={'res':{'rec_text':'SA','rec_score':.99}})]
            backend=types.SimpleNamespace(TextRecognition=MagicMock(return_value=model))
            with patch.dict(sys.modules,{'paddleocr':backend}),patch('importlib.metadata.version',return_value='test'):
                result=run(baseline,model_dir,root/'out.json')
            row=result['readings'][0]
            self.assertEqual(row['raw_text'],'SA');self.assertEqual(row['status'],'unrecognized')
            self.assertEqual(len(result['model_sha256']),3);model.close.assert_called_once()
