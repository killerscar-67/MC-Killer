"""Single-server teacher pilot with isolated accounts and persisted batch jobs."""
import argparse
import getpass
import hashlib
import io
import json
import logging
import os
import secrets
import threading
import time
import uuid
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from .core import export, grade, validate
from .review import refresh_review
from .database import connect,initialize,begin_write,locked,next_queued,INTEGRITY_ERRORS

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['name','signature','class','student_id','subject_paper']
ALLOWED = {'.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp'}


def create_app(data=None, testing=False, start_worker=True):
    data = Path(data or os.environ.get('MCK_DATA_DIR',ROOT/'instance')).resolve()
    secret = os.environ.get('MCK_SECRET_KEY')
    if not secret and not testing:
        raise RuntimeError('Set MCK_SECRET_KEY to a random secret before starting the server')
    initialize(data)
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secret or 'test-only-secret', TESTING=testing, DATA=data,
                      MAX_CONTENT_LENGTH=50*1024*1024, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('MCK_HTTPS')=='1',
                      PERMANENT_SESSION_LIFETIME=8*3600)
    app.config.update(AUTH_MODE=os.environ.get('MCK_AUTH_MODE','password' if testing else 'google'),
                      GOOGLE_CLIENT_ID=os.environ.get('MCK_GOOGLE_CLIENT_ID',''),
                      GOOGLE_CLIENT_SECRET=os.environ.get('MCK_GOOGLE_CLIENT_SECRET',''),
                      GOOGLE_REDIRECT_URI=os.environ.get('MCK_GOOGLE_REDIRECT_URI',''))
    if app.config['AUTH_MODE'] not in ('google','password'): raise ValueError('MCK_AUTH_MODE must be google or password')
    from .google_login import register_google
    register_google(app,connect,data)
    attempts = {}
    attempts_lock=threading.Lock()

    def audit(db,jid,action,detail):
        db.execute('INSERT INTO audit(job,actor,at,action,detail) VALUES(?,?,?,?,?)',
                   (jid,session['user'],time.time(),action,json.dumps(detail,ensure_ascii=False)))

    @app.before_request
    def csrf():
        if 'csrf' not in session:
            session['csrf']=secrets.token_urlsafe(32)
        if request.method=='POST' and not secrets.compare_digest(request.form.get('csrf',''),session['csrf']):
            abort(400,'Form expired. Reload the page and try again.')

    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args,**kwargs):
            with connect(data) as db:
                user=db.execute('SELECT enabled FROM users WHERE id=?',(session.get('user',''),)).fetchone()
            if not user or not user['enabled'] or session.get('auth_method','password')!=app.config['AUTH_MODE']:
                session.pop('user',None)
                return redirect(url_for('login'))
            return fn(*args,**kwargs)
        return wrapper

    def owned(jid):
        with connect(data) as db:
            job=db.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(jid,session['user'])).fetchone()
        if not job:
            abort(404)
        return dict(job)

    @app.get('/healthz')
    def health():
        with connect(data) as db: db.execute('SELECT 1')
        return {'status':'ok'}

    @app.route('/login',methods=['GET','POST'])
    def login():
        if app.config['AUTH_MODE']=='google':
            if request.method=='POST': abort(405)
            return render_template('login.html',google_mode=True,google_configured=all(app.config.get(k) for k in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REDIRECT_URI')))
        if request.method=='POST':
            email=request.form.get('email','').strip().lower()
            key=(request.remote_addr,email)
            with attempts_lock:
                now=time.time()
                # Bound memory and use a short per-IP/account cooldown.
                for old in [k for k,v in attempts.items() if now-v[1]>600]:
                    attempts.pop(old,None)
                failures,last=attempts.get(key,(0,now))
                if failures>=10 and now-last<600:
                    abort(429,'Too many attempts. Try again in ten minutes.')
            with connect(data) as db:
                user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if user and user['enabled'] and user['password'] and check_password_hash(user['password'],request.form.get('password','')):
                with attempts_lock:
                    attempts.pop(key,None)
                session.clear()
                session.update(user=user['id'],email=user['email'],auth_method='password',csrf=secrets.token_urlsafe(32))
                session.permanent=True
                return redirect(url_for('index'))
            with attempts_lock:
                attempts[key]=(failures+1,now)
            flash('Email or password is incorrect.','error')
        return render_template('login.html')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    @login_required
    def index():
        with connect(data) as db:
            jobs=db.execute('SELECT * FROM jobs WHERE owner=? ORDER BY created DESC',(session['user'],)).fetchall()
        return render_template('index.html',jobs=jobs)

    @app.route('/assessments/new',methods=['GET','POST'])
    @login_required
    def new():
        if request.method=='GET':
            return render_template('new.html')
        directory=None
        try:
            count=int(request.form.get('count','0'))
            key=''.join(request.form.get('key','').upper().split())
            if not 1<=count<=100 or len(key)!=count or any(c not in 'ABCD' for c in key):
                raise ValueError('Enter 1–100 questions and exactly one A–D answer per question.')
            title=request.form.get('title','').strip()
            if not title or len(title)>160:
                raise ValueError('Enter an assessment name of 1–160 characters.')
            config=json.loads((Path(__file__).parent/'layouts/delia-layout.json').read_text())
            config['template_image']=str(Path(__file__).parent/'layouts/delia-template.png')
            config['questions']=[{**q,'answer':key[i]} for i,q in enumerate(config['questions'][:count])]
            config['scoring']={'correct':1,'wrong':float(request.form.get('wrong','0')),'blank':0,'multiple':0}
            config['pass_percent']=float(request.form.get('pass','50'))
            validate(config)
            uploads=[f for f in request.files.getlist('scans') if f.filename]
            if not uploads or len(uploads)>100:
                raise ValueError('Upload between 1 and 100 PDF or image files.')
            jid=uuid.uuid4().hex
            directory=data/'batches'/jid
            source=directory/'input'
            source.mkdir(parents=True,mode=0o700)
            total_pages=0
            manifest=[]
            for i,f in enumerate(uploads):
                filename=secure_filename(f.filename)
                extension=Path(filename).suffix.lower()
                if extension not in ALLOWED:
                    raise ValueError('Only PDF, PNG, JPEG, TIFF and BMP files are supported.')
                destination=source/f'{i+1:03d}-{filename}'
                f.save(destination)
                total_pages+=inspect_upload(destination)
                if total_pages>200:
                    raise ValueError('Limit each batch to 200 pages.')
                manifest.append({'stored':destination.name,'original':f.filename,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()})
            (directory/'manifest.json').write_text(json.dumps(manifest))
            now=time.time()
            with connect(data) as db:
                db.execute('INSERT INTO jobs(id,owner,title,subject,level,state,created,updated,config) VALUES(?,?,?,?,?,?,?,?,?)',
                    (jid,session['user'],title,request.form.get('subject','').strip()[:160],request.form.get('level','').strip()[:80],'queued',now,now,json.dumps(config)))
                audit(db,jid,'created',{'files':len(uploads),'pages':total_pages})
            return redirect(url_for('assessment',jid=jid))
        except (ValueError,TypeError,OSError) as exc:
            if directory:
                import shutil
                shutil.rmtree(directory,ignore_errors=True)
            flash(str(exc),'error')
            return render_template('new.html'),400

    @app.get('/assessments/<jid>')
    @login_required
    def assessment(jid):
        job=owned(jid)
        results=json.loads(job['results'])
        with connect(data) as db:
            history=db.execute('SELECT action,at FROM audit WHERE job=? ORDER BY id DESC LIMIT 20',(jid,)).fetchall()
        return render_template('assessment.html',job=job,results=results,history=history,
            pending=sum(r.get('review_required',False) for r in results))

    @app.get('/assessments/<jid>/sheets/<int:index>')
    @login_required
    def sheet(jid,index):
        job=owned(jid)
        results=json.loads(job['results'])
        if not 0<=index<len(results): abort(404)
        row=results[index]
        output=(data/'batches'/jid/'output').resolve()
        def asset(path):
            if not path: return None
            try:
                relative=Path(path).resolve().relative_to(output)
            except ValueError:
                return None
            return url_for('image',jid=jid,path=relative.as_posix())
        return render_template('sheet.html',job=job,row=row,index=index,fields=FIELDS,asset=asset,
            full_image=url_for('image',jid=jid,path=f'review/{index+1:05d}.png'))

    @app.get('/assessments/<jid>/images/<path:path>')
    @login_required
    def image(jid,path):
        owned(jid)
        root=(data/'batches'/jid/'output'/'review').resolve()
        candidate=(data/'batches'/jid/'output'/path).resolve()
        try: candidate.relative_to(root)
        except ValueError: abort(404)
        if candidate.suffix.lower()!='.png' or not candidate.is_file(): abort(404)
        return send_file(candidate,mimetype='image/png')

    @app.post('/assessments/<jid>/sheets/<int:index>/review')
    @login_required
    def review(jid,index):
        owned(jid)
        with connect(data) as db:
            begin_write(db)
            job=dict(locked(db,'SELECT * FROM jobs WHERE id=? AND owner=?',(jid,session['user'])).fetchone())
            if job['state']!='ready' or job['finalized']: abort(409,'Assessment is not open for review.')
            # Reject stale forms from another tab or teacher session.
            if request.form.get('version')!=str(job['updated']): abort(409,'Results changed. Reload before saving.')
            rows=json.loads(job['results'])
            if not 0<=index<len(rows): abort(404)
            row=rows[index]
            before=json.loads(json.dumps(row))
            for answer in row['responses']:
                decision=request.form.get('q'+answer['question'],'').strip().upper()
                if not decision: continue
                labels=[] if decision=='BLANK' else decision.split('|')
                config=json.loads(job['config'])
                q=next(q for q in config['questions'] if str(q['id'])==answer['question'])
                if len(set(labels))!=len(labels) or any(label not in q['labels'] for label in labels): abort(400,'Invalid answer decision.')
                answer.setdefault('raw_selected',list(answer['selected']))
                answer['teacher_review']={'previous_selected':answer['selected'],'decision':labels,'note':request.form.get('note','')[:2000], 'actor':session['email'],'at':time.time()}
                answer['selected']=labels
            if request.form.get('confirm_metadata')=='yes':
                row.setdefault('original_metadata',{f:row.get(f,'') for f in FIELDS})
                for field in FIELDS:
                    row[field]=request.form.get(field,'').strip()[:500]
                row['teacher_metadata_review']={'actor':session['email'],'at':time.time(),'note':request.form.get('note','')[:2000]}
                row['sheet_review_issues']=[issue for issue in row.get('sheet_review_issues',[]) if not issue.startswith('metadata_')]
            row.update(grade(row['responses'],json.loads(job['config'])))
            refresh_review(row)
            # Re-evaluate duplicates across the batch after identity edits.
            identities={}
            for candidate in rows:
                candidate['sheet_review_issues']=[s for s in candidate.get('sheet_review_issues',[]) if s!='duplicate_identity']
                identity=(candidate.get('class'),candidate.get('student_id'))
                if all(identity): identities.setdefault(identity,[]).append(candidate)
            for group in identities.values():
                if len(group)>1:
                    for candidate in group: candidate['sheet_review_issues'].append('duplicate_identity')
            for candidate in rows: refresh_review(candidate)
            db.execute('UPDATE jobs SET results=?,updated=? WHERE id=?',(json.dumps(rows,ensure_ascii=False),time.time(),jid))
            audit(db,jid,'sheet_reviewed',{'sheet':index,'before':before,'after':row})
        flash('Review saved. Scores and statistics updated.','success')
        return redirect(url_for('sheet',jid=jid,index=index))

    @app.post('/assessments/<jid>/finalize')
    @login_required
    def finalize(jid):
        owned(jid)
        with connect(data) as db:
            begin_write(db)
            job=dict(locked(db,'SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
            rows=json.loads(job['results'])
            if job['state']!='ready' or not rows or any(r.get('review_required') for r in rows):
                abort(409,'Resolve every answer and identity review before finalizing.')
            db.execute('UPDATE jobs SET finalized=1,updated=? WHERE id=?',(time.time(),jid))
            audit(db,jid,'finalized',{'sheets':len(rows)})
        return redirect(url_for('assessment',jid=jid))

    @app.post('/assessments/<jid>/retry')
    @login_required
    def retry(jid):
        owned(jid)
        with connect(data) as db:
            db.execute('UPDATE jobs SET state=?,error=?,updated=? WHERE id=? AND state=?',('queued','',time.time(),jid,'failed'))
            audit(db,jid,'retry_requested',{})
        return redirect(url_for('assessment',jid=jid))

    @app.get('/assessments/<jid>/export/<kind>')
    @login_required
    def download(jid,kind):
        job=owned(jid)
        if job['state']!='ready': abort(409)
        allowed={'students':'students.csv','classes':'class_statistics.csv','items':'item_statistics.csv','details':'results.json'}
        if kind not in allowed: abort(404)
        # Produce exports from the authoritative database snapshot, not stale disk results.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            export(json.loads(job['results']),json.loads(job['config']),tmp,[])
            content=(Path(tmp)/allowed[kind]).read_bytes()
        return send_file(io.BytesIO(content),as_attachment=True,download_name=allowed[kind],mimetype='application/json' if kind=='details' else 'text/csv')

    @app.errorhandler(413)
    def too_large(exc):
        return render_template('error.html',message='The upload exceeds the 50 MB batch limit.'),413

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(429)
    @app.errorhandler(503)
    def error(exc):
        return render_template('error.html',message=exc.description),exc.code

    if start_worker:
        # Run one service process; claim persisted jobs atomically in SQLite.
        with connect(data) as db:
            db.execute("UPDATE jobs SET state='failed',error='Processing interrupted by server restart. Retry this batch.' WHERE state='processing'")
        threading.Thread(target=worker,args=(data,),daemon=True).start()
    return app


def inspect_upload(path):
    try:
        if path.suffix.lower()=='.pdf':
            import fitz
            with fitz.open(path) as doc:
                if doc.is_encrypted: raise ValueError('Password-protected PDFs are not supported.')
                count=len(doc)
                if any(p.rect.width<=0 or p.rect.height<=0 or p.rect.width*p.rect.height>10_000_000 for p in doc):
                    raise ValueError('PDF page dimensions are too large.')
        else:
            from PIL import Image
            with Image.open(path) as image:
                count=getattr(image,'n_frames',1)
                for i in range(count):
                    image.seek(i)
                    if image.width*image.height>40_000_000: raise ValueError('Image dimensions are too large.')
                    image.load()
        if not 1<=count<=200: raise ValueError('Files must contain 1–200 pages.')
        return count
    except Exception as exc:
        raise ValueError(f'Cannot read {path.name}: {exc}') from exc


def process_job(data,job):
    from .cli import run
    directory=Path(data)/'batches'/job['id']
    try:
        code=run([directory/'input'],json.loads(job['config']),directory/'output')
        rows=json.loads((directory/'output/results.json').read_text())
        if code or not rows:
            raise ValueError('Some sheets failed processing. Check scan quality and retry; partial batches cannot be finalized.')
        with connect(data) as db:
            db.execute('UPDATE jobs SET state=?,results=?,error=?,updated=? WHERE id=?',('ready',json.dumps(rows,ensure_ascii=False),'',time.time(),job['id']))
    except Exception:
        logging.exception('Batch %s failed',job['id'])
        with connect(data) as db:
            db.execute('UPDATE jobs SET state=?,error=?,updated=? WHERE id=?',('failed','Processing failed. Check file quality and the server log, then retry.',time.time(),job['id']))


def worker(data):
    while True:
        try:
            with connect(data) as db:
                begin_write(db)
                job=next_queued(db)
                if job:
                    db.execute("UPDATE jobs SET state='processing',updated=? WHERE id=?",(time.time(),job['id']))
            if job: process_job(data,dict(job))
            else: time.sleep(1)
        except Exception:
            logging.exception('Worker error')
            time.sleep(2)


def main():
    parser=argparse.ArgumentParser(description='MC-Killer teacher pilot')
    parser.add_argument('command',choices=['serve','create-user','authorize-teacher','revoke-teacher'])
    parser.add_argument('--data',default=os.environ.get('MCK_DATA_DIR',str(ROOT/'instance')))
    parser.add_argument('--email')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--host',default='127.0.0.1')
    args=parser.parse_args()
    initialize(args.data)
    if args.command in ('authorize-teacher','revoke-teacher'):
        email=(args.email or input('Teacher email: ')).strip().lower()
        if email.count('@')!=1 or not email.endswith('@delia.edu.hk'): parser.error('Use an @delia.edu.hk teacher email.')
        with connect(args.data) as db:
            if args.command=='authorize-teacher':
                db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET enabled=1',(uuid.uuid4().hex,email,''))
                print('Teacher authorized for Google sign-in.')
            else:
                db.execute('UPDATE users SET enabled=0 WHERE email=?',(email,))
                print('Teacher access revoked, including existing sessions.')
    elif args.command=='create-user':
        email=(args.email or input('Teacher email: ')).strip().lower()
        password=getpass.getpass('Password (at least 12 characters): ')
        if '@' not in email or len(password)<12: parser.error('Use a valid email and a password of at least 12 characters.')
        with connect(args.data) as db:
            try: db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)',(uuid.uuid4().hex,email,generate_password_hash(password,method='pbkdf2:sha256:1000000')))
            except INTEGRITY_ERRORS: parser.error('That account already exists.')
        print('Teacher account created.')
    else:
        from waitress import serve
        serve(create_app(args.data),host=args.host,port=args.port,threads=8)

if __name__=='__main__': main()
