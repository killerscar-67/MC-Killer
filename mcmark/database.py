"""SQLite development storage and pooled PostgreSQL production storage."""
import json
import os
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

try:
    import psycopg
    from psycopg_pool import ConnectionPool
    INTEGRITY_ERRORS=(sqlite3.IntegrityError,psycopg.IntegrityError)
except ImportError:
    psycopg=None
    INTEGRITY_ERRORS=(sqlite3.IntegrityError,)


class Record(dict):
    """Mapping rows, with SQLite's positional-read convenience for existing callers."""
    def __getitem__(self,key):
        return tuple(self.values())[key] if isinstance(key,int) else super().__getitem__(key)


def record_factory(cursor):
    names=[column.name for column in cursor.description] if cursor.description else []
    def make(values):
        # The existing processing API consumes serialized JSON; store JSONB in PG.
        return Record(zip(names,[json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for v in values]))
    return make


@lru_cache(maxsize=4)
def pool_for(dsn,sslmode,sslrootcert):
    if psycopg is None: raise RuntimeError('Install the project PostgreSQL dependencies.')
    kwargs={'row_factory':record_factory,'connect_timeout':10,'prepare_threshold':None,'sslmode':sslmode}
    if sslmode=='verify-full': kwargs['sslrootcert']=sslrootcert
    return ConnectionPool(conninfo=dsn,min_size=0,max_size=8,timeout=15,kwargs=kwargs,open=True)


class PostgresConnection:
    dialect='postgres'
    def __init__(self,connection): self.connection=connection
    def execute(self,sql,parameters=()):
        # All statements are application-owned. Values always remain bound parameters.
        return self.connection.execute(sql.replace('?', '%s'),parameters)


@contextmanager
def connect(data):
    dsn=os.environ.get('MCK_DATABASE_URL')
    if dsn:
        if psycopg is None: raise RuntimeError('Install the project PostgreSQL dependencies.')
        sslmode=os.environ.get('MCK_DB_SSLMODE','verify-full')
        host=psycopg.conninfo.conninfo_to_dict(dsn).get('host','')
        if sslmode!='verify-full' and host not in ('localhost','127.0.0.1','::1'):
            raise RuntimeError('Remote database connections require sslmode=verify-full.')
        pool=pool_for(dsn,sslmode,os.environ.get('MCK_DB_SSLROOTCERT','system'))
        with pool.connection() as connection:
            connection.execute("SELECT set_config('search_path','mc_killer,pg_catalog',true)")
            yield PostgresConnection(connection)
    else:
        db=sqlite3.connect(str(Path(data)/'school.sqlite'),timeout=30)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()


def begin_write(db):
    if getattr(db,'dialect','sqlite')=='sqlite': db.execute('BEGIN IMMEDIATE')


def locked(db,sql,parameters=()):
    if getattr(db,'dialect','sqlite')=='postgres': sql+=' FOR UPDATE'
    return db.execute(sql,parameters)


def next_queued(db):
    sql="SELECT * FROM jobs WHERE state='queued' ORDER BY created LIMIT 1"
    if getattr(db,'dialect','sqlite')=='postgres': sql+=' FOR UPDATE SKIP LOCKED'
    return db.execute(sql).fetchone()


def initialize(data):
    Path(data).mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.environ.get('MCK_REQUIRE_POSTGRES')=='1' and not os.environ.get('MCK_DATABASE_URL'):
        raise RuntimeError('MCK_DATABASE_URL is required for this deployment.')
    if os.environ.get('MCK_DATABASE_URL'):
        with connect(data) as db:
            db.execute('SELECT id,google_sub,enabled FROM users LIMIT 0')
            db.execute('SELECT id FROM jobs LIMIT 0')
            db.execute('SELECT id FROM audit LIMIT 0')
        return
    with connect(data) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),title TEXT NOT NULL,
            subject TEXT NOT NULL,level TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,
            config TEXT NOT NULL,results TEXT NOT NULL DEFAULT '[]',error TEXT NOT NULL DEFAULT '',finalized INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,job TEXT NOT NULL REFERENCES jobs(id),
            actor TEXT NOT NULL REFERENCES users(id),at REAL NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL);
        ''')
        columns={row['name'] for row in db.execute('PRAGMA table_info(users)')}
        if 'google_sub' not in columns: db.execute('ALTER TABLE users ADD COLUMN google_sub TEXT')
        if 'enabled' not in columns: db.execute('ALTER TABLE users ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub ON users(google_sub)')
        db.execute('CREATE INDEX IF NOT EXISTS jobs_owner_created ON jobs(owner,created DESC)')
        db.execute('CREATE INDEX IF NOT EXISTS audit_job_id ON audit(job,id DESC)')
