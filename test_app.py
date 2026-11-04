"""Run: python -m unittest -v test_app.py"""
import os
import tempfile
import unittest

from app import app


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app.config.update(TESTING=True, DATABASE_PATH=os.path.join(self.temp.name, 'test.db'), SECRET_KEY='test-key')
        self.client = app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def csrf(self):
        with self.client.session_transaction() as s:
            return s['csrf']

    def register(self, name, username):
        self.client.get('/register')
        return self.client.post('/register', data={'csrf_token': self.csrf(), 'name': name, 'username': username, 'password': 'SafePass123!'}, follow_redirects=True)

    def test_author_ownership_and_replies(self):
        r = self.register('Susan', 'susan')
        self.assertIn(b'Community issues', r.data)
        r = self.client.post('/new/issue', data={'csrf_token': self.csrf(), 'title': 'Neighborhood potluck', 'description': 'Please bring snacks.', 'event_at': '2026-11-14T17:00', 'location': 'Clubhouse', 'status': 'Open'}, follow_redirects=True)
        self.assertIn(b'Neighborhood potluck', r.data)
        self.client.post('/logout', data={'csrf_token': self.csrf()})
        self.register('Joey', 'joey')
        self.assertEqual(self.client.get('/post/1/edit').status_code, 403)
        self.assertEqual(self.client.post('/post/1/delete', data={'csrf_token': self.csrf()}).status_code, 403)
        r = self.client.post('/post/1/comment', data={'csrf_token': self.csrf(), 'body': 'I can bring bread.'}, follow_redirects=True)
        self.assertIn(b'I can bring bread.', r.data)
        self.client.post('/logout', data={'csrf_token': self.csrf()})
        self.client.get('/login')
        self.client.post('/login', data={'csrf_token': self.csrf(), 'username': 'susan', 'password': 'SafePass123!'})
        self.assertEqual(self.client.get('/post/1/edit').status_code, 200)
        r = self.client.post('/post/1/edit', data={'csrf_token': self.csrf(), 'title': 'Potluck updated', 'description': 'New information!', 'status': 'Resolved'}, follow_redirects=True)
        self.assertIn(b'Potluck updated', r.data)

    def test_login_required_csrf_and_chat(self):
        self.assertEqual(self.client.get('/issues').status_code, 302)
        self.register('Maria', 'maria')
        self.assertEqual(self.client.post('/chat', data={'body': 'hello'}).status_code, 400)
        r = self.client.post('/chat', data={'csrf_token': self.csrf(), 'body': 'Hello neighbors!'}, follow_redirects=True)
        self.assertIn(b'Hello neighbors!', r.data)
        self.assertIn(b'Maria', self.client.get('/members').data)


if __name__ == '__main__':
    unittest.main()
