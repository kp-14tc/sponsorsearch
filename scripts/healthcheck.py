"""Read-only service diagnostics, usable on the host or inside worker."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request(url, data=None, timeout=15):
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def check(name, inside=False, structured=False):
    if name == 'docker':
        if not shutil.which('docker'):
            return 'NOT AVAILABLE', 'Docker CLI absent'
        result = subprocess.run(['docker', 'compose', 'config', '--quiet'], cwd=ROOT, capture_output=True, text=True)
        return ('PASS', 'Compose configuration valid') if result.returncode == 0 else ('FAIL', 'docker compose config failed; run it directly for details')
    if name == 'postgres':
        if not inside:
            if not shutil.which('docker'):
                return 'NOT AVAILABLE', 'PostgreSQL is internal; Docker CLI absent'
            result = subprocess.run(['docker', 'compose', 'exec', '-T', 'postgres', 'sh', '-c', 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'], cwd=ROOT, capture_output=True, text=True)
            return ('PASS', 'PostgreSQL responds') if result.returncode == 0 else ('FAIL', 'PostgreSQL readiness check failed')
        try:
            import psycopg
        except ImportError:
            return 'NOT AVAILABLE', 'Install requirements.txt for psycopg'
        with psycopg.connect(connect_timeout=5) as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1')
                assert cursor.fetchone()[0] == 1
        return 'PASS', 'PostgreSQL query succeeds'
    urls = {
        'n8n': os.getenv('N8N_URL', 'http://n8n:5678' if inside else 'http://localhost:5678') + '/healthz',
        'searxng': os.getenv('SEARXNG_URL', 'http://searxng:8080' if inside else 'http://localhost:8080') + '/search?q=industrial+automation+Example City+Illinois&format=json',
        'ollama': (os.getenv('OLLAMA_URL', 'http://host.docker.internal:11434') if inside else os.getenv('OLLAMA_HOST_URL', 'http://localhost:11434')) + '/api/tags',
        'crawl4ai': os.getenv('CRAWL4AI_URL', '').rstrip('/') + '/health',
        'worker': 'http://localhost:8000/health',
    }
    if name == 'crawl4ai' and not os.getenv('CRAWL4AI_URL'):
        return 'NOT AVAILABLE', 'Optional Crawl4AI disabled; bounded HTTP extraction is default'
    if name == 'worker' and not inside:
        if not shutil.which('docker'):
            return 'NOT AVAILABLE', 'Worker is internal; Docker CLI absent'
        result = subprocess.run(['docker', 'compose', 'exec', '-T', 'worker', 'python', 'scripts/healthcheck.py', '--inside', '--service', 'worker'], cwd=ROOT, capture_output=True, text=True)
        return ('PASS', 'Worker responds') if result.returncode == 0 else ('FAIL', 'Worker health check failed')
    value = request(urls[name])
    if name == 'searxng' and not isinstance(value.get('results'), list):
        raise ValueError('SearXNG did not return a JSON results list')
    if name == 'ollama':
        names = {item['name'] for item in value.get('models', [])}
        expected = {os.getenv('SCOUT_MODEL', 'qwen3.5:4b'), os.getenv('RESEARCH_MODEL', 'qwen3.5:9b')}
        missing = expected - names
        if missing:
            return 'FAIL', 'Missing models: ' + ', '.join(sorted(missing))
        if structured:
            base = urls[name].rsplit('/api/', 1)[0]
            result = request(base + '/api/chat', {'model': os.getenv('SCOUT_MODEL', 'qwen3.5:4b'), 'stream': False, 'think': False, 'format': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False}, 'messages': [{'role': 'user', 'content': 'Return {"ok":true}.'}]}, timeout=300)
            if json.loads(result['message']['content']) != {'ok': True}:
                raise ValueError('Structured model response invalid')
    return 'PASS', name + ' responds'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside', action='store_true', help='Use Docker service DNS and native-host Ollama bridge')
    parser.add_argument('--service', choices=['docker', 'postgres', 'n8n', 'searxng', 'ollama', 'crawl4ai', 'worker'])
    parser.add_argument('--structured', action='store_true', help='Also request a tiny scout-model JSON response')
    args = parser.parse_args()
    load_env()
    failed = False
    for name in ([args.service] if args.service else (['postgres', 'n8n', 'searxng', 'ollama', 'crawl4ai', 'worker'] if args.inside else ['docker', 'postgres', 'n8n', 'searxng', 'ollama', 'crawl4ai', 'worker'])):
        try:
            status, detail = check(name, args.inside, args.structured)
        except urllib.error.HTTPError as exc:
            status, detail = 'FAIL', 'HTTP status ' + str(exc.code)
        except (urllib.error.URLError, OSError) as exc:
            status, detail = 'NOT AVAILABLE', 'Service unreachable: ' + type(exc).__name__
        except Exception as exc:
            status, detail = 'FAIL', type(exc).__name__ + ': response or query failed'
        print(f'{status}: {name}: {detail}')
        failed = failed or status == 'FAIL' or (args.inside and status == 'NOT AVAILABLE' and name != 'crawl4ai')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
