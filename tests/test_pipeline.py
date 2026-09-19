import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app import schemas, services
import jsonschema


class FixtureTests(unittest.TestCase):
    @patch('app.main.db')
    def test_review_missing_lead(self, db):
        connection = db.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = None
        self.assertEqual(TestClient(app).get('/leads/77').status_code, 404)

    @patch('app.main.db')
    def test_unqualified_cannot_draft(self, db):
        db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {'overall_score': 69, 'status': 'researched'}
        self.assertEqual(TestClient(app).post('/draft', json={'lead_id': 1}).status_code, 409)

    @patch('app.main.db')
    def test_completed_draft_retry_does_not_call_model(self, db):
        execute = db.return_value.__enter__.return_value.execute
        execute.return_value.fetchone.side_effect = [{'overall_score': 80, 'status': 'needs_review'}, {'id': 9, 'approved': False}]
        with patch('app.main.services.model') as model:
            response = TestClient(app).post('/draft', json={'lead_id': 1})
        self.assertEqual(response.json()['draft_id'], 9)
        model.assert_not_called()

    def test_api_bounds_and_approval_require_named_human(self):
        client = TestClient(app)
        self.assertEqual(client.post('/discover', json={'result_limit': 20}).status_code, 422)
        self.assertEqual(client.post('/drafts/1/approve', json={'approved_by': ' '}).status_code, 422)

    @patch('app.services.public_url', side_effect=['https://example.com/', ValueError('Private address rejected')])
    @patch('app.services.requests.Session')
    def test_redirect_is_validated_before_request(self, session, public):
        response = MagicMock()
        response.is_redirect = True
        response.headers = {'Location': 'http://127.0.0.1/secret'}
        session.return_value.get.return_value = response
        with self.assertRaises(ValueError):
            services.fetch('https://example.com/')
        self.assertEqual(session.return_value.get.call_count, 1)

    @patch('app.services.requests.Session')
    @patch('app.services.public_url', return_value='https://example.com/')
    def test_http_fixture_cleaning_and_byte_cap(self, public, session):
        response = MagicMock()
        response.is_redirect = False
        response.headers = {'Content-Type': 'text/html'}
        response.iter_content.return_value = [b'<html><title>Example</title><script>ignore me</script><p>We manufacture CNC tooling in Illinois and provide engineering services.</p></html>']
        session.return_value.get.return_value = response
        source = services.fetch('https://example.com/')
        self.assertIn('CNC tooling', source['text'])
        self.assertNotIn('ignore me', source['text'])
        response.iter_content.return_value = [b'x' * 1000001]
        with self.assertRaises(ValueError):
            services.fetch('https://example.com/')

    @patch('app.services.socket.getaddrinfo')
    def test_connection_pins_public_ip_preserving_tls_hostname(self, dns):
        import requests
        dns.return_value = [(0, 0, 0, '', ('93.184.216.34', 443))]
        adapter = services.PublicAddressAdapter()
        prepared = requests.Request('GET', 'https://example.com/page').prepare()
        pool = adapter.get_connection_with_tls_context(prepared, True)
        self.assertEqual(pool.host, '93.184.216.34')
        self.assertEqual(pool.assert_hostname, 'example.com')
        self.assertEqual(pool.conn_kw['server_hostname'], 'example.com')
        dns.return_value = [(0, 0, 0, '', ('127.0.0.1', 443))]
        with self.assertRaises(ValueError):
            adapter.get_connection_with_tls_context(prepared, True)

    @patch('app.services.time.monotonic', side_effect=[0, 1, 31])
    @patch('app.services.public_url', return_value='https://example.com/')
    @patch('app.services.requests.Session')
    def test_trickle_deadline_closes_response_and_session(self, session, public, clock):
        response = MagicMock()
        response.is_redirect = False
        response.headers = {'Content-Type': 'text/plain'}
        response.iter_content.return_value = [b'x']
        session.return_value.get.return_value = response
        with self.assertRaises(TimeoutError):
            services.fetch('https://example.com/')
        response.close.assert_called_once()
        session.return_value.close.assert_called_once()

    @patch.dict('os.environ', {'RESEARCH_TIMEOUT_SECONDS': '1000'})
    def test_configurable_timeout_is_bounded(self):
        self.assertEqual(services.timeout_setting('RESEARCH_TIMEOUT_SECONDS', 900, 1200), 1000)
        with patch.dict('os.environ', {'RESEARCH_TIMEOUT_SECONDS': '9999'}):
            with self.assertRaises(ValueError):
                services.timeout_setting('RESEARCH_TIMEOUT_SECONDS', 900, 1200)

    @patch('app.main.failed')
    @patch('app.main.claim', return_value={'homepage_url': 'https://example.com/', 'company_name': 'Fixture', 'domain': 'example.com', 'company_id': 7})
    @patch('app.main.db')
    @patch('app.main.services.search', return_value=[])
    @patch('app.main.services.fetch', return_value={'url': 'https://example.com/', 'title': 'Fixture', 'text': 'We manufacture CNC tooling in Illinois.', 'retrieved_at': 1000})
    @patch('app.main.services.model')
    def test_fabricated_evidence_fails_before_persistence(self, model, fetch, search, db, claim, failed):
        from app.logic import SCORE_LIMITS
        db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {'status': 'ready'}
        model.return_value = dict({key: maximum for key, maximum in SCORE_LIMITS.items()},
            evidence=[{'claim': 'Supports FIRST', 'source_url': 'https://invented.example/', 'excerpt': 'Sponsors FIRST robotics teams'}])
        response = TestClient(app).post('/research', json={'lead_id': 1})
        self.assertEqual(response.status_code, 502)
        failed.assert_called_once()
        self.assertEqual(failed.call_args[0][:2], (1, 'research_failed'))
        # Only the eligibility lookup opened a connection; promotion/evidence writes never ran.
        self.assertEqual(db.call_count, 1)

    @patch('app.services.requests.Session')
    @patch('app.services.public_url', return_value='https://example.com/contact')
    def test_public_contact_href_fields_survive_cleaning(self, public, session):
        response = MagicMock()
        response.is_redirect = False
        response.headers = {'Content-Type': 'text/html'}
        response.iter_content.return_value = [b'<p>Contact Jane Smith, Engineering Manager, about our Illinois machining services.</p><a href="mailto:jane@example.com?subject=Hello">Email Jane</a><a href="https://www.linkedin.com/in/jane-fixture">Profile</a><a href="https://private.example/">Other</a>']
        session.return_value.get.return_value = response
        source = services.fetch('https://example.com/contact')
        self.assertIn('jane@example.com', source['text'])
        self.assertIn('https://www.linkedin.com/in/jane-fixture', source['text'])
        self.assertNotIn('https://private.example/', source['text'])
        session.return_value.close.assert_called_once()

    def test_scout_strict_output_rejects_extra_fields_and_bad_confidence(self):
        data = {'company_name': 'Fixture', 'relevant': True, 'confidence': 1.2,
                'industry': 'CNC', 'local_signal': '', 'reason': 'Fixture'}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(data, schemas.SCOUT)
        data['confidence'] = .8
        data['send_email'] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(data, schemas.SCOUT)


if __name__ == '__main__':
    unittest.main()
