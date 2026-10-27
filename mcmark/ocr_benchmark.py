"""Offline OCR comparison; output contains private text/images, never uploads data."""
import argparse
import hashlib
import json
import math
import platform
import re
import time
from pathlib import Path

import cv2
import numpy as np

from .ocr import recognize
from .vision import align, pages


def crop_original(gray, transform, box, page_size, max_scale=3):
    """Warp only a field from original pixels using the validated page transform."""
    x,y,w,h=map(float,box);pw,ph=page_size
    if not all(math.isfinite(v) for v in (x,y,w,h,max_scale)) or min(w,h,max_scale)<=0 or min(x,y)<0 or x+w>pw or y+h>ph:
        raise ValueError('Invalid field crop bounds or scale')
    matrix=np.asarray(transform,dtype=np.float64)
    if matrix.shape!=(3,3) or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix))<1e-12:
        raise ValueError('Invalid registration transform')
    scale=min(max_scale,gray.shape[1]/pw,gray.shape[0]/ph)
    width,height=max(1,round(w*scale)),max(1,round(h*scale))
    if width*height>5_000_000: raise ValueError('Field crop exceeds pixel limit')
    output=np.array([[scale,0,-x*scale],[0,scale,-y*scale],[0,0,1]],dtype=np.float64)
    return cv2.warpPerspective(gray,output @ matrix,(width,height),borderValue=255)


def summarize(reading,field,minimum=70):
    words=[(str(t),float(c)) for t,c in zip(reading['text'],reading['conf']) if str(t).strip()]
    raw=' '.join(t for t,_ in words).strip()
    value=re.sub(r'\s+','',raw).upper() if field in ('class','student_id') else raw
    confidence=min((c for _,c in words),default=None)
    pattern={'class':r'[0-9]+[A-Z]','student_id':r'[0-9]+'}.get(field,r'.+')
    status='recognized' if value and confidence is not None and confidence>=minimum and re.fullmatch(pattern,value) else 'unrecognized'
    return {'raw_text':raw,'normalized_text':value,'confidence':confidence,'status':status,
            **{k:reading[k] for k in ('engine','engine_version','profile','psm','languages') if k in reading}}


def source_pages(path,dpi=300):
    if path.suffix.lower()!='.pdf':
        yield from pages(path);return
    import fitz
    with fitz.open(path) as doc:
        for number,page in enumerate(doc,1):
            pix=page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),alpha=False,colorspace=fitz.csRGB)
            yield number,cv2.cvtColor(np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3),cv2.COLOR_RGB2GRAY)


def run(source,layout,output,engine='tesseract',tessdata=None,max_pages=200):
    config=json.loads(layout.read_text())
    if config.get('template_image'):
        config['template_image']=str((layout.resolve().parent/config['template_image']).resolve())
    output.mkdir(parents=True,exist_ok=True);(output/'crops').mkdir(exist_ok=True)
    rows=[];errors=[];total=time.perf_counter();label_template={}
    legacy_iterator=iter(pages(source))
    for page,raw in source_pages(source):
        if page>max_pages:break
        try:
            # Legacy baseline uses the same 2x PDF render as the app, before registration.
            # Original grayscale is used only for the high-resolution candidate crops.
            legacy_page,legacy_raw=next(legacy_iterator)
            if legacy_page!=page:raise ValueError('Page order mismatch')
            legacy=align(legacy_raw,config)
            _,matrix=align(raw,config,return_transform=True)
        except Exception as exc:
            errors.append({'page':page,'stage':'registration','error':str(exc)});continue
        label_template[str(page)]={}
        for field,zone in config['metadata'].items():
            if zone['mode']!='ocr':continue
            x,y,w,h=zone['box'];low=legacy[y:y+h,x:x+w]
            high=crop_original(raw,matrix,zone['box'],config['page_size'])
            contrast=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(high)
            label_template[str(page)][field]=None
            for variant,crop,profile in [('legacy',low,'legacy'),('low_field',low,'field_v1'),('native_legacy',high,'legacy'),('native_field',high,'field_v1'),('native_contrast',contrast,'field_v1')]:
                path=output/'crops'/f'p{page:03d}-{field}-{variant}.png';cv2.imwrite(str(path),crop)
                start=time.perf_counter();row={'page':page,'field':field,'variant':variant,'crop':str(path.relative_to(output)), 'crop_size':[crop.shape[1],crop.shape[0]]}
                try:row.update(summarize(recognize(crop,engine,field=field,profile=profile,tessdata=tessdata),field,zone.get('min_confidence',70)))
                except Exception as exc:row.update(status='error',error=str(exc))
                row['seconds']=round(time.perf_counter()-start,3);rows.append(row)
        print('Processed OCR page '+str(page),flush=True)
    language_models={}
    if tessdata:
        for model in ('eng','chi_tra'):
            path=Path(tessdata)/(model+'.traineddata')
            if path.is_file():language_models[model]=hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        import resource
        peak=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024*1024 if platform.system()=='Darwin' else 1024),1)
    except ImportError:peak=None
    report={'layout_sha256':hashlib.sha256(layout.read_bytes()).hexdigest(),'language_model_sha256':language_models,'parent_peak_rss_mb':peak,'source_file':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'engine':engine,'variants':['legacy','low_field','native_legacy','native_field','native_contrast'],'readings':rows,'errors':errors,
            'elapsed_seconds':round(time.perf_counter()-total,2),'accuracy':'not measured: confirmed written-field transcriptions required',
            'baseline_note':'same pages() 2x RGB-to-grayscale render and align() path as the app',
            'scope':'offline recognizer/crop benchmark; no production change, roster assignment or hosted capacity claim'}
    (output/'ocr-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    # Never overwrite annotations when rerunning a benchmark.
    path=output/'expected-fields.template.json'
    if not path.exists():path.write_text(json.dumps(label_template,ensure_ascii=False,indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--layout',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--engine',choices=['tesseract','tesserocr','apple_vision'],default='tesseract');p.add_argument('--tessdata',type=Path);p.add_argument('--max-pages',type=int,default=200,choices=range(1,201))
    a=p.parse_args();report=run(a.source,a.layout,a.output,a.engine,str(a.tessdata) if a.tessdata else None,a.max_pages)
    print(json.dumps({'readings':len(report['readings']),'registration_errors':len(report['errors']),'elapsed_seconds':report['elapsed_seconds']}))

if __name__=='__main__':main()
