"""Local OCR backends; no scans are uploaded."""
import atexit
import json
import platform
import shutil
import shlex
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def apple_helper():
    compiler = shutil.which('swiftc')
    if not compiler:
        raise RuntimeError('macOS OCR requires Swift command line tools, or install Tesseract')
    directory = Path(tempfile.mkdtemp(prefix='mcmark-vision-'))
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    binary = directory/'ocr'
    subprocess.run([compiler, '-module-cache-path', str(directory/'modules'), str(Path(__file__).with_name('apple_ocr.swift')), '-o', str(binary)],check=True,capture_output=True,timeout=60)
    return binary


def field_settings(field=None, profile='legacy'):
    if profile not in ('legacy','field_v1'):
        raise ValueError('Unknown OCR profile')
    if profile=='field_v1' and field in ('class','student_id'):
        return {'psm':8,'language':'eng','whitelist':'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ' if field=='class' else '0123456789'}
    return {'psm':7,'language':'multilingual','whitelist':None}


def recognize(crop, engine='auto', *, field=None, profile='legacy', tessdata=None):
    settings=field_settings(field,profile)
    if engine == 'auto':
        engine = 'tesseract' if shutil.which('tesseract') else 'apple_vision' if platform.system() == 'Darwin' else 'tesseract'
    if engine=='tesserocr':
        # Optional isolated benchmark backend. Never selected automatically.
        import csv
        import io
        import tesserocr
        from PIL import Image
        import cv2
        available=tesserocr.get_languages(tessdata)[1] if tessdata else tesserocr.get_languages()[1]
        languages='eng+chi_tra' if settings['language']=='multilingual' and 'chi_tra' in available else 'eng'
        kwargs={'lang':languages,'psm':settings['psm']}
        if tessdata: kwargs['path']=str(tessdata)
        with tesserocr.PyTessBaseAPI(**kwargs) as api:
            if settings['whitelist']: api.SetVariable('tessedit_char_whitelist',settings['whitelist'])
            padded=cv2.copyMakeBorder(crop,24,24,24,24,cv2.BORDER_CONSTANT,value=255)
            api.SetImage(Image.fromarray(padded))
            rows=list(csv.DictReader(io.StringIO(api.GetTSVText(0)),delimiter='\t',fieldnames=['level','page_num','block_num','par_num','line_num','word_num','left','top','width','height','conf','text']))
        return {'text':[row['text'] for row in rows], 'conf':[row['conf'] for row in rows],
                'engine':'tesserocr','engine_version':tesserocr.tesseract_version().splitlines()[0],
                'profile':profile,'psm':settings['psm'],'languages':languages}
    # White margins help segment large handwriting in shallow field crops.
    import cv2
    crop = cv2.copyMakeBorder(crop,24,24,24,24,cv2.BORDER_CONSTANT,value=255)
    if engine == 'tesseract':
        import pytesseract
        model_options='--tessdata-dir '+shlex.quote(str(tessdata)) if tessdata else ''
        available = pytesseract.get_languages(config=model_options)
        languages = 'eng+chi_tra' if settings['language']=='multilingual' and 'chi_tra' in available else 'eng'
        options=(model_options+' --psm '+str(settings['psm'])).strip()
        if settings['whitelist']: options+=' -c tessedit_char_whitelist='+settings['whitelist']
        data = pytesseract.image_to_data(crop,lang=languages,config=options,output_type=pytesseract.Output.DICT,timeout=30)
        return {**data,'engine':'tesseract','profile':profile,'psm':settings['psm'],'languages':languages}
    if engine == 'apple_vision':
        if platform.system() != 'Darwin':
            raise RuntimeError('Apple Vision OCR is available only on macOS')
        import cv2
        with tempfile.TemporaryDirectory(prefix='mcmark-ocr-image-') as tmp:
            image=Path(tmp)/'field.png'
            if not cv2.imwrite(str(image),crop):
                raise OSError('Could not prepare OCR image')
            result=subprocess.run([str(apple_helper()),str(image)],check=True,capture_output=True,text=True,timeout=30)
            return json.loads(result.stdout)
    raise ValueError(f'Unknown OCR engine: {engine}')
