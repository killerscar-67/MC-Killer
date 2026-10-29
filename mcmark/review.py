"""Image evidence, a teacher review queue, and auditable answer corrections."""
import csv
import html
from pathlib import Path
from urllib.parse import quote
from .core import grade


def save_question_crop(gray, question, destination):
    import cv2
    xs,ys = zip(*question['centers'])
    margin = max(22, int(question.get('radius', 10)*2))
    left,top = max(0,int(min(xs))-margin),max(0,int(min(ys))-margin)
    right,bottom = min(gray.shape[1],int(max(xs))+margin+1),min(gray.shape[0],int(max(ys))+margin+1)
    destination = Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not cv2.imwrite(str(destination),gray[top:bottom,left:right]):
        raise OSError(f'Could not save question crop: {destination}')
    return str(destination.resolve())


def refresh_review(row):
    row['score_is_provisional'] = any(a.get('review_reasons') and not a.get('teacher_review') for a in row['responses'])
    row['review_required'] = bool(row.get('sheet_review_issues')) or row['score_is_provisional']


def apply_corrections(results, config, path):
    """Validate every decision before mutating any result. Blank decisions stay pending."""
    records = {(r['file'],str(r['page'])):r for r in results}
    questions = {str(q['id']):q for q in config['questions']}
    pending=[]
    seen=set()
    with Path(path).open(newline='',encoding='utf-8-sig') as stream:
        reader=csv.DictReader(stream)
        if not {'file','page','question','decision'}.issubset(reader.fieldnames or []):
            raise ValueError('Corrections CSV needs file,page,question,decision columns')
        for line in reader:
            decision=(line.get('decision') or '').strip()
            if not decision:
                continue
            source=line['file']
            # Undo spreadsheet-safe CSV prefix, only where the exporter adds it.
            if source.startswith("'") and source[1:].lstrip().startswith(('=','+','-','@')):
                source=source[1:]
            row=records.get((source,line['page']))
            qid=line['question']
            if row is None or qid not in questions:
                raise ValueError(f'Correction source/page/question not in this batch: {source}, {line["page"]}, {qid}')
            identity=(source,line['page'],qid)
            if identity in seen:
                raise ValueError(f'Duplicate correction for {identity}')
            seen.add(identity)
            chosen=[] if decision.upper()=='BLANK' else [label.strip().upper() for label in decision.split('|')]
            if len(set(chosen))!=len(chosen) or any(label not in questions[qid]['labels'] for label in chosen):
                raise ValueError(f'Invalid decision for question {qid}: {decision}')
            response=next(a for a in row['responses'] if a['question']==qid)
            pending.append((row,response,chosen,line.get('note','')))
    for row,response,chosen,note in pending:
        response.setdefault('raw_selected',list(response['selected']))
        response['teacher_review']={'previous_selected':list(response['selected']), 'decision':chosen, 'note':note}
        response['selected']=chosen
    for row in results:
        row.update(grade(row['responses'],config))
        refresh_review(row)


def write_review(results, output):
    output=Path(output)
    fields=['file','page','name','class','student_id','question','raw_selected','current_selected','suggested_selected','reasons','image','status','decision','note']
    rows=[]
    sections=[]
    for result in results:
        e=html.escape
        answers=' '.join(f"{a['question']}:{'|'.join(a['selected']) or 'BLANK'}" for a in result['responses'])
        sections.append(f'<article><h2>{e(Path(result["file"]).name)} · page {result["page"]}</h2>'
                        f'<p>Score: {result["score"]:g}/{result["maximum"]:g} ({result["percent"]:.1f}%) · '
                        f'{"PROVISIONAL ANSWERS" if result.get("score_is_provisional") else "No pending answer flags"}</p>'
                        f'<p>Registered responses: {e(answers)}</p>'
                        f'<p>Sheet issues: {e(", ".join(result.get("sheet_review_issues",[]))) or "none"}</p></article>')
        for field,detail in result.get('metadata_details',{}).items():
            crop=detail.get('crop')
            if not crop:
                continue
            relative=Path(crop).relative_to(output.resolve()).as_posix()
            sections.append(f'<article><h2>{e(field)} · {e(Path(result["file"]).name)}</h2>'
                            f'<p>OCR: {e(detail.get("text", "")) or "(unrecognized)"} · {e(detail.get("status", ""))} · '
                            f'confidence: {detail.get("confidence")}</p><img src="{quote(relative)}" alt="Original written field"/></article>')
        for a in result['responses']:
            if not a.get('review_reasons') and not a.get('teacher_review'):
                continue
            teacher=a.get('teacher_review')
            crop=a.get('review_crop','')
            rows.append({
                'file':result['file'],'page':result['page'],'name':result.get('name',''),'class':result.get('class',''),'student_id':result.get('student_id',''),
                'question':a['question'],'raw_selected':'|'.join(a.get('raw_selected',a['selected'])),
                'current_selected':'|'.join(a['selected']),'suggested_selected':'|'.join(a.get('suggested_selected') or []),
                'reasons':'|'.join(a.get('review_reasons',[])), 'image':crop,
                'status':'reviewed' if teacher else 'pending',
                'decision':('|'.join(teacher['decision']) or 'BLANK') if teacher else '', 'note':teacher.get('note','') if teacher else ''})
            relative=Path(crop).relative_to(output.resolve()).as_posix() if crop else ''
            e=html.escape
            sections.append(f'<article><h2>{e(Path(result["file"]).name)} · page {result["page"]} · Q{e(a["question"])}</h2>'
                            f'<p>{e(result.get("name", ""))} · class {e(result.get("class", ""))} · no. {e(result.get("student_id", ""))}</p>'
                            f'<p>Detected: {e("|".join(a.get("raw_selected",a["selected"])) or "BLANK")} · current: {e("|".join(a["selected"]) or "BLANK")} · {"reviewed" if teacher else "pending"}</p>'
                            f'<p>{e(", ".join(a.get("review_reasons",[])))}</p>'
                            f'<img src="{quote(relative)}" alt="Original registered question row"/></article>')
    with (output/'review_queue.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        writer.writerows({k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in row.items()} for row in rows)
    (output/'review.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>MCQ teacher review</title>'
        '<style>body{font:16px system-ui;max-width:1000px;margin:32px auto;padding:0 20px;background:#f4f6f8;color:#17212b}article{background:white;padding:20px;margin:20px 0;border:1px solid #bbc5d0;border-radius:12px}img{width:100%;max-width:900px;image-rendering:auto}h2{font-size:20px}</style>'
        '<h1>MCQ teacher review</h1><p>These images show unannotated registered question rows. Cross-out clues are suggestions only; the system does not discard a marked option automatically.</p>'
        '<p>Edit the decision column in review_queue.csv: A, B, C, D, A|C, or BLANK. An empty decision stays pending. Keep file, page and question unchanged. Re-run the same batch with --corrections pointing to the edited CSV and a new output folder. Scores and statistics are recalculated; original readings are retained.</p>'
        +(''.join(sections) or '<p>No question reviews are pending. Check students.csv for metadata or identity review flags.</p>')+'</html>',encoding='utf-8')


def visual_review_eligible(answer):
    """A single current choice can be explicitly confirmed after seeing its image.

    This does not grant automatic eligibility or suppress cancellation warnings.
    Failed alignment must be corrected before a compact confirmation is offered.
    """
    return (len(answer.get('selected',[]))==1 and bool(answer.get('review_reasons'))
            and not answer.get('teacher_review')
            and 'uncertain_local_alignment' not in answer.get('review_reasons',[]))


def batch_review_eligible(answer):
    """Permit explicit visual batch confirmation only for isolated single choices."""
    blockers={'multiple','blank','possible_cross_out','possible_cancellation_stroke',
              'uncertain_local_alignment','ambiguous_thin_marks'}
    return (len(answer.get('selected',[]))==1 and bool(answer.get('review_reasons'))
            and not answer.get('teacher_review')
            and not blockers.intersection(answer.get('review_reasons',[]))
            and not any(c.get('cross_suspected') or c.get('diagonal_clue')
                        for c in answer.get('mark_clues',{}).values()))
