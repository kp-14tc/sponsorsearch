"""/draft force=True: regenerate a stored draft, except when it is already approved."""
import unittest
from unittest.mock import MagicMock, Mock, patch

from fastapi.testclient import TestClient
from app.main import app
from tests.test_success_flow import FixtureDatabase
from tests.test_draft_quality import researched_lead, GOOD_DRAFT

REDRAFT = dict(
    subject='A different note about your CNC work',
    body="Hello Fixture team,\n\nI'm [Your Name], a student with Example Robotics Team, Team 0000 at Example High School.\n\nI noticed your CNC work and would be interested in learning which technical skills matter most in your field.\n\nWould someone on your team be open to a 15-minute conversation?\n\nBest,\n[Your Name]\nExample Robotics Team | Team 0000\nExample High School",
    linkedin_note="Hello Fixture team, I'm [Your Name] with Example Robotics Team. I noticed your CNC work and would appreciate the chance to connect and learn from your experience.",
    followup_body="Hello Fixture team,\n\nI'm following up on my earlier message. Would someone on your team be open to a 15-minute conversation about CNC careers?\n\nBest,\n[Your Name]\nExample Robotics Team | Team 0000\nExample High School",
)


class ForceRedraftTest(unittest.TestCase):
    def test_force_false_on_drafted_lead_returns_stored_draft_and_skips_model(self):
        database = FixtureDatabase()
        client = TestClient(app)
        researched_lead(database, client)
        with patch('app.main.db', database.connect), patch('app.main.services.model', side_effect=[GOOD_DRAFT]):
            client.post('/draft', json={'lead_id': 1})
        with patch('app.main.db', database.connect), patch('app.main.services.model') as model:
            response = client.post('/draft', json={'lead_id': 1, 'force': False})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['draft_id'], database.draft['id'])
        self.assertEqual(database.draft['subject'], GOOD_DRAFT['subject'])
        model.assert_not_called()

    def test_force_true_on_unapproved_draft_regenerates_and_overwrites(self):
        database = FixtureDatabase()
        client = TestClient(app)
        researched_lead(database, client)
        with patch('app.main.db', database.connect), patch('app.main.services.model', side_effect=[GOOD_DRAFT]):
            client.post('/draft', json={'lead_id': 1})
        with patch('app.main.db', database.connect), patch('app.main.services.model', side_effect=[REDRAFT]) as model:
            response = client.post('/draft', json={'lead_id': 1, 'force': True})
        self.assertEqual(response.status_code, 200, response.text)
        model.assert_called_once()
        self.assertEqual(database.draft['subject'], REDRAFT['subject'])
        self.assertFalse(database.draft['approved'])

    def test_force_true_on_approved_draft_is_refused(self):
        database = FixtureDatabase()
        client = TestClient(app)
        researched_lead(database, client)
        with patch('app.main.db', database.connect), patch('app.main.services.model', side_effect=[GOOD_DRAFT]):
            drafted = client.post('/draft', json={'lead_id': 1}).json()
        with patch('app.main.db', database.connect):
            approved = client.post('/drafts/%s/approve' % drafted['draft_id'], json={'approved_by': 'Mentor'})
        self.assertEqual(approved.status_code, 200, approved.text)
        with patch('app.main.db', database.connect), patch('app.main.services.model') as model:
            response = client.post('/draft', json={'lead_id': 1, 'force': True})
        self.assertEqual(response.status_code, 409)
        model.assert_not_called()
        self.assertEqual(database.draft['subject'], GOOD_DRAFT['subject'])

    def test_concurrent_approval_restores_lead_status_before_conflict(self):
        existing = type('Result', (), {'fetchone': lambda self: {'id': 9, 'approved': False}})()
        lost_update = type('Result', (), {'fetchone': lambda self: None})()
        connection = Mock()
        connection.execute.side_effect = [existing, lost_update, Mock()]
        database = MagicMock()
        database.return_value.__enter__.return_value = connection
        lead_row = {'id': 1, 'status': 'needs_review', 'overall_score': 90, 'domain': 'example.com', 'company_name': 'Fixture'}
        detail = {**lead_row, 'evidence': [], 'contacts': [], 'outreach_angle': '', 'in_kind_opportunities': [], 'research_summary': ''}
        with patch('app.main.db', database), patch('app.main.lead', return_value=lead_row), \
             patch('app.main.claim'), patch('app.main.get_lead', return_value=detail), \
             patch('app.main.services.model', return_value=GOOD_DRAFT):
            response = TestClient(app).post('/draft', json={'lead_id': 1, 'force': True})
        self.assertEqual(response.status_code, 409)
        self.assertIn("status='needs_review'", connection.execute.call_args_list[2].args[0])
        self.assertTrue(all(call.args[0] is None for call in database.return_value.__exit__.call_args_list))

    @patch('app.main.db')
    def test_force_true_still_blocked_below_score_threshold(self, db):
        db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {'overall_score': 69, 'status': 'researched'}
        with patch('app.main.services.model') as model:
            response = TestClient(app).post('/draft', json={'lead_id': 1, 'force': True})
        self.assertEqual(response.status_code, 409)
        model.assert_not_called()

    @patch('app.main.exclusions.blocked_reason', return_value='Excluded: Fixture Co')
    @patch('app.main.db')
    def test_force_true_still_blocked_by_exclusion_guard(self, db, blocked_reason):
        db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {
            'overall_score': 90, 'status': 'researched', 'domain': 'excluded.example', 'company_name': 'Fixture Co'}
        with patch('app.main.services.model') as model:
            response = TestClient(app).post('/draft', json={'lead_id': 1, 'force': True})
        self.assertEqual(response.status_code, 409)
        model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
