"""Generate a standard layout and deterministic validation sheets."""
import json
from pathlib import Path
import cv2
import numpy as np

root = Path(__file__).parent
config = {'page_size':[1000,1400], 'radius':14,'density_threshold':.35,
          'fiducials':[[40,40],[960,40],[960,1360],[40,1360]],
          'metadata':{},'questions':[], 'scoring':{'correct':1,'wrong':-.25,'blank':0,'multiple':0},'pass_percent':50}
for name, labels, xs in [('class',list('ABC'),[180]),('student_id',list('0123456789'),[380,460])]:
    config['metadata'][name] = {'mode':'bubble','columns':[{'labels':labels,'centers':[[x,150+i*35] for i in range(len(labels))]} for x in xs]}
for i in range(10):
    config['questions'].append({'id':str(i+1),'labels':list('ABCD'),'centers':[[300+j*100,650+i*55] for j in range(4)],'answer':'ABCD'[i%4],'weight':2 if i==9 else 1})
(root/'layout.json').write_text(json.dumps(config,indent=2))
base = np.full((1400,1000),255,np.uint8)
for x,y in config['fiducials']:
    cv2.rectangle(base,(x-12,y-12),(x+12,y+12),0,-1)
cv2.putText(base,'MCQ ANSWER SHEET',(240,80),cv2.FONT_HERSHEY_SIMPLEX,1,0,2)
for name,zone in config['metadata'].items():
    for col in zone['columns']:
        x,y = col['centers'][0]
        cv2.putText(base,name,(x-35,y-35),cv2.FONT_HERSHEY_SIMPLEX,.45,0,1)
        for label,(x,y) in zip(col['labels'],col['centers']):
            cv2.circle(base,(x,y),14,0,2)
            cv2.putText(base,label,(x+20,y+5),cv2.FONT_HERSHEY_SIMPLEX,.5,0,1)
for q in config['questions']:
    cv2.putText(base,q['id'],(200,q['centers'][0][1]+5),cv2.FONT_HERSHEY_SIMPLEX,.6,0,1)
    for label,(x,y) in zip(q['labels'],q['centers']):
        cv2.circle(base,(x,y),14,0,2)
        cv2.putText(base,label,(x-5,y-22),cv2.FONT_HERSHEY_SIMPLEX,.5,0,1)
cv2.imwrite(str(root/'blank-sheet.png'),base)
(root/'sample-input').mkdir(exist_ok=True)
for number in (1,2):
    sheet=base.copy()
    for name,value in [('class','A'),('student_id',f'{number:02d}')]:
        for col,char in zip(config['metadata'][name]['columns'],value):
            cv2.circle(sheet,tuple(col['centers'][col['labels'].index(char)]),12,0,-1)
    for i,q in enumerate(config['questions']):
        selected = [q['answer']] if number==1 else [] if i==0 else ['A','B'] if i==1 else ['D']
        for char in selected:
            cv2.circle(sheet,tuple(q['centers'][q['labels'].index(char)]),12,0,-1)
    cv2.imwrite(str(root/'sample-input'/f'student-{number}.png'),sheet)
