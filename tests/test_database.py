import os
import unittest
from unittest.mock import Mock,patch
from mcmark.database import PostgresConnection,Record,locked,next_queued,connect


class DatabaseAdapterTests(unittest.TestCase):
    def test_values_stay_bound_and_rows_support_named_or_positional_access(self):
        raw=Mock()
        db=PostgresConnection(raw)
        db.execute('SELECT * FROM jobs WHERE owner=?',("teacher's ? input",))
        raw.execute.assert_called_once_with('SELECT * FROM jobs WHERE owner=%s',("teacher's ? input",))
        row=Record(id='id1',email='teacher@deliahw2.edu.hk')
        self.assertEqual(row[0],row['id'])
        self.assertEqual(row[1],row['email'])

    def test_postgres_locks_rows_and_skips_claimed_jobs(self):
        raw=Mock();db=PostgresConnection(raw)
        locked(db,'SELECT * FROM jobs WHERE id=?',('job1',))
        self.assertTrue(raw.execute.call_args.args[0].endswith('FOR UPDATE'))
        next_queued(db)
        self.assertTrue(raw.execute.call_args.args[0].endswith('FOR UPDATE SKIP LOCKED'))

    def test_remote_database_cannot_disable_tls_verification(self):
        with patch.dict(os.environ,{'MCK_DATABASE_URL':'postgresql://user:password@remote.example/postgres','MCK_DB_SSLMODE':'disable'}):
            with self.assertRaises(RuntimeError):
                with connect('/unused'): pass
