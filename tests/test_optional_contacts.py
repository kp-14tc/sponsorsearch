import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.logic import SCORE_LIMITS, filter_contacts, validate_contacts
from app.main import app
from tests.test_success_flow import FixtureDatabase


class OptionalContactTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(url='https://example.com/', title='Fixture', text='Jane Smith Engineering Manager email jane@example.com. We manufacture CNC tooling in Illinois.', retrieved_at=1234)
        self.contact = dict(source_url=self.source['url'], excerpt='Jane Smith Engineering Manager', name='Jane Smith', title='Engineering Manager', email='jane@example.com', public_profile_url='', confidence=.8)

    def test_mixed_contacts_discard_entire_unsupported_entry(self):
        changes = [dict(name='Invented Person'), dict(email='guessed@example.com'), dict(title='CEO'), dict(excerpt='This excerpt was invented'), dict(source_url='https://invented.com/'), dict(public_profile_url='https://linkedin.com/in/invented')]
        invalid = [dict(self.contact, **change) for change in changes]
        contacts = [self.contact] + invalid
        accepted, warnings = filter_contacts(contacts, {self.source['url']: self.source})
        self.assertEqual(accepted, [self.contact])
        self.assertEqual([warning['contact_index'] for warning in warnings], list(range(1, 7)))
        self.assertTrue(all(warning['reason'] for warning in warnings))
        self.assertEqual(contacts, [self.contact] + invalid)
        for contact in invalid:
            with self.assertRaises(ValueError):
                validate_contacts([contact], {self.source['url']: self.source})

    def test_absent_optional_fields_can_stay_empty(self):
        contact = dict(self.contact, name='', title='', email='', public_profile_url='')
        self.assertEqual(filter_contacts([contact], {self.source['url']: self.source}), ([contact], []))

    def test_valid_research_persists_when_optional_contact_is_rejected(self):
        database = FixtureDatabase()
        database.company = dict(id=7, domain='example.com', company_name='Fixture', homepage_url=self.source['url'], industry='CNC')
        database.lead = dict(id=1, company_id=7, status='ready', overall_score=None)
        research = dict({key: value for key, value in SCORE_LIMITS.items()}, in_kind_opportunities=[], target_roles=['CEO'], outreach_angle='Education', evidence=[dict(claim='Makes tooling', source_url=self.source['url'], excerpt='manufacture CNC tooling in Illinois')])
        with patch('app.main.db', database.connect), patch('app.main.services.search', return_value=[]), patch('app.main.services.fetch', return_value=self.source), patch('app.main.services.model', side_effect=[research, {'contacts': [dict(self.contact, title='CEO')]}]):
            response = TestClient(app).post('/research', json={'lead_id': 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(database.lead['status'], 'researched')
        self.assertEqual(len(database.evidence), 1)
        self.assertEqual(response.json()['contact_warnings'], [{'contact_index': 0, 'reason': 'Contact field absent from source: title'}])
        self.assertIn('Contact field absent from source: title', database.lead['last_error'])
        # FixtureDatabase rejects unexpected SQL, including INSERT INTO contacts.
