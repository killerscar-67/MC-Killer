"""Assessment-private class lists and deterministic exam-stack identities."""
import csv
import hashlib
import io
import json
import re


def parse_roster(content):
    if not content or len(content)>1024*1024:
        raise ValueError('Upload a UTF-8 CSV class list smaller than 1 MB.')
    try:
        reader=csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        headers=[(h or '').strip().lower() for h in (reader.fieldnames or [])]
        if len(headers)!=len(set(headers)):
            raise ValueError('Class-list column names must be unique.')
        reader.fieldnames=headers
        number=next((h for h in ('number','class_number','student_id') if h in headers),None)
        if not number or not {'class','name'}.issubset(headers):
            raise ValueError('The CSV needs class, number and name columns.')
        rows=[];seen=set()
        for row in reader:
            if not any(str(v or '').strip() for v in row.values()): continue
            klass=re.sub(r'\s+','',row.get('class') or '').upper()
            student_id=(row.get(number) or '').strip()
            name=(row.get('name') or '').strip()
            if not re.fullmatch(r'[0-9]+[A-Z]',klass) or len(klass)>12:
                raise ValueError('Each class must be digits followed by one letter, such as 3A.')
            if not re.fullmatch(r'[0-9]{1,6}',student_id) or not name or len(name)>200:
                raise ValueError('Each student needs a numeric class number and a name of 1–200 characters.')
            if int(student_id) in seen:
                raise ValueError('Class numbers must be unique (01 and 1 are the same number).')
            seen.add(int(student_id))
            rows.append({'class':klass,'student_id':student_id,'name':name,'absent':False})
            if len(rows)>200: raise ValueError('Limit a class list to 200 students.')
        if not rows or len({r['class'] for r in rows})!=1:
            raise ValueError('Upload a nonempty class list for one class.')
        return sorted(rows,key=lambda r:int(r['student_id']))
    except (UnicodeDecodeError,csv.Error) as exc:
        raise ValueError('Cannot read the class list. Export it as UTF-8 CSV.') from exc


def roster_digest(rows):
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()


def with_absences(rows,absent):
    key='record_id' if all(r.get('record_id') for r in rows) else 'student_id'
    numbers={r[key] for r in rows}
    if len(absent)!=len(set(absent)) or not set(absent).issubset(numbers):
        raise ValueError('Invalid absence selection. Preview the class list again.')
    marked=[{**r,'absent':r[key] in absent} for r in rows]
    if all(r['absent'] for r in marked):
        raise ValueError('Select at least one student who sat the exam.')
    return marked


def assign_roster(results,config):
    if config.get('identity_mode')!='roster': return
    present=[r for r in config['roster'] if not r['absent']]
    if len(results)!=len(present):
        raise ValueError(f'Sheet count ({len(results)}) must match students sitting the exam ({len(present)}).')
    for position,(result,student) in enumerate(zip(results,present),1):
        result.update(name=student['name'],student_id=student['student_id'],
                      **{'class':student['class']},signature='',
                      subject_paper=config.get('assessment_subject',''),
                      identity_source='roster_order',roster_position=position,
                      roster_assignment={k:student[k] for k in ('name','class','student_id','record_id','english_name','chinese_name') if k in student})
        if student.get('record_id'):result['student_record_id']=student['record_id']


def submission_csv(config,results):
    if not config.get('roster_snapshot_version') and len(results)!=sum(not student['absent'] for student in config['roster']):
        raise ValueError('Submission record requires one processed sheet per student sitting the exam.')
    stream=io.StringIO(newline='')
    writer=csv.writer(stream)
    writer.writerow(['class','number','name','attendance','submission','sheet'])
    sheet=0
    for student in config['roster']:
        if not student['absent']: sheet+=1
        assigned=next((i+1 for i,r in enumerate(results) if r.get('student_record_id')==student.get('record_id')),None) if config.get('roster_snapshot_version') else sheet
        values=[student['class'],student['student_id'],student['name'],
                'Absent' if student['absent'] else 'Present',
                'Not expected' if student['absent'] else 'Submitted' if assigned else 'Not submitted',
                '' if student['absent'] else assigned or '']
        writer.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v for v in values])
    return ('\ufeff'+stream.getvalue()).encode('utf-8')
