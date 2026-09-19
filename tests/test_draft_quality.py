"""/draft endpoint: retry-on-review, professional style gates, and no cash context."""
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import schemas, services
from app.main import app
from app.logic import SCORE_LIMITS
from tests.test_success_flow import FixtureDatabase

GOOD_DRAFT = dict(
    subject='Learning about your CNC work',
    body="Hello Fixture Manufacturing team,\n\nI'm [Your Name], a student with Example Robotics Team, Team 0000 at Example High School. "
         "I'm reaching out to learn from professionals working in manufacturing and engineering.\n\n"
         "I noticed that your company provides CNC machining services in Illinois. I would be interested in hearing "
         "which technical skills matter most for students preparing for manufacturing careers.\n\n"
         "Would someone on your team be open to a 15-minute conversation?\n\nBest,\n[Your Name]\n"
         "Example Robotics Team | Team 0000\nExample High School",
    linkedin_note="Hello Fixture Manufacturing team, I'm [Your Name], a student with Example Robotics Team. I noticed your CNC machining work and would appreciate the chance to connect and learn from your experience.",
    followup_body="Hello Fixture Manufacturing team,\n\nI'm following up on my earlier message. Would someone on your team be open to a 15-minute conversation about skills students should develop for manufacturing careers?\n\nBest,\n[Your Name]\nExample Robotics Team | Team 0000\nExample High School",
)
BAD_DRAFT = dict(
    subject='Sponsorship request for Example Robotics Team',
    body='Please sponsor us with $2,500 today.',
    linkedin_note='Connect?',
    followup_body='Following up',
)


def researched_lead(database, client):
    source = dict(url='https://example.com/', title='Fixture Manufacturing', text='We manufacture CNC tooling in Illinois and mentor students.', retrieved_at=1234)
    scout = dict(company_name='Fixture Manufacturing', relevant=True, confidence=.9, industry='Manufacturing', local_signal='Illinois', reason='CNC tooling')
    research = dict({key: value for key, value in SCORE_LIMITS.items()}, company_name='Fixture Manufacturing', summary='s',
                     overall_score=0, tier=4, suggested_cash_ask='Invented', in_kind_opportunities=['Machining time'],
                     target_roles=['Engineering Manager'], outreach_angle='Shared interest in STEM education',
                     evidence=[dict(claim='Makes CNC tooling', source_url=source['url'], excerpt='manufacture CNC tooling in Illinois')])
    with patch('app.main.db', database.connect), \
         patch('app.main.services.search', return_value=[dict(url=source['url'], title='Fixture Manufacturing', content='CNC tooling')]), \
         patch('app.main.services.fetch', return_value=source), \
         patch('app.main.services.model', side_effect=[scout, research, {'contacts': []}]):
        client.post('/discover', json={})
        client.post('/research', json={'lead_id': 1})


class DraftQualityTest(unittest.TestCase):
    def test_email_writer_does_not_receive_cash_planning_context(self):
        response = unittest.mock.MagicMock()
        response.json.return_value = {'message': {'content': json.dumps(GOOD_DRAFT)}}
        with patch('app.services.requests.post', return_value=response) as post:
            services._model('email-writer', {'company_name': 'Fixture'}, schemas.DRAFT)
        system_message = post.call_args.kwargs['json']['messages'][0]['content']
        self.assertNotIn('Typical cash planning ranges', system_message)
        self.assertNotIn('$2,500', system_message)
        self.assertIn('first time', system_message)

    def test_retries_once_and_succeeds_on_second_attempt(self):
        database = FixtureDatabase()
        client = TestClient(app)
        researched_lead(database, client)
        with patch('app.main.db', database.connect), patch('app.main.services.model', side_effect=[BAD_DRAFT, GOOD_DRAFT]) as model:
            response = client.post('/draft', json={'lead_id': 1})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['draft_warnings'], [])
        self.assertEqual(model.call_count, 2)
        self.assertIn('revision_notes', model.call_args_list[1][0][1])
        self.assertEqual(database.draft['subject'], GOOD_DRAFT['subject'])

    def test_second_revision_carries_forward_all_prior_problems(self):
        database = FixtureDatabase()
        client = TestClient(app)
        researched_lead(database, client)
        new_problem = dict(GOOD_DRAFT, subject='A' * 56)
        with patch('app.main.db', database.connect), patch(
            'app.main.services.model', side_effect=[BAD_DRAFT, new_problem, GOOD_DRAFT]
        ) as model:
            response = client.post('/draft', json={'lead_id': 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(model.call_count, 3)
        final_notes = model.call_args_list[2][0][1]['revision_notes']
        self.assertIn('subject is longer than 55 characters', final_notes)
        self.assertIn('body is missing the [Your Name] signature', final_notes)

    def test_rejects_without_persisting_when_all_three_attempts_fail(self):
        database = FixtureDatabase()
        client = TestClient(app)
        researched_lead(database, client)
        with patch('app.main.db', database.connect), patch('app.main.services.model', side_effect=[BAD_DRAFT, BAD_DRAFT, BAD_DRAFT]) as model:
            response = client.post('/draft', json={'lead_id': 1})
        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(model.call_count, 3)
        self.assertIsNone(database.draft)
        self.assertEqual(database.lead['status'], 'draft_failed')
        self.assertIn('Draft rejected after two revisions', database.lead['last_error'])

    def test_draft_payload_has_no_cash_ask_and_has_outreach_angle(self):
        database = FixtureDatabase()
        client = TestClient(app)
        researched_lead(database, client)
        with patch('app.main.db', database.connect), patch('app.main.services.model', side_effect=[GOOD_DRAFT]) as model:
            response = client.post('/draft', json={'lead_id': 1})
        self.assertEqual(response.status_code, 200, response.text)
        payload = model.call_args_list[0][0][1]
        self.assertNotIn('suggested_cash_ask', payload)
        self.assertEqual(payload['outreach_angle'], 'Shared interest in STEM education')
        self.assertEqual(payload['in_kind_opportunities'], ['Machining time'])


if __name__ == '__main__':
    unittest.main()
