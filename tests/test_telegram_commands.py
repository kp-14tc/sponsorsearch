import os
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.main import app, parse_telegram_update


class TelegramCommandTests(unittest.TestCase):
    def test_update_parser_requires_exact_owner_and_command_shape(self):
        update = {
            'update_id': 12,
            'message': {'message_id': 3, 'chat': {'id': 12345}, 'from': {'id': 12345}, 'text': '/search   local   robotics'},
        }
        self.assertEqual(parse_telegram_update(update, '12345')['query'], 'local robotics')
        update['message']['from']['id'] = 999
        self.assertIsNone(parse_telegram_update(update, '12345'))

    def test_empty_first_intake_initializes_durable_cursor(self):
        state_result = Mock()
        state_result.fetchone.return_value = {'next_offset': -1, 'initialized': False}
        with patch.dict(os.environ, {'TELEGRAM_OWNER_CHAT_ID': '12345'}), patch('app.main.db') as db:
            connection = db.return_value.__enter__.return_value
            connection.execute.side_effect = [state_result, Mock()]
            response = TestClient(app).post('/telegram-commands/intake', json={'updates': []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'commands': [], 'next_offset': 0})
        self.assertIn('initialized=true', connection.execute.call_args_list[1].args[0])

    def test_initialized_intake_claims_status_and_advances(self):
        state_result = Mock()
        state_result.fetchone.return_value = {'next_offset': 10, 'initialized': True}
        insert_result = Mock()
        insert_result.fetchone.return_value = {'update_id': 12}
        update = {
            'update_id': 12,
            'message': {'message_id': 3, 'chat': {'id': 12345}, 'from': {'id': 12345}, 'text': '/status'},
        }
        with patch.dict(os.environ, {'TELEGRAM_OWNER_CHAT_ID': '12345'}), patch('app.main.db') as db:
            connection = db.return_value.__enter__.return_value
            connection.execute.side_effect = [state_result, Mock(), insert_result]
            response = TestClient(app).post('/telegram-commands/intake', json={'updates': [update]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['next_offset'], 13)
        self.assertEqual(response.json()['commands'][0]['command'], 'status')

    def test_overlapping_initial_poll_cannot_execute_update_below_cursor(self):
        state_result = Mock()
        state_result.fetchone.return_value = {'next_offset': 13, 'initialized': True}
        stale_update = {
            'update_id': 12,
            'message': {'message_id': 3, 'chat': {'id': 12345}, 'from': {'id': 12345}, 'text': '/draft 8'},
        }
        with patch.dict(os.environ, {'TELEGRAM_OWNER_CHAT_ID': '12345'}), patch('app.main.db') as db:
            connection = db.return_value.__enter__.return_value
            connection.execute.side_effect = [state_result, Mock()]
            response = TestClient(app).post('/telegram-commands/intake', json={'updates': [stale_update]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'commands': [], 'next_offset': 13})
        self.assertEqual(connection.execute.call_count, 2)

    def test_owner_command_is_claimed_once(self):
        with patch.dict(os.environ, {'TELEGRAM_OWNER_CHAT_ID': '12345'}), patch('app.main.db') as db:
            connection = db.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.side_effect = [{'update_id': 9}, None]
            payload = {'update_id': 9, 'message_id': 4, 'chat_id': 12345, 'command': 'search', 'query': '  local   robotics  '}
            first = TestClient(app).post('/telegram-commands/claim', json=payload)
            second = TestClient(app).post('/telegram-commands/claim', json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['accepted'])
        self.assertEqual(first.json()['query'], 'local robotics')
        self.assertFalse(second.json()['accepted'])

    def test_wrong_or_unconfigured_chat_is_rejected_before_database(self):
        payload = {'update_id': 1, 'message_id': 1, 'chat_id': 999, 'command': 'status'}
        for configured in ('', '12345'):
            with self.subTest(configured=configured), patch.dict(os.environ, {'TELEGRAM_OWNER_CHAT_ID': configured}), patch('app.main.db') as db:
                response = TestClient(app).post('/telegram-commands/claim', json=payload)
                self.assertEqual(response.status_code, 403)
                db.assert_not_called()

    def test_command_arguments_are_bounded_by_type(self):
        base = {'update_id': 1, 'message_id': 1, 'chat_id': 12345}
        cases = [
            ({**base, 'command': 'draft'}, 422),
            ({**base, 'command': 'status', 'lead_id': 1}, 422),
            ({**base, 'command': 'draft', 'lead_id': 1, 'query': 'x'}, 422),
            ({**base, 'command': 'delete'}, 422),
        ]
        with patch.dict(os.environ, {'TELEGRAM_OWNER_CHAT_ID': '12345'}), patch('app.main.db') as db:
            for payload, status in cases:
                with self.subTest(payload=payload):
                    self.assertEqual(TestClient(app).post('/telegram-commands/claim', json=payload).status_code, status)
            db.assert_not_called()


if __name__ == '__main__':
    unittest.main()
