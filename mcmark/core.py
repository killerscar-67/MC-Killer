import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def validate(config):
    width, height = config['page_size']
    if width <= 0 or height <= 0:
        raise ValueError('page_size must be positive')
    ids = [str(q['id']) for q in config['questions']]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('Questions require unique IDs')
    def check_grid(grid):
        if len(grid['centers']) != len(grid['labels']) or not grid['labels']:
            raise ValueError('Each grid needs one center per label')
        if len(set(grid['labels'])) != len(grid['labels']):
            raise ValueError('Grid labels must be unique')
        if grid.get('radius', config.get('radius', 10)) <= 0:
            raise ValueError('Bubble radius must be positive')
        if grid.get('sample_box') and (len(grid['sample_box']) != 2 or any(v <= 0 for v in grid['sample_box'])):
            raise ValueError('sample_box must contain positive width and height')
        for x, y in grid['centers']:
            if not (0 <= x < width and 0 <= y < height):
                raise ValueError('Bubble center outside page')
    for q in config['questions']:
        check_grid(q)
        if q['answer'] not in q['labels']:
            raise ValueError(f"Invalid answer for question {q['id']}")
        if not math.isfinite(float(q.get('weight', 1))) or q.get('weight', 1) <= 0:
            raise ValueError('Question weights must be positive and finite')
    for name, zone in config.get('metadata', {}).items():
        if zone['mode'] == 'bubble':
            for column in zone['columns']:
                check_grid(column)
        elif zone['mode'] == 'ocr':
            x, y, w, h = zone['box']
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > width or y+h > height:
                raise ValueError(f'Invalid OCR box: {name}')
            if zone.get('evidence_box'):
                ex,ey,ew,eh = zone['evidence_box']
                if ex < 0 or ey < 0 or ew <= 0 or eh <= 0 or ex+ew > width or ey+eh > height:
                    raise ValueError(f'Invalid evidence box: {name}')
        else:
            raise ValueError(f'Unknown metadata mode: {name}')
    threshold = config.get('density_threshold', .35)
    if not 0 < threshold < 1:
        raise ValueError('density_threshold must be between zero and one')
    scoring = config.get('scoring', {})
    if scoring.get('correct', 1) <= 0:
        raise ValueError('Correct mark must be positive')
    for key in ('correct', 'wrong', 'blank', 'multiple'):
        if not math.isfinite(float(scoring.get(key, 1 if key == 'correct' else 0))):
            raise ValueError('Marks must be finite')
    if not 0 <= config.get('pass_percent', 50) <= 100:
        raise ValueError('pass_percent must be between zero and 100')
    return config


def grade(responses, config):
    if len(responses) != len(config['questions']):
        raise ValueError('Response count does not match question count')
    scoring = {'correct': 1, 'wrong': 0, 'blank': 0, 'multiple': 0, **config.get('scoring', {})}
    score = maximum = 0
    details = []
    for q, response in zip(config['questions'], responses):
        selected = response['selected']
        status = 'blank' if not selected else 'multiple' if len(selected) > 1 else 'correct' if selected[0] == q['answer'] else 'wrong'
        marks = scoring[status] * q.get('weight', 1)
        maximum += scoring['correct'] * q.get('weight', 1)
        score += marks
        details.append({**response, 'question': str(q['id']), 'status': status, 'marks': marks})
    return {'score': score, 'maximum': maximum, 'percent': 100 * score / maximum,
            'passed': 100 * score / maximum >= config.get('pass_percent', 50), 'responses': details}


def describe(rows, group):
    scores = [r['score'] for r in rows]
    return dict(group=group, count=len(rows), mean=statistics.mean(scores), median=statistics.median(scores),
                minimum=min(scores), maximum=max(scores), standard_deviation=statistics.pstdev(scores),
                passed=sum(r['passed'] for r in rows), failed=sum(not r['passed'] for r in rows),
                pass_percent=100 * sum(r['passed'] for r in rows)/len(rows),
                provisional_count=sum(bool(r.get('score_is_provisional')) for r in rows),
                review_required_count=sum(bool(r.get('review_required')) for r in rows))


def export(results, config, output, events):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    def write(name, rows, fields):
        with (output/name).open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            # Prevent spreadsheet formula execution from OCR text and filenames.
            writer.writerows({k: ("'"+str(v) if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v) for k,v in row.items()} for row in rows)
    metadata_fields = list(dict.fromkeys(['name','signature','class','student_id','subject_paper', *config.get('metadata', {})]))
    fields = ['file','page', *metadata_fields, 'review_required','score_is_provisional','score','maximum','percent','passed']
    for name in config.get('metadata', {}):
        if config['metadata'][name]['mode'] == 'ocr':
            fields.extend([f'{name}_confidence', f'{name}_status', f'{name}_crop'])
    master = []
    for r in results:
        row = {k:r.get(k, '') for k in fields}
        for name, detail in r.get('metadata_details', {}).items():
            for suffix in ('confidence','status','crop'):
                row[f'{name}_{suffix}'] = detail.get(suffix, '')
        for a in r['responses']:
            row[f"Q{a['question']}_review"] = 'reviewed' if a.get('teacher_review') else 'pending' if a.get('review_reasons') else ''
            row[f"Q{a['question']}"] = '|'.join(a['selected'])
            row[f"Q{a['question']}_status"] = a['status']
        master.append(row)
    for q in config['questions']:
        fields.extend([f"Q{q['id']}", f"Q{q['id']}_status", f"Q{q['id']}_review"])
    write('students.csv', master, fields)
    groups = defaultdict(list)
    for r in results:
        groups[r.get('class') or '(unrecognized)'].append(r)
    summaries = ([describe(results, 'ALL')] if results else []) + [describe(rows, name) for name,rows in sorted(groups.items())]
    write('class_statistics.csv', summaries, ['group','count','mean','median','minimum','maximum','standard_deviation','passed','failed','pass_percent','provisional_count','review_required_count'])
    items = []
    for group, rows in [('ALL', results), *sorted(groups.items())]:
        for i, q in enumerate(config['questions']):
            answers = [r['responses'][i] for r in rows]
            counts = Counter(label for a in answers for label in a['selected'])
            for label in q['labels']:
                items.append(dict(group=group, question=q['id'], option=label, is_key=label == q['answer'],
                                  selection_count=counts[label], selection_percent=100*counts[label]/len(rows) if rows else 0,
                                  facility_percent=100*sum(a['status']=='correct' for a in answers)/len(rows) if rows else 0,
                                  pending_review_count=sum(bool(a.get('review_reasons')) and not a.get('teacher_review') for a in answers),
                                  blank_count=sum(a['status']=='blank' for a in answers), multiple_count=sum(a['status']=='multiple' for a in answers), count=len(rows)))
    write('item_statistics.csv', items, ['group','question','option','is_key','selection_count','selection_percent','facility_percent','blank_count','multiple_count','pending_review_count','count'])
    (output/'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    (output/'events.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False)+'\n' for e in events), encoding='utf-8')
