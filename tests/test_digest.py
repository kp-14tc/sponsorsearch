import unittest
from datetime import date
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.digest import format_digest, format_draft, DISPLAY_LIMIT
from app.logic import daily_queries


RULES = ('Already contacted', [('Blocked', ['blocked'], {'blocked.com'})])


def row(index, name='Fixture', domain='example.com'):
    return dict(lead_id=index, company_name=name, domain=domain, status='researched', overall_score=80, tier=2, draft_exists=False, source_urls=['https://example.com/evidence'])


class DigestTests(unittest.TestCase):
    def test_daily_query_rotation_wraps_and_is_deterministic(self):
        queries = ['first', 'second', 'third']
        day = date.fromordinal(5)
        self.assertEqual(daily_queries(queries, day, 3), ['third', 'first', 'second'])
        self.assertEqual(daily_queries(queries, date.fromordinal(6), 1), ['first'])
        self.assertEqual(daily_queries([], day, 3), [])
        self.assertEqual(daily_queries(['only'], day, 3), ['only'])

    def test_discovery_daily_rotation_and_explicit_query_override(self):
        with patch('app.main.exclusions.load_exclusions', return_value=RULES), patch('app.main.services.search', return_value=[]) as search, patch('app.main.ZoneInfo'), patch('app.main.datetime') as clock:
            clock.now.return_value.date.return_value = date.fromordinal(5)
            response = TestClient(app).post('/discover', json={'rotate_daily': True, 'query_limit': 3, 'query_offset': 999999})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()['queries']), 3)
            self.assertEqual(search.call_count, 3)
            override = TestClient(app).post('/discover', json={'rotate_daily': True, 'query': 'Explicit override'})
            self.assertEqual(override.json()['queries'], ['Explicit override'])
            unchanged = TestClient(app).post('/discover', json={'query_offset': 999999})
            self.assertEqual(unchanged.json()['queries'], [])

    def test_empty_queue_and_plain_text_persisted_fields(self):
        self.assertIn('No qualifying leads ready', format_digest([], RULES)['text'])
        result = format_digest([row(1, '<script>malicious</script>\nInjected')], RULES)
        self.assertIn('<script>malicious</script> Injected', result['text'])
        self.assertIn('https://example.com/evidence', result['text'])
        self.assertIn('not created', result['text'])
        self.assertEqual(set(result), {'title', 'text', 'messages', 'lead_count', 'truncated'})
        self.assertEqual(result['messages'], [{'part': 1, 'parts': 1, 'text': result['text']}])

    def test_long_queue_splits_into_sendable_telegram_parts(self):
        result = format_digest([row(i, 'Fixture ' + str(i)) for i in range(DISPLAY_LIMIT)], RULES)
        messages = result['messages']
        self.assertGreater(len(messages), 1)
        self.assertEqual([message['part'] for message in messages], list(range(1, len(messages) + 1)))
        self.assertEqual({message['parts'] for message in messages}, {len(messages)})
        for message in messages:
            self.assertLessEqual(len(message['text']), 4096)
            self.assertTrue(message['text'].endswith('(' + str(message['part']) + '/' + str(len(messages)) + ')'))
        rejoined = '\n'.join(message['text'].rsplit('\n\n(', 1)[0] for message in messages)
        self.assertEqual(rejoined, result['text'])

    def test_single_line_longer_than_the_transport_limit_is_marked_truncated(self):
        result = format_digest([dict(row(1), source_urls=['https://example.com/' + 'x' * 5000])], RULES)
        self.assertNotIn('…', result['text'])
        self.assertTrue(any('…' in message['text'] for message in result['messages']))
        for message in result['messages']:
            self.assertLessEqual(len(message['text']), 4096)

    def test_exclusions_do_not_consume_display_limit_and_scan_is_disclosed(self):
        rows = [row(i, 'Blocked', 'blocked.com') for i in range(30)] + [row(i) for i in range(30, 56)]
        result = format_digest(rows, RULES)
        self.assertEqual(result['lead_count'], 25)
        self.assertTrue(result['truncated'])
        self.assertNotIn('blocked.com', result['text'])
        self.assertIn('latest 56 checked', result['text'])
        self.assertTrue(format_digest([row(i, 'Blocked', 'blocked.com') for i in range(200)], RULES)['truncated'])

    def test_endpoint_read_only_bounded_durable_query(self):
        with patch('app.main.exclusions.load_exclusions', return_value=RULES), patch('app.main.db') as db, patch('app.main.services.model') as model:
            connection = db.return_value.__enter__.return_value
            connection.execute.return_value.fetchall.return_value = [dict(row(7), draft_exists=True)]
            response = TestClient(app).get('/digest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['lead_count'], 1)
        self.assertIn('pending human approval', response.json()['text'])
        query = connection.execute.call_args.args[0]
        self.assertIn('LIMIT 200', query)
        self.assertIn('NOT d.approved', query)
        self.assertIn('l.overall_score>=70', query)
        self.assertNotIn('contacts', query)
        self.assertNotIn('interval', query)
        self.assertTrue(query.startswith('SELECT'))
        model.assert_not_called()

    def test_saved_draft_is_complete_and_split_for_telegram(self):
        saved = {
            'lead_id': 8, 'draft_id': 2, 'company_name': 'Fixture', 'domain': 'example.com',
            'subject': 'Sponsorship idea', 'body': 'A' * 7001,
            'linkedin_note': 'Short note', 'followup_body': 'Follow up', 'approved': False,
        }
        result = format_draft(saved)
        self.assertIn('Subject:\nSponsorship idea', result['text'])
        self.assertIn('Email body:', result['text'])
        self.assertEqual(result['text'].count('A'), 7001)
        self.assertGreater(len(result['messages']), 1)
        self.assertTrue(all(len(message['text']) <= 4096 for message in result['messages']))
        self.assertIn('was not sent to the company', result['text'])

    def test_saved_draft_reports_actual_approval_state(self):
        saved = {
            'lead_id': 8, 'draft_id': 2, 'company_name': 'Fixture', 'domain': 'example.com',
            'subject': 'Subject', 'body': 'Body', 'linkedin_note': 'Note',
            'followup_body': 'Follow up', 'approved': True,
        }
        result = format_draft(saved)
        self.assertIn('approved by a human reviewer', result['text'])
        self.assertNotIn('pending human approval', result['text'])

    def test_saved_draft_endpoint_reads_persisted_content_only(self):
        saved = {
            'lead_id': 8, 'draft_id': 2, 'company_name': 'Fixture', 'domain': 'example.com',
            'subject': 'Saved subject', 'body': 'Saved body', 'linkedin_note': 'Saved note',
            'followup_body': 'Saved follow-up', 'approved': False,
        }
        with patch('app.main.db') as db, patch('app.main.guard_exclusion') as guard, patch('app.main.services.model') as model:
            connection = db.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = saved
            response = TestClient(app).get('/telegram-drafts/8')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Saved subject', response.json()['text'])
        self.assertIn('Saved body', response.json()['text'])
        self.assertIn('JOIN email_drafts', connection.execute.call_args.args[0])
        guard.assert_called_once_with(saved)
        model.assert_not_called()

    def test_invalid_configuration_blocks_before_database(self):
        with patch('app.main.exclusions.load_exclusions', side_effect=RuntimeError('invalid config')), patch('app.main.db') as db:
            with self.assertRaises(RuntimeError):
                TestClient(app).get('/digest')
        db.assert_not_called()
