"""Local OCR backends; no scans are uploaded."""
import atexit
import json
import platform
import shutil
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


def recognize(crop, engine='auto'):
    if engine == 'auto':
        engine = 'tesseract' if shutil.which('tesseract') else 'apple_vision' if platform.system() == 'Darwin' else 'tesseract'
    # White margins help segment large handwriting in shallow field crops.
    import cv2
    crop = cv2.copyMakeBorder(crop,24,24,24,24,cv2.BORDER_CONSTANT,value=255)
    if engine == 'tesseract':
        import pytesseract
        available = pytesseract.get_languages(config='')
        languages = 'eng+chi_tra' if 'chi_tra' in available else 'eng'
        data = pytesseract.image_to_data(crop,lang=languages,config='--psm 7',output_type=pytesseract.Output.DICT)
        return {**data,'engine':'tesseract'}
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
