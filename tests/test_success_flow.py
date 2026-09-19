"""Pipeline fixture checks SQL call contracts, not PostgreSQL execution."""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.logic import SCORE_LIMITS


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FixtureDatabase:
    def __init__(self):
        self.company = None
        self.lead = None
        self.evidence = []
        self.draft = None

    @contextmanager
    def connect(self):
        yield self

    def execute(self, sql, args=()):
        if sql.startswith('INSERT INTO companies'):
            if self.company:
                return Cursor([])
            self.company = dict(id=7, domain=args[0], company_name=args[1], homepage_url=args[2], industry='')
            return Cursor([{'id': 7}])
        if sql.startswith('INSERT INTO leads'):
            self.lead = dict(id=1, company_id=7, status='discovered', overall_score=None)
            return Cursor([{'id': 1}])
        if sql.startswith('SELECT l.id,l.status'):
            return Cursor([{**self.lead, 'company_name': self.company['company_name'], 'domain': self.company['domain']}])
        if sql.startswith('SELECT l.*,'):
            return Cursor([{**self.lead, **{key: value for key, value in self.company.items() if key != 'id'}}])
        if sql.startswith('UPDATE companies'):
            self.company.update(company_name=args[0], industry=args[1], location=args[2])
        elif sql.startswith('UPDATE leads SET status=%s, attempts'):
            if self.lead['status'] != args[2]:
                return Cursor([])
            self.lead['status'] = args[0]
            return Cursor([{'id': 1}])
        elif sql.startswith('UPDATE leads SET scout_relevance'):
            self.lead.update(scout_relevance=args[0], scout_confidence=args[1], scout_reason=args[2], status=args[3])
        elif sql.startswith('UPDATE leads SET geographic_fit'):
            self.lead.update(dict(zip(SCORE_LIMITS, args[:7])))
            self.lead.update(research_summary=args[7], overall_score=args[8], tier=args[9], suggested_cash_ask=args[10], in_kind_opportunities=args[11].obj, outreach_angle=args[13], status='researched')
        elif sql.startswith('UPDATE leads SET last_error='):
            self.lead['last_error'] = args[0]
        elif sql.startswith('UPDATE leads SET status=%s,last_error=%s'):
            self.lead.update(status=args[0], last_error=args[1])
        elif sql.startswith('DELETE FROM evidence'):
            self.evidence.clear()
        elif sql.startswith('INSERT INTO evidence'):
            self.evidence.append(dict(lead_id=args[0], company_id=args[1], claim=args[2], source_url=args[3], source_title=args[4], excerpt=args[5], retrieved_at=args[6]))
        elif sql.startswith('SELECT * FROM evidence'):
            return Cursor(list(self.evidence))
        elif sql.startswith('SELECT * FROM contacts') or sql.startswith('DELETE FROM contacts'):
            return Cursor([])
        elif sql.startswith('INSERT INTO email_drafts'):
            self.draft = dict(id=9, lead_id=args[0], subject=args[1], body=args[2], linkedin_note=args[3], followup_body=args[4], approved=False, draft_status='needs_review')
            return Cursor([{'id': 9}])
        elif sql.startswith("UPDATE leads SET status='needs_review'"):
            self.lead['status'] = 'needs_review'
        elif sql.startswith('SELECT * FROM email_drafts') or sql.startswith('SELECT id,approved FROM email_drafts'):
            return Cursor([dict(self.draft)] if self.draft else [])
        elif sql.startswith('UPDATE email_drafts SET approved=true'):
            self.draft.update(approved=True, approved_by=args[0], draft_status='approved')
            return Cursor([dict(self.draft)])
        elif sql.startswith('SELECT c.domain,c.company_name FROM email_drafts'):
            return Cursor([dict(self.company)] if self.draft else [])
        else:
            raise AssertionError('Unexpected SQL contract: ' + sql)
        return Cursor([])


class SuccessFlowTest(unittest.TestCase):
    def test_discover_research_draft_review_and_retries(self):
        database = FixtureDatabase()
        client = TestClient(app)
        source = dict(url='https://example.com/', title='Fixture Manufacturing', text='We manufacture CNC tooling in Illinois and mentor students.', retrieved_at=1234)
        scout = dict(company_name='Fixture Manufacturing', relevant=True, confidence=.9, industry='Manufacturing', local_signal='Illinois', reason='CNC tooling')
        research = dict({key: value for key, value in SCORE_LIMITS.items()}, company_name='Fixture Manufacturing', summary='Uncited model summary must be discarded', overall_score=0, tier=4, suggested_cash_ask='Invented', in_kind_opportunities=['Machining'], target_roles=['Engineering Manager'], outreach_angle='Education partnership', evidence=[dict(claim='Makes CNC tooling', source_url=source['url'], excerpt='manufacture CNC tooling in Illinois')])
        draft = dict(subject='Learning about your CNC work', body='Hello Fixture Manufacturing team,\n\nI am [Your Name], a student with Example Robotics Team. I noticed your CNC work and would value a short conversation about skills students should develop.\n\nWould someone on your team be open to a 15-minute call?\n\nBest,\n[Your Name]\nExample Robotics Team | Team 0000\nExample High School', linkedin_note='Hello Fixture Manufacturing team, I am [Your Name] with Example Robotics Team. I would appreciate the chance to connect and learn about your work.', followup_body='Hello Fixture Manufacturing team,\n\nI am following up on my earlier message. Would someone on your team be open to a 15-minute conversation?\n\nBest,\n[Your Name]\nExample Robotics Team | Team 0000\nExample High School')
        with patch('app.main.db', database.connect), patch('app.main.services.search', return_value=[dict(url=source['url'], title='Fixture Manufacturing', content='CNC tooling')]), patch('app.main.services.fetch', return_value=source), patch('app.main.services.model', side_effect=[scout, research, {'contacts': []}, draft]) as model:
            discovered = client.post('/discover', json={}).json()
            self.assertEqual(discovered['leads'][0]['lead_id'], 1)
            researched = client.post('/research', json={'lead_id': 1})
            self.assertEqual(researched.status_code, 200, researched.text)
            self.assertEqual(researched.json()['overall_score'], 100)
            self.assertEqual(database.evidence[0]['retrieved_at'], 1234)
            self.assertNotIn('Uncited', database.lead['research_summary'])
            drafted = client.post('/draft', json={'lead_id': 1})
            self.assertEqual(drafted.status_code, 200, drafted.text)
            self.assertFalse(database.draft['approved'])
            self.assertEqual(client.post('/draft', json={'lead_id': 1}).json()['draft_id'], 9)
            self.assertTrue(client.post('/research', json={'lead_id': 1}).json()['qualified'])
            self.assertEqual(model.call_count, 4)
            approved = client.post('/drafts/9/approve', json={'approved_by': 'Student reviewer'})
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertTrue(database.draft['approved'])
            self.assertEqual(database.draft['approved_by'], 'Student reviewer')
            review = client.get('/leads/1').json()
            self.assertEqual(review['drafts'][0]['body'], draft['body'])
            self.assertEqual(len(review['evidence']), 1)


if __name__ == '__main__':
    unittest.main()
