"""Teacher-owned reusable rosters and explicitly versioned candidate snapshots."""
import io
import json
import time
import uuid

from flask import Blueprint,abort,flash,redirect,render_template,request,send_file,session,url_for
from itsdangerous import URLSafeTimedSerializer,BadSignature,SignatureExpired
from .database import connect,begin_write,locked
from .student_lists import student,validate_students,parse_import,export_list


def register_rosters(app,data,login_required,owned,audit):
    bp=Blueprint('lists',__name__)
    signer=URLSafeTimedSerializer(app.secret_key,salt='roster-import-v1')

    def get_list(db,rid,write=False):
        query='SELECT * FROM rosters WHERE id=? AND owner=?'
        row=(locked(db,query,(rid,session['user'])) if write else db.execute(query,(rid,session['user']))).fetchone()
        if not row:abort(404)
        return dict(row)

    def roster_audit(db,rid,action,detail):
        db.execute('INSERT INTO roster_audit(roster,actor,at,action,detail) VALUES(?,?,?,?,?)',(rid,session['user'],time.time(),action,json.dumps(detail,ensure_ascii=False)))

    def current(job):
        if job['finalized'] or job['state'] not in ('draft','ready'):abort(409,'Candidates can be edited before scanning or after processing, while results remain open.')
        if request.form.get('version')!=str(job['updated']):abort(409,'This assessment changed. Reload and try again.')

    @bp.route('/rosters',methods=['GET','POST'])
    @login_required
    def index():
        if request.method=='POST':
            title=request.form.get('title','').strip();year=request.form.get('school_year','').strip()
            if not title or len(title)>160 or not year or len(year)>40:abort(400,'Enter a roster name and school year.')
            rid=uuid.uuid4().hex;now=time.time()
            with connect(data) as db:
                db.execute('INSERT INTO rosters(id,owner,title,school_year,students,created,updated) VALUES(?,?,?,?,?,?,?)',(rid,session['user'],title,year,'[]',now,now))
                roster_audit(db,rid,'created',{})
            return redirect(url_for('lists.edit',rid=rid))
        with connect(data) as db:rows=[dict(r) for r in db.execute('SELECT * FROM rosters WHERE owner=? ORDER BY school_year DESC,title',(session['user'],)).fetchall()]
        return render_template('rosters.html',rosters=rows)

    @bp.route('/rosters/<rid>',methods=['GET','POST'])
    @login_required
    def edit(rid):
        preview=None;changes=None;pending=None
        with connect(data) as db:
            if request.method=='POST':begin_write(db)
            roster=get_list(db,rid,request.method=='POST');students=json.loads(roster['students'])
            if request.method=='POST':
                if request.form.get('version')!=str(roster['version']):abort(409,'Roster changed in another tab. Reload before editing.')
                action=request.form.get('action')
                try:
                    if action=='import':
                        file=request.files.get('file')
                        if not file:raise ValueError('Choose a CSV or XLSX roster.')
                        preview,changes=parse_import(file.stream.read(1024*1024+1),file.filename,students)
                        pending=signer.dumps({'roster':rid,'actor':session['user'],'version':roster['version'],'students':preview,'changes':changes})
                    elif action=='confirm_import':
                        try:proposal=signer.loads(request.form.get('proposal',''),max_age=900)
                        except (BadSignature,SignatureExpired):raise ValueError('Preview expired or invalid. Upload the roster again.')
                        if (proposal['roster'],proposal['actor'],proposal['version'])!=(rid,session['user'],roster['version']):abort(409,'Import preview no longer matches this roster.')
                        students=validate_students(proposal['students']);changes=proposal['changes']
                    elif action in ('add','edit'):
                        rid_student=request.form.get('record_id')
                        if action=='edit' and rid_student not in {r['record_id'] for r in students}:abort(404)
                        row=student(request.form,rid_student if action=='edit' else None)
                        before=next((r for r in students if r['record_id']==row['record_id']),None)
                        students=validate_students([r for r in students if r['record_id']!=row['record_id']]+[row])
                        changes=[{'before':before,'after':row}]
                    elif action=='rename':
                        title=request.form.get('title','').strip();year=request.form.get('school_year','').strip()
                        if not title or len(title)>160 or not year or len(year)>40:raise ValueError('Enter a roster name and school year.')
                        db.execute('UPDATE rosters SET title=?,school_year=? WHERE id=?',(title,year,rid));changes=[{'title':title,'school_year':year}]
                    else:raise ValueError('Unknown roster action.')
                    if action!='import':
                        db.execute('UPDATE rosters SET students=?,version=version+1,updated=? WHERE id=?',(json.dumps(students,ensure_ascii=False),time.time(),rid))
                        roster_audit(db,rid,action,changes)
                        flash('Roster saved. Existing assessment candidates have not changed.')
                        return redirect(url_for('lists.edit',rid=rid))
                except ValueError as exc:abort(400,str(exc))
            history=db.execute('SELECT action,at FROM roster_audit WHERE roster=? ORDER BY id DESC LIMIT 30',(rid,)).fetchall()
        return render_template('roster_edit.html',roster=roster,students=students,history=history,changes=changes,proposal=pending)

    @bp.get('/rosters/<rid>/export')
    @login_required
    def export(rid):
        with connect(data) as db:roster=get_list(db,rid)
        return send_file(io.BytesIO(export_list(json.loads(roster['students']))),as_attachment=True,download_name='roster.csv',mimetype='text/csv')

    @bp.route('/assessments/<jid>/candidates',methods=['GET','POST'])
    @login_required
    def candidates(jid):
        owned(jid)
        with connect(data) as db:
            if request.method=='POST':begin_write(db)
            job=dict(locked(db,'SELECT * FROM jobs WHERE id=?',(jid,)).fetchone());config=json.loads(job['config'])
            if not config.get('roster_snapshot_version'):abort(404)
            source=get_list(db,config['roster_id']) if config.get('roster_id') else None
            available=json.loads(source['students']) if source else config['roster']
            rows=json.loads(job['results']);bound={r.get('student_record_id') for r in rows if r.get('student_record_id')}
            if request.method=='POST':
                if job['finalized'] or job['state']!='ready':abort(409,'Candidate changes are available after processing, while results remain open.')
                if request.form.get('version')!=str(job['updated']):abort(409,'Assessment changed. Reload before updating candidates.')
                if source and str(source['version'])!=request.form.get('roster_version'):abort(409,'The source roster changed. Reload before applying it.')
                selected=request.form.getlist('candidate');by_id={r['record_id']:r for r in available}
                if not selected or len(selected)!=len(set(selected)) or not set(selected)<=set(by_id):abort(400,'Select valid candidates.')
                if bound-set(selected):abort(409,'Submitted students must retain their historical assessment record. Reassign an incorrect sheet before removing a candidate.')
                if any(not by_id[r].get('active',True) and r not in bound for r in selected):abort(400,'Reactivate withdrawn students in the roster before adding them.')
                previous={r['record_id']:r for r in config['roster']};updated=[]
                for rid in selected:
                    # Names/classes on submitted records are historical; no silent rewrites.
                    updated.append(previous[rid] if rid in bound else {**by_id[rid],'absent':False})
                updated.extend({**r,'absent':True} for rid,r in previous.items() if rid not in selected)
                config['roster']=sorted(updated,key=lambda r:(r['class'],int(r['student_id']),r['record_id']))
                if source:config['roster_version']=source['version']
                db.execute('UPDATE jobs SET config=?,updated=? WHERE id=?',(json.dumps(config,ensure_ascii=False),time.time(),jid))
                audit(db,jid,'candidate_snapshot_updated',{'source_version':source['version'] if source else None,'selected':selected})
                flash('Candidates saved. Submitted identities were kept. Check the submission record and identity assignments before finalising.')
                return redirect(url_for('lists.candidates',jid=jid))
        return render_template('candidates.html',job=job,config=config,source=source,available=available,selected={r['record_id'] for r in config['roster'] if not r['absent']},submitted=bound)

    @bp.route('/assessments/<jid>/identities',methods=['GET','POST'])
    @login_required
    def identities(jid):
        from .review import refresh_review
        owned(jid)
        with connect(data) as db:
            if request.method=='POST':begin_write(db)
            job=dict(locked(db,'SELECT * FROM jobs WHERE id=?',(jid,)).fetchone());config=json.loads(job['config']);rows=json.loads(job['results'])
            if not config.get('roster_snapshot_version') or job['state']!='ready':abort(409,'Wait for roster processing to finish.')
            if request.method=='POST':
                if job['finalized']:abort(409,'This assessment is finalised.')
                if request.form.get('version')!=str(job['updated']):abort(409,'Assessment changed. Reload before reviewing identities.')
                choices={r['record_id']:r for r in config['roster'] if not r['absent']};assigned=set();decisions=[]
                for i,row in enumerate(rows):
                    rid=request.form.get('student_'+str(i),'')
                    if rid and (rid not in choices or rid in assigned):abort(400,'Each candidate can be assigned to at most one sheet.')
                    if rid:assigned.add(rid)
                    if rid==row.get('student_record_id',''):continue
                    previous={k:row.get(k) for k in ('name','class','student_id','student_record_id','identity_source')}
                    row.setdefault('original_identity',previous)
                    row['sheet_review_issues']=[s for s in row.get('sheet_review_issues',[]) if s!='identity_unassigned']
                    if rid:
                        candidate=choices[rid];row.update(name=candidate['name'],student_id=candidate['student_id'],**{'class':candidate['class']},student_record_id=rid,identity_source='teacher_roster',roster_assignment=dict(candidate))
                    else:
                        row.update(name='',student_id='',**{'class':''},student_record_id='',identity_source='roster_pending');row['sheet_review_issues'].append('identity_unassigned')
                    row['teacher_identity_review']={'actor':session['email'],'at':time.time(),'previous':previous,'record_id':rid}
                    refresh_review(row);decisions.append({'sheet':i,'previous':previous,'record_id':rid})
                db.execute('UPDATE jobs SET results=?,updated=? WHERE id=?',(json.dumps(rows,ensure_ascii=False),time.time(),jid));audit(db,jid,'identities_reviewed',decisions)
                return redirect(url_for('lists.identities',jid=jid))
        return render_template('identities.html',job=job,rows=rows,candidates=[r for r in config['roster'] if not r['absent']])

    app.register_blueprint(bp)
