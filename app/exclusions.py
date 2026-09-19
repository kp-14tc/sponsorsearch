"""Deterministic, offline company exclusions; malformed configuration blocks work."""
import json
import re
import unicodedata
from pathlib import Path

from .logic import normalize_domain

CONFIG = Path(__file__).resolve().parent.parent / 'config/excluded-companies.json'


def normalized_name(value):
    return ' '.join(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', value).casefold()))


def load_exclusions():
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('reason'), str) or not data['reason'].strip() or not isinstance(data.get('companies'), list):
            raise ValueError('Expected reason and companies')
        entries = []
        for company in data['companies']:
            if not isinstance(company, dict) or not isinstance(company.get('name'), str) or not normalized_name(company['name']):
                raise ValueError('Each company requires a name')
            names = [company['name']]
            for field in ('aliases', 'domains'):
                values = company.get(field)
                if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
                    raise ValueError('Each company requires string lists for aliases and domains')
            names.extend(company['aliases'])
            if any(not normalized_name(name) for name in names):
                raise ValueError('Empty normalized alias')
            entries.append((company['name'], [normalized_name(name) for name in names], {normalize_domain(domain) for domain in company['domains']}))
        return data['reason'], entries
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError('Company exclusion configuration unavailable or invalid') from exc


def blocked_reason(domain=None, name=None, rules=None):
    reason, entries = rules if rules is not None else load_exclusions()
    domain = normalize_domain(domain) if domain else None
    name = ' ' + normalized_name(name or '') + ' '
    for company, names, domains in entries:
        if domain in domains or any(' ' + alias + ' ' in name for alias in names):
            return reason + ': ' + company
    return None
