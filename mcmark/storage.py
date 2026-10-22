"""Private, backend-only Supabase storage; local files are processing scratch space."""
import hashlib
import json
import mimetypes
import os
import re
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

import requests


class StorageError(OSError):
    pass


def safe_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')) or '\\' in value:
        raise StorageError('Invalid storage path.')
    return path


class SupabaseStorage:
    def __init__(self, url, key, bucket):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('MCK_SUPABASE_URL must be an HTTPS project URL.')
        if not key or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', bucket):
            raise ValueError('Configure a backend storage key and valid private bucket name.')
        self.url = url.rstrip('/') + '/storage/v1'
        self.key, self.bucket = key, bucket

    def request(self, method, path, **kwargs):
        headers = {'apikey': self.key}
        # New secret keys use apikey; legacy service-role JWTs also use Bearer.
        if not self.key.startswith('sb_secret_'):
            headers['Authorization'] = 'Bearer ' + self.key
        headers.update(kwargs.pop('headers', {}))
        try:
            response = requests.request(method, self.url + path, headers=headers,
                                        timeout=(10, 120), allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise StorageError('Private scan storage is unavailable. Try again later.') from None
        if not 200 <= response.status_code < 300:
            raise StorageError('Private scan storage request failed (HTTP %s).' % response.status_code)
        return response

    def check(self):
        bucket = self.request('GET', '/bucket/' + self.bucket).json()
        if bucket.get('public') is not False:
            raise StorageError('Scan storage bucket must be private.')

    def object_path(self, key):
        safe_path(key)
        return '/object/' + self.bucket + '/' + quote(key, safe='/')

    def put(self, key, content, content_type='application/octet-stream'):
        self.request('POST', self.object_path(key), data=content,
                     headers={'Content-Type': content_type, 'x-upsert': 'true'})

    def get(self, key):
        return self.request('GET', self.object_path(key)).content

    def save_tree(self, prefix, directory):
        """Publish the manifest last, only after every file is durable."""
        records = []
        for path in sorted(Path(directory).rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(directory).as_posix()
            content = path.read_bytes()
            self.put(prefix + '/' + relative, content, mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            records.append({'path': relative, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
        self.put(prefix + '/_manifest.json', json.dumps(records).encode(), 'application/json')

    def records(self, prefix):
        return json.loads(self.get(prefix + '/_manifest.json'))

    def read_verified(self, prefix, record):
        safe_path(record['path'])
        content = self.get(prefix + '/' + record['path'])
        if len(content) != record['size'] or hashlib.sha256(content).hexdigest() != record['sha256']:
            raise StorageError('Stored scan integrity check failed.')
        return content

    def restore_tree(self, prefix, directory):
        directory = Path(directory).resolve()
        for record in self.records(prefix):
            relative = safe_path(record['path'])
            destination = (directory / str(relative)).resolve()
            destination.relative_to(directory)
            content = self.read_verified(prefix, record)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination.write_bytes(content)

    def read_file(self, prefix, path):
        safe_path(path)
        for record in self.records(prefix):
            if record['path'] == path:
                return self.read_verified(prefix, record)
        raise FileNotFoundError(path)


def configured_storage():
    backend = os.environ.get('MCK_STORAGE_BACKEND', 'local')
    if backend == 'local':
        if os.environ.get('MCK_REQUIRE_PERSISTENT_STORAGE') == '1':
            raise RuntimeError('Persistent scan storage is required; configure MCK_STORAGE_BACKEND=supabase.')
        return None
    if backend != 'supabase':
        raise ValueError('MCK_STORAGE_BACKEND must be local or supabase.')
    return SupabaseStorage(os.environ.get('MCK_SUPABASE_URL', ''),
                           os.environ.get('MCK_SUPABASE_STORAGE_KEY', ''),
                           os.environ.get('MCK_STORAGE_BUCKET', 'mc-killer-scans'))


def job_prefix(job):
    if not re.fullmatch(r'[a-f0-9]{32}', job['id']):
        raise StorageError('Invalid assessment identifier.')
    return 'batches/' + job['id']


def relative_evidence(value, output):
    """Keep result image references independent of a container's filesystem path."""
    if isinstance(value, dict):
        return {k: relative_evidence(v, output) for k, v in value.items()}
    if isinstance(value, list):
        return [relative_evidence(v, output) for v in value]
    if isinstance(value, str):
        try:
            return Path(value).resolve().relative_to(output.resolve()).as_posix()
        except (ValueError, OSError):
            pass
    return value


def main():
    import argparse
    import time
    from .database import connect, initialize, begin_write, locked
    parser = argparse.ArgumentParser(description='Configure and migrate private scan storage')
    parser.add_argument('command', choices=['check', 'migrate'])
    parser.add_argument('--data', default=os.environ.get('MCK_DATA_DIR', 'instance'))
    args = parser.parse_args()
    storage = configured_storage()
    if not storage:
        parser.error('Configure MCK_STORAGE_BACKEND=supabase first.')
    storage.check()
    if args.command == 'check':
        # Synthetic probe only; never upload student material for this check.
        key = 'checks/' + uuid.uuid4().hex + '.txt'
        probe = b'MC-Killer private storage connectivity check'
        storage.put(key, probe, 'text/plain')
        if storage.get(key) != probe:
            raise StorageError('Storage round-trip verification failed.')
        storage.request('DELETE', '/object/' + storage.bucket, json={'prefixes': [key]})
        print('Private bucket verified; upload/download round trip passed.')
        return
    # Stop the web service/worker before running this command. Keep local files
    # until the deployment and review-image checks pass.
    data = Path(args.data).resolve()
    initialize(data)
    with connect(data) as db:
        jobs = [dict(row) for row in db.execute('SELECT * FROM jobs').fetchall()]
    for job in jobs:
        config = json.loads(job['config'])
        if config.get('_storage') == 'supabase':
            continue
        if job['state'] == 'processing':
            raise StorageError('Stop processing before migrating scans.')
        directory = data/'batches'/job['id']
        if not (directory/'input').is_dir() or not any((directory/'input').iterdir()):
            raise StorageError('Missing local originals for assessment ' + job['id'] + '; migration stopped.')
        if job['state'] == 'ready' and not (directory/'output/review').is_dir():
            raise StorageError('Missing local review evidence for assessment ' + job['id'] + '; migration stopped.')
        prefix = job_prefix(job)
        if (directory/'manifest.json').is_file() and not (directory/'input/manifest.json').exists():
            (directory/'input/manifest.json').write_bytes((directory/'manifest.json').read_bytes())
        storage.save_tree(prefix+'/input', directory/'input')
        if (directory/'output').is_dir():
            storage.save_tree(prefix+'/output', directory/'output')
        # Verify every object before recording the switch in the database.
        for section in ('input', 'output'):
            if (directory/section).is_dir():
                for record in storage.records(prefix+'/'+section):
                    storage.read_verified(prefix+'/'+section, record)
        config.update(_storage='supabase', _storage_bucket=storage.bucket)
        rows = relative_evidence(json.loads(job['results']), directory/'output')
        with connect(data) as db:
            begin_write(db)
            current = locked(db, 'SELECT updated FROM jobs WHERE id=?', (job['id'],)).fetchone()
            if current['updated'] != job['updated']:
                raise StorageError('Assessment changed during migration; stop the service and retry.')
            now = time.time()
            db.execute('UPDATE jobs SET config=?,results=?,updated=? WHERE id=?',
                       (json.dumps(config),json.dumps(rows,ensure_ascii=False),now,job['id']))
            db.execute('INSERT INTO audit(job,actor,at,action,detail) VALUES(?,?,?,?,?)',
                       (job['id'],job['owner'],now,'storage_migrated',json.dumps({'bucket':storage.bucket})))
        print('Migrated assessment ' + job['id'] + '; local originals retained.')


if __name__ == '__main__':
    main()
