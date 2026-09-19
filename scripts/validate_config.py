"""Static checks; Docker validation runs when the CLI is available."""
import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    for path in list((ROOT / 'config').rglob('*.json')) + list((ROOT / 'n8n').rglob('*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if 'workflows' in path.parts:
                nodes = data['nodes']
                assert nodes and data['active'] is False
                names = {node['name'] for node in nodes}
                for name, edges in data['connections'].items():
                    assert name in names
                    for branches in edges.values():
                        for branch in branches:
                            for edge in branch:
                                assert edge['node'] in names
                for node in nodes:
                    assert node['type'] != 'n8n-nodes-base.emailSend', 'SMTP sending is not supported'
                    assert node['type'] != 'n8n-nodes-base.gmail', 'Owner digest delivery is Telegram, not Gmail'
                    if node['type'] == 'n8n-nodes-base.telegram':
                        # User authorized an owner digest, never sponsor outreach.
                        assert path.name == '05-daily-lead-summary.json'
                        parameters = node['parameters']
                        assert node['name'] == 'Send owner digest'
                        assert parameters['resource'] == 'message' and parameters['operation'] == 'sendMessage'
                        # A literal chat ID: lead data must never steer the destination.
                        assert isinstance(parameters['chatId'], str) and parameters['chatId'].strip()
                        assert not parameters['chatId'].startswith('=')
                        assert parameters['text'] == "={{ $json.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }}"
                        assert parameters['additionalFields']['appendAttribution'] is False
                        assert parameters['additionalFields']['parse_mode'] == 'HTML'
                    if path.name == '05-daily-lead-summary.json' and node['name'] == 'Read daily summary':
                        assert "http://worker:8000/telegram-drafts/" in node['parameters']['url']
                        assert "http://worker:8000/digest" in node['parameters']['url']
                    if path.name == '06-telegram-commands.json' and node['name'] == 'Poll Telegram':
                        assert node['type'] == 'n8n-nodes-base.httpRequest'
                        assert node['parameters']['method'] == 'GET'
                        assert node['parameters']['url'] == "={{ 'https://api.telegram.org/bot' + $env.TELEGRAM_BOT_TOKEN + '/getUpdates' }}"
                        assert not node.get('credentials')
                    if path.name == '06-telegram-commands.json' and node['name'] == 'Read durable cursor':
                        assert node['type'] == 'n8n-nodes-base.httpRequest'
                        assert node['parameters']['url'] == 'http://worker:8000/telegram-commands/cursor'
                    if path.name == '06-telegram-commands.json' and node['name'] == 'Ingest Telegram updates':
                        assert node['type'] == 'n8n-nodes-base.httpRequest'
                        assert node['parameters']['method'] == 'POST'
                        assert node['parameters']['url'] == 'http://worker:8000/telegram-commands/intake'
                    if path.name == '06-telegram-commands.json' and node['name'] == 'Include saved draft':
                        assert 'include_draft: true' in node['parameters']['jsCode']
        except Exception as exc:
            errors.append(str(path.relative_to(ROOT)) + ': ' + str(exc))
    for folder in ['app', 'scripts', 'tests']:
        for path in (ROOT / folder).rglob('*.py'):
            try:
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            except SyntaxError as exc:
                errors.append(str(path.relative_to(ROOT)) + ': ' + str(exc))
    try:
        locations = json.loads((ROOT / 'config/locations.json').read_text(encoding='utf-8'))
        queries = json.loads((ROOT / 'config/search-query-templates.json').read_text(encoding='utf-8'))
        assert locations and all(isinstance(x, str) and x for x in locations)
        assert queries['discovery'] and queries['research']
        for query in queries['discovery']:
            query.format(location=locations[0])
        for query in queries['research']:
            query.format(company='Example', domain='example.com')
        sql = (ROOT / 'database/schema.sql').read_text(encoding='utf-8')
        assert 'CREATE SCHEMA' in sql.upper()
        for table in ['companies', 'leads', 'evidence', 'contacts', 'email_drafts', 'telegram_commands', 'telegram_poll_state']:
            assert table in sql
        for prompt in ['team-context', 'email-team-context', 'scout', 'researcher', 'contact-researcher', 'email-writer']:
            assert (ROOT / ('prompts/' + prompt + '.md')).read_text(encoding='utf-8').strip()
        try:
            import yaml
            compose = yaml.safe_load((ROOT / 'compose.yml').read_text(encoding='utf-8'))
            assert {'postgres', 'n8n', 'searxng', 'worker'} <= set(compose['services'])
            assert not compose['services']['postgres'].get('ports')
            assert not compose['services']['worker'].get('ports')
            print('PASS: YAML parses; internal service port checks')
        except ImportError:
            print('NOT AVAILABLE: install requirements-dev.txt for YAML parsing')
    except Exception as exc:
        errors.append('Project consistency: ' + str(exc))
    if shutil.which('docker'):
        result = subprocess.run(['docker', 'compose', '--env-file', '.env.example', 'config', '--quiet'], cwd=ROOT)
        if result.returncode:
            errors.append('Docker Compose validation failed')
    else:
        print('NOT AVAILABLE: Docker Compose CLI')
    for error in errors:
        print('FAIL: ' + error)
    if not errors:
        print('PASS: JSON, Python syntax, config, prompts, SQL structure, workflow links')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
