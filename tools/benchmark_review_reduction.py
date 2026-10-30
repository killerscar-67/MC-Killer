"""Offline review-risk benchmark. Outputs can be private: never commit them.

Labels must be independently confirmed student selections, not the answer key.
The optional baseline is a trusted local Python source file, executed on import.
Perturbations reuse the same writers; they are not independent validation data.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mcmark import vision


def load_baseline(path):
    spec=importlib.util.spec_from_file_location('benchmark_baseline',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def perturb(gray,name):
    if name=='brightness20':return np.clip(gray.astype(np.int16)+20,0,255).astype(np.uint8)
    if name=='contrast80':return np.clip(gray*.8+35,0,255).astype(np.uint8)
    if name=='blur06':return cv2.GaussianBlur(gray,(3,3),.6)
    if name=='jpeg70':return cv2.imdecode(cv2.imencode('.jpg',gray,[cv2.IMWRITE_JPEG_QUALITY,70])[1],0)
    if name=='shift1':return cv2.warpAffine(gray,np.float32([[1,0,1],[0,1,-1]]),(gray.shape[1],gray.shape[0]),borderValue=255)
    return gray


def record(stats,reading,expected):
    pending=bool(reading['review_reasons'])
    stats['total']+=1;stats['pending']+=pending
    stats['correct']+=reading['selected']==expected
    stats['unflagged_errors']+=reading['selected']!=expected and not pending


def empty_stats():
    return dict(total=0,pending=0,correct=0,unflagged_errors=0,seconds=0.0)


def evaluate(args,config,baseline):
    if not args.pdf or not args.labels:
        raise ValueError('--pdf and --labels are required together')
    labels=json.loads(args.labels.read_text())['labels'];truth={}
    for label in labels:
        key=(int(label['page']),str(label['question']))
        if key in truth:raise ValueError('Duplicate confirmed label')
        truth[key]=label['selected']
    cases=[];summaries={};variants=['original']
    if args.perturbations:variants+=['brightness20','contrast80','blur06','jpeg70','shift1']
    for name in variants:
        summaries[name]={'candidate':empty_stats(),'baseline':empty_stats(),'newly_unflagged_errors':0}
    used=set();alignment_seconds=0.0
    for page,raw in vision.pages(args.pdf):
        start=time.perf_counter();cv2.setRNGSeed(0)
        gray=vision.align(raw,config);alignment_seconds+=time.perf_counter()-start
        for name in variants:
            image=perturb(gray,name)
            for grid in config['questions'][:args.questions]:
                key=(page,str(grid['id']))
                if key not in truth:raise ValueError('Missing confirmed label; blanks are never inferred')
                used.add(key);expected=truth[key];pair={}
                for tag,module in (('baseline',baseline),('candidate',vision)):
                    start=time.perf_counter();reading=module.detect(image,grid,config)
                    summaries[name][tag]['seconds']+=time.perf_counter()-start
                    record(summaries[name][tag],reading,expected);pair[tag]=reading
                a,b=pair['baseline'],pair['candidate']
                newly_wrong=(b['selected']!=expected and not b['review_reasons']
                             and (a['review_reasons'] or a['selected']==expected))
                summaries[name]['newly_unflagged_errors']+=bool(newly_wrong)
                if name=='original' or newly_wrong:
                    cases.append(dict(page=page,question=grid['id'],variant=name,
                        expected=expected,selected=b['selected'],reasons=b['review_reasons'],
                        baseline_reasons=a['review_reasons'],auto_accept_reason=b.get('auto_accept_reason'),
                        choice_stability=b.get('choice_stability'),alignment_score=b.get('alignment_score'),
                        printed_alignment=b.get('printed_alignment'),newly_unflagged_error=bool(newly_wrong)))
    unused=sorted(set(truth)-used)
    if unused:raise ValueError('Labels include unprocessed pages/questions; choose the correct question count')
    for result in summaries.values():
        for tag in ('candidate','baseline'):
            stats=result[tag];accepted=stats['total']-stats['pending']
            stats['review_rate']=stats['pending']/stats['total']
            stats['accepted']=accepted
            # Descriptive only: reused/tuned data do not support an independent guarantee.
            stats['zero_error_iid_upper95']=(1-.05**(1/accepted)
                if accepted and stats['unflagged_errors']==0 else None)
    return dict(variants=summaries,alignment_seconds=alignment_seconds,cases=cases)


def cancellation_matrix(config,baseline):
    template=vision.load_template(config['template_image']);grid=config['questions'][0]
    stats=dict(total=0,baseline_accepted=0,candidate_accepted=0,newly_accepted=0,by_kind={})
    cases=[]
    for kind,angle,color,thickness,radius in itertools.product(
        ('cross','cross_fill','cross_loop','other_plus_cross'),(25,30,45,60,65),(0,100,170),(1,2),(9,11,14)):
        image=template.copy();x,y=map(round,grid['centers'][1])
        if kind=='cross_fill':cv2.rectangle(image,(x-8,y-3),(x+8,y+3),30,-1)
        if kind=='cross_loop':cv2.ellipse(image,(x,y),(7,4),0,0,360,30,1)
        if kind=='other_plus_cross':
            ax,ay=map(round,grid['centers'][0]);cv2.rectangle(image,(ax-8,ay-3),(ax+8,ay+3),30,-1)
        overlay=np.full_like(image,255)
        for theta in (angle,180-angle):
            dx=round(radius*math.cos(math.radians(theta)));dy=round(radius*math.sin(math.radians(theta)))
            cv2.line(overlay,(x-dx,y-dy),(x+dx,y+dy),color,thickness)
        # Faint pen cannot lighten an existing dark fill.
        image=np.minimum(image,overlay)
        a=baseline.detect(image,grid,config);b=vision.detect(image,grid,config)
        group=stats['by_kind'].setdefault(kind,dict(total=0,baseline_accepted=0,candidate_accepted=0))
        for counts in (stats,group):
            counts['total']+=1;counts['baseline_accepted']+=not bool(a['review_reasons'])
            counts['candidate_accepted']+=not bool(b['review_reasons'])
        stats['newly_accepted']+=not bool(b['review_reasons']) and bool(a['review_reasons'])
        if not b['review_reasons']:
            cases.append(dict(kind=kind,angle=angle,color=color,thickness=thickness,radius=radius))
    stats['remaining_accepted_cases']=cases
    return stats


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path);parser.add_argument('--labels',type=Path)
    parser.add_argument('--layout',type=Path,default=ROOT/'mcmark/layouts/delia-layout.json')
    parser.add_argument('--questions',type=int,default=20,choices=range(1,101))
    parser.add_argument('--baseline-vision',type=Path,required=True,help='Trusted local baseline Python source')
    parser.add_argument('--perturbations',action='store_true');parser.add_argument('--synthetic',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();config=json.loads(args.layout.read_text())
    config['template_image']=str((args.layout.resolve().parent/config['template_image']).resolve())
    baseline=load_baseline(args.baseline_vision)
    report=dict(candidate_sha256=hashlib.sha256(Path(vision.__file__).read_bytes()).hexdigest(),
                baseline_sha256=hashlib.sha256(args.baseline_vision.read_bytes()).hexdigest(),
                caution='Development replay and synthetic stress are not independent writer/scanner validation.')
    if args.pdf or args.labels:report['labelled']=evaluate(args,config,baseline)
    if args.synthetic:report['synthetic']=cancellation_matrix(config,baseline)
    if not (args.pdf or args.synthetic):parser.error('Provide a labelled PDF or --synthetic')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    compact={k:v for k,v in report.items() if k!='labelled'}
    if 'labelled' in report:compact['labelled']=report['labelled']['variants']
    print(json.dumps(compact,indent=2))


if __name__=='__main__':main()
