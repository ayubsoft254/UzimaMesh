from django.test import TestCase
from django.contrib.auth.models import User

class DatabaseConnectivityTest(TestCase):
    def test_database_connection(self):
        """Simple smoke test to ensure the database is reachable."""
        user_count = User.objects.count()
        self.assertIsInstance(user_count, int)
