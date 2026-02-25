import os
import unittest

from django.db import connection
from django.test import TestCase


@unittest.skipUnless(
    os.getenv('DATABASE_URL'),
    'Skipping PostgreSQL connectivity test: DATABASE_URL is not set. '
    'Set DATABASE_URL to run this integration test against the configured Postgres/PgBouncer backend.'
)
class DatabaseConnectivityTest(TestCase):
    def test_database_connection(self):
        """Integration test: validates the configured database backend is reachable via SELECT 1."""
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            result = cursor.fetchone()
        self.assertEqual(result[0], 1)
