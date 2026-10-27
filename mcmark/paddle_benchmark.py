"""Offline PaddleOCR comparison on existing private benchmark crops.

Requires a separately installed Paddle environment and an explicitly downloaded
local model directory. Never selected by the application's OCR auto backend.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

from .ocr_benchmark import summarize


def local_crop(root, relative):
    path=(root/relative).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise ValueError('Crop must be an existing file inside the benchmark directory')
    return path


def run(baseline, model_dir, output):
    model_dir=model_dir.resolve()
    required=['inference.json','inference.pdiparams','inference.yml']
    if not all((model_dir/name).is_file() for name in required):
        raise ValueError('Provide the downloaded PP-OCRv5_mobile_rec model directory')
    # Explicit local model files avoid automatic model downloads during inference.
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
    from paddleocr import TextRecognition
    started=time.perf_counter()
    model=TextRecognition(model_name='PP-OCRv5_mobile_rec',model_dir=str(model_dir),device='cpu',cpu_threads=2,enable_mkldnn=False)
    source=json.loads(baseline.read_text());rows=[]
    try:
        for previous in source['readings']:
            if previous['variant'] not in ('legacy','native_field','native_contrast'):continue
            row={k:previous[k] for k in ('page','field','variant','crop','crop_size')}
            tick=time.perf_counter()
            try:
                path=local_crop(baseline.parent,previous['crop'])
                result=model.predict(input=str(path))[0].json['res']
                score=float(result['rec_score'])*100
                row.update(summarize({'text':[result['rec_text']],'conf':[score],'engine':'paddleocr'},previous['field']))
            except Exception as exc:row.update(status='error',error=str(exc))
            row['seconds']=round(time.perf_counter()-tick,3);rows.append(row)
    finally:model.close()
    try:
        import resource,platform
        peak=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024*1024 if platform.system()=='Darwin' else 1024),1)
    except ImportError:peak=None
    report={'source_sha256':source['source_sha256'],'layout_sha256':source['layout_sha256'],'engine':'paddleocr',
            'versions':{name:importlib.metadata.version(name) for name in ('paddleocr','paddlepaddle','paddlex')},
            'model':'PP-OCRv5_mobile_rec','model_sha256':{name:hashlib.sha256((model_dir/name).read_bytes()).hexdigest() for name in required},
            'readings':rows,'elapsed_seconds':round(time.perf_counter()-started,2),'parent_peak_rss_mb':peak,
            'accuracy':'not measured: confirmed written-field transcriptions required',
            'scope':'offline recognition only; confidence >=70 and format counts are diagnostics, not calibrated accuracy or deployment acceptance'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline',type=Path);p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=run(args.baseline,args.model_dir,args.output)
    print(json.dumps({'readings':len(r['readings']),'errors':sum(x['status']=='error' for x in r['readings']),'elapsed_seconds':r['elapsed_seconds'],'parent_peak_rss_mb':r['parent_peak_rss_mb']}))

if __name__=='__main__':main()
