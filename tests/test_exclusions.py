import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import exclusions
from app.main import app
from tests.test_success_flow import FixtureDatabase


class IMTSConfigTests(unittest.TestCase):
    def test_all_listed_companies_aliases_and_domains_are_blocked(self):
        rules = exclusions.load_exclusions()
        data = json.loads(exclusions.CONFIG.read_text(encoding='utf-8'))
        self.assertEqual(len(data['companies']), 23)
        for company in data['companies']:
            for name in [company['name']] + company['aliases']:
                with self.subTest(name=name):
                    self.assertIn('Already contacted at IMTS', exclusions.blocked_reason(name=name.swapcase(), rules=rules))
            for domain in company['domains']:
                with self.subTest(domain=domain):
                    self.assertTrue(exclusions.blocked_reason('https://shop.' + domain + '/catalog', rules=rules))
        for name in ('Hexagon Precision Machine Shop', 'SMC Local Fabrication', 'Kennametallic Workshop'):
            with self.subTest(unrelated=name):
                self.assertIsNone(exclusions.blocked_reason(name=name, rules=rules))


class ExclusionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'excluded.json'
        self.path.write_text(json.dumps({'reason': 'Already contacted at IMTS', 'companies': [
            {'name': 'Acme Machine', 'aliases': ['ACME Tooling'], 'domains': ['acme.com']}
        ]}))
        self.patch = patch.object(exclusions, 'CONFIG', self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temp.cleanup)

    def test_normalization_and_word_boundaries(self):
        self.assertTrue(exclusions.blocked_reason('https://shop.acme.com/catalog'))
        self.assertTrue(exclusions.blocked_reason(name='Welcome to ACME-Tooling!'))
        self.assertFalse(exclusions.blocked_reason(name='Acme Toolinghouse'))
        self.assertFalse(exclusions.blocked_reason(name='Macroacme Machine'))
        self.assertFalse(exclusions.blocked_reason('acme-other.com', 'Other Machine'))

    def test_missing_or_malformed_configuration_fails_closed(self):
        for content in ('{}', '{', '{"reason":"x","companies":[{"name":"Acme","aliases":[],"domains":["localhost"]}]}'):
            self.path.write_text(content)
            with self.assertRaises(RuntimeError):
                exclusions.load_exclusions()
        self.path.unlink()
        with self.assertRaises(RuntimeError):
            exclusions.load_exclusions()

    def test_excluded_result_never_opens_database_or_calls_model(self):
        for result in ({'url': 'https://shop.acme.com', 'title': 'Catalog'}, {'url': 'https://other.com', 'title': 'ACME Tooling | Home'}):
            with patch('app.main.services.search', return_value=[result]), patch('app.main.db') as db, patch('app.main.services.model') as model:
                response = TestClient(app).post('/discover', json={})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()['excluded']), 1)
            db.assert_not_called()
            model.assert_not_called()

    def test_scout_alias_excluded_before_ready_and_retry(self):
        database = FixtureDatabase()
        scout = dict(company_name='ACME Tooling', relevant=True, confidence=.9, industry='CNC', local_signal='', reason='CNC')
        result = dict(url='https://other.com', title='Other Machine', content='Distributor of ACME Tooling')
        with patch('app.main.db', database.connect), patch('app.main.services.search', return_value=[result]), patch('app.main.services.model', return_value=scout) as model:
            response = TestClient(app).post('/discover', json={}).json()
            self.assertEqual(database.lead['status'], 'skipped')
            self.assertEqual(response['leads'], [])
            self.assertEqual(len(response['excluded']), 1)
            database.lead['status'] = 'ready'
            retry = TestClient(app).post('/discover', json={}).json()
            self.assertEqual(retry['leads'], [])
            self.assertEqual(len(retry['excluded']), 1)
            self.assertEqual(model.call_count, 1)

    def test_existing_stages_and_approval_blocked_without_writes(self):
        for endpoint, status in (('/research', 'ready'), ('/research', 'research_failed'), ('/research', 'needs_review'), ('/draft', 'researched'), ('/draft', 'draft_failed'), ('/draft', 'needs_review'), ('/drafts/9/approve', 'needs_review')):
            with self.subTest(endpoint=endpoint, status=status), patch('app.main.db') as db, patch('app.main.claim') as claim, patch('app.main.services.model') as model:
                connection = db.return_value.__enter__.return_value
                connection.execute.return_value.fetchone.return_value = dict(domain='other.com', company_name='ACME Tooling', status=status, overall_score=90)
                payload = {'approved_by': 'Human'} if 'approve' in endpoint else {'lead_id': 1}
                response = TestClient(app).post(endpoint, json=payload)
                self.assertEqual(response.status_code, 409)
                self.assertIn('Already contacted at IMTS', response.json()['detail'])
                self.assertEqual(connection.execute.call_count, 1)
                claim.assert_not_called()
                model.assert_not_called()
