"""Experimental comparison only: red student marks can also be removed.
Run in an isolated local environment. Fewer flags do not prove better accuracy.
Original PDF is never overwritten; output may contain private response data.
"""
import sys,json,time,argparse
from pathlib import Path
import fitz,cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcmark.vision import align,detect
parser=argparse.ArgumentParser(description='Offline experimental red-annotation comparison. Never applies decisions or uploads data.')
parser.add_argument('pdf',type=Path);parser.add_argument('--layout',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--count',type=int,default=20,choices=range(1,101))
args=parser.parse_args()
out=args.output;out.mkdir(parents=True,exist_ok=True)
c=json.loads(args.layout.read_text());c['template_image']=str((args.layout.resolve().parent/c['template_image']).resolve());c['questions']=c['questions'][:args.count]
summary=[]
with fitz.open(args.pdf) as doc:
 for i,page in enumerate(doc):
  pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False,colorspace=fitz.csRGB);rgb=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3).copy()
  r,g,b=[rgb[:,:,k].astype(np.int16) for k in range(3)];mask=(r>140)&(r-g>40)&(r-b>40);filtered=rgb.copy();filtered[mask]=255
  gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);clean=cv2.cvtColor(filtered,cv2.COLOR_RGB2GRAY)
  results=[]
  for image in (gray,clean):
   registered=align(image,c);results.append([detect(registered,q,c) for q in c['questions']])
  a,z=results
  record={'page':i+1,'red_pixels_removed':int(mask.sum()),'original_pending':sum(bool(x['review_reasons']) for x in a),'filtered_pending':sum(bool(x['review_reasons']) for x in z),'selection_changes':[{'q':str(k+1),'before':x['selected'],'after':y['selected']} for k,(x,y) in enumerate(zip(a,z)) if x['selected']!=y['selected']],'suggestion_changes':[{'q':str(k+1),'before':x['suggested_selected'],'after':y['suggested_selected']} for k,(x,y) in enumerate(zip(a,z)) if x['suggested_selected']!=y['suggested_selected']]}
  summary.append(record)
print(json.dumps(summary))
(out/'comparison.json').write_text(json.dumps(summary,indent=2))
