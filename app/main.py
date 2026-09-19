import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import schemas, services, exclusions, digest
from .logic import SCORE_LIMITS, normalize_domain, junk_domain, score_research, filter_contacts, evidence_summary, research_queries, select_research_urls, daily_queries, review_draft

app = FastAPI(title='Robotics sponsor research')


@contextmanager
def db():
    with psycopg.connect(os.getenv('DATABASE_URL', ''), row_factory=dict_row) as connection:
        connection.execute("SET search_path TO fundraising")
        yield connection


def lead(connection, lead_id):
    row = connection.execute('SELECT l.*, c.domain, c.company_name, c.homepage_url, c.industry FROM leads l JOIN companies c ON c.id=l.company_id WHERE l.id=%s', (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Lead not found')
    return row


def claim(lead_id, stage, allowed):
    with db() as connection:
        row = lead(connection, lead_id)
        guard_exclusion(row)
        if row['status'] not in allowed:
            if row['status'] == stage:
                # A stopped worker leaves an inspectable lease, recoverable after 90 minutes.
                row = connection.execute("SELECT *, stage_started_at < now() - interval '90 minutes' AS stale FROM leads WHERE id=%s FOR UPDATE", (lead_id,)).fetchone()
                if not row['stale']:
                    raise HTTPException(409, 'Stage is already running')
            else:
                raise HTTPException(409, 'Lead is not eligible for this stage')
        updated = connection.execute("UPDATE leads SET status=%s, attempts=attempts+1, last_error=NULL, stage_started_at=now(), updated_at=now() WHERE id=%s AND status=%s RETURNING id", (stage, lead_id, row['status'])).fetchone()
        if not updated:
            raise HTTPException(409, 'Another worker claimed this lead')
        return lead(connection, lead_id)


def failed(lead_id, status, error):
    with db() as connection:
        connection.execute('UPDATE leads SET status=%s,last_error=%s,updated_at=now() WHERE id=%s', (status, str(error)[:1500], lead_id))


def guard_exclusion(row):
    reason = exclusions.blocked_reason(row.get('domain'), row.get('company_name'))
    if reason:
        raise HTTPException(409, reason)


class Discover(BaseModel):
    query_limit: int = Field(1, ge=1, le=3)
    result_limit: int = Field(5, ge=1, le=5)
    query_offset: int = Field(0, ge=0)
    rotate_daily: bool = False
    query: str = Field(None, max_length=300)


class LeadInput(BaseModel):
    lead_id: int = Field(..., gt=0)


class DraftInput(LeadInput):
    force: bool = False


class TelegramCommand(BaseModel):
    update_id: int = Field(..., ge=0)
    message_id: int = Field(..., ge=0)
    chat_id: int
    command: Literal['search', 'draft', 'status']
    query: Optional[str] = Field(None, max_length=300)
    lead_id: Optional[int] = Field(None, gt=0)


class TelegramUpdateBatch(BaseModel):
    updates: List[Dict[str, Any]] = Field(default_factory=list, max_length=10)


TELEGRAM_COMMAND = re.compile(r'^/(search|draft|status)(?:@[A-Za-z0-9_]+)?(?:\s+(.+))?$', re.IGNORECASE)


def telegram_owner_chat_id():
    owner_chat_id = os.getenv('TELEGRAM_OWNER_CHAT_ID', '').strip()
    if not owner_chat_id:
        raise HTTPException(503, 'Telegram owner chat is not configured')
    return owner_chat_id


def parse_telegram_update(update, owner_chat_id):
    message = update.get('message')
    if not isinstance(message, dict) or not isinstance(message.get('text'), str):
        return None
    chat_id = (message.get('chat') or {}).get('id')
    sender_id = (message.get('from') or {}).get('id')
    if str(chat_id) != owner_chat_id or str(sender_id) != owner_chat_id:
        return None
    match = TELEGRAM_COMMAND.fullmatch(message['text'].strip())
    if not match:
        return None
    command = match.group(1).lower()
    argument = ' '.join((match.group(2) or '').split()) or None
    if command == 'draft':
        if not argument or not re.fullmatch(r'[1-9]\d{0,17}', argument):
            return None
        lead_id = int(argument)
        query = None
    elif command == 'status':
        if argument:
            return None
        lead_id = None
        query = None
    else:
        if argument and len(argument) > 300:
            return None
        lead_id = None
        query = argument
    return {
        'update_id': update['update_id'],
        'message_id': message.get('message_id'),
        'chat_id': chat_id,
        'command': command,
        'query': query,
        'lead_id': lead_id,
    }


def telegram_poll_state(connection):
    return connection.execute(
        '''INSERT INTO telegram_poll_state(id,next_offset,initialized)
           VALUES(1,-1,false) ON CONFLICT(id) DO UPDATE SET id=EXCLUDED.id
           RETURNING next_offset,initialized'''
    ).fetchone()


@app.get('/telegram-commands/cursor')
def telegram_command_cursor():
    telegram_owner_chat_id()
    with db() as connection:
        state = telegram_poll_state(connection)
    return {'offset': state['next_offset']}


@app.post('/telegram-commands/intake')
def intake_telegram_updates(request: TelegramUpdateBatch):
    owner_chat_id = telegram_owner_chat_id()
    updates = sorted(
        (update for update in request.updates if isinstance(update.get('update_id'), int) and update['update_id'] >= 0),
        key=lambda update: update['update_id'],
    )
    with db() as connection:
        state = telegram_poll_state(connection)
        if state['initialized']:
            updates = [update for update in updates if update['update_id'] >= state['next_offset']]
        default_offset = 0 if not state['initialized'] else state['next_offset']
        next_offset = max(max((update['update_id'] + 1 for update in updates), default=default_offset), state['next_offset'])
        connection.execute(
            'UPDATE telegram_poll_state SET next_offset=%s,initialized=true,updated_at=now() WHERE id=1',
            (next_offset,),
        )
        if not state['initialized']:
            return {'commands': [], 'next_offset': next_offset}
        commands = []
        for update in updates:
            parsed = parse_telegram_update(update, owner_chat_id)
            if not parsed:
                continue
            row = connection.execute(
                '''INSERT INTO telegram_commands(update_id,message_id,chat_id,command,query,lead_id)
                   VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(update_id) DO NOTHING RETURNING update_id''',
                (parsed['update_id'], parsed['message_id'], parsed['chat_id'], parsed['command'], parsed['query'], parsed['lead_id']),
            ).fetchone()
            if row:
                commands.append({'accepted': True, **parsed})
    return {'commands': commands, 'next_offset': next_offset}


@app.post('/telegram-commands/claim')
def claim_telegram_command(request: TelegramCommand):
    owner_chat_id = os.getenv('TELEGRAM_OWNER_CHAT_ID', '').strip()
    if not owner_chat_id or str(request.chat_id) != owner_chat_id:
        raise HTTPException(403, 'Telegram command is not authorized')
    query = ' '.join(request.query.split()) if request.query else None
    if request.command == 'draft' and request.lead_id is None:
        raise HTTPException(422, 'Draft command requires a lead ID')
    if request.command != 'draft' and request.lead_id is not None:
        raise HTTPException(422, 'Lead ID is only valid for draft commands')
    if request.command != 'search' and query is not None:
        raise HTTPException(422, 'Query is only valid for search commands')
    with db() as connection:
        row = connection.execute(
            '''INSERT INTO telegram_commands(update_id,message_id,chat_id,command,query,lead_id)
               VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(update_id) DO NOTHING RETURNING update_id''',
            (request.update_id, request.message_id, request.chat_id, request.command, query, request.lead_id),
        ).fetchone()
    return {'accepted': bool(row), 'update_id': request.update_id, 'command': request.command,
            'query': query, 'lead_id': request.lead_id}


@app.get('/health')
def health():
    try:
        with db() as connection:
            connection.execute('SELECT 1 FROM leads LIMIT 1')
        return {'status': 'ok', 'database': 'ok'}
    except Exception as exc:
        raise HTTPException(503, 'Database unavailable or schema not initialized') from exc


@app.get('/leads')
def list_leads():
    with db() as connection:
        return connection.execute('SELECT l.*, c.domain,c.company_name FROM leads l JOIN companies c ON c.id=l.company_id ORDER BY l.updated_at DESC LIMIT 200').fetchall()


@app.get('/digest')
def owner_digest():
    rules = exclusions.load_exclusions()
    with db() as connection:
        rows = connection.execute("""SELECT l.id AS lead_id,c.domain,c.company_name,l.status,l.overall_score,l.tier,
            d.id IS NOT NULL AS draft_exists,
            ARRAY(SELECT DISTINCT e.source_url FROM evidence e WHERE e.lead_id=l.id ORDER BY e.source_url LIMIT 10) AS source_urls
            FROM leads l JOIN companies c ON c.id=l.company_id
            LEFT JOIN email_drafts d ON d.lead_id=l.id
            WHERE l.status IN ('researched','needs_review','draft_failed') AND l.overall_score>=70
              AND (d.id IS NULL OR NOT d.approved)
              AND EXISTS (SELECT 1 FROM evidence e WHERE e.lead_id=l.id)
            ORDER BY l.updated_at DESC,l.id DESC LIMIT 200""").fetchall()
    return digest.format_digest(rows, rules)


@app.get('/telegram-drafts/{lead_id}')
def owner_telegram_draft(lead_id: int):
    with db() as connection:
        row = connection.execute(
            '''SELECT l.id AS lead_id,c.domain,c.company_name,d.id AS draft_id,
                      d.subject,d.body,d.linkedin_note,d.followup_body,d.approved
               FROM leads l JOIN companies c ON c.id=l.company_id
               JOIN email_drafts d ON d.lead_id=l.id WHERE l.id=%s''',
            (lead_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, 'Saved draft not found')
    guard_exclusion(row)
    return digest.format_draft(row)


@app.get('/leads/{lead_id}')
def get_lead(lead_id: int):
    with db() as connection:
        result = lead(connection, lead_id)
        result['evidence'] = connection.execute('SELECT * FROM evidence WHERE lead_id=%s', (lead_id,)).fetchall()
        result['contacts'] = connection.execute('SELECT * FROM contacts WHERE company_id=%s', (result['company_id'],)).fetchall()
        result['drafts'] = connection.execute('SELECT * FROM email_drafts WHERE lead_id=%s ORDER BY created_at DESC', (lead_id,)).fetchall()
        return result


@app.post('/discover')
def discover(request: Discover):
    rules = exclusions.load_exclusions()
    locations = json.loads((services.ROOT / 'config/locations.json').read_text())
    templates = json.loads((services.ROOT / 'config/search-query-templates.json').read_text())['discovery']
    configured_queries = [template.format(location=location) for location in locations for template in templates]
    queries = configured_queries[request.query_offset:request.query_offset + request.query_limit]
    if request.rotate_daily and not request.query:
        day = datetime.now(ZoneInfo(os.getenv('TZ', 'UTC'))).date()
        queries = daily_queries(configured_queries, day, request.query_limit)
    if request.query:
        queries = [request.query]
    output, errors, excluded = [], [], []
    for query in queries:
        for result in services.search(query, request.result_limit):
            try:
                domain = normalize_domain(result['url'])
                if junk_domain(domain):
                    continue
                reason = exclusions.blocked_reason(domain, result.get('title'), rules)
                if reason:
                    excluded.append({'url': result['url'], 'domain': domain, 'reason': reason})
                    continue
                with db() as connection:
                    company = connection.execute('INSERT INTO companies(domain,company_name,homepage_url) VALUES(%s,%s,%s) ON CONFLICT(domain) DO NOTHING RETURNING id', (domain, result.get('title', domain)[:250], 'https://' + domain + '/')).fetchone()
                    if company:
                        lead_id = connection.execute('INSERT INTO leads(company_id) VALUES(%s) RETURNING id', (company['id'],)).fetchone()['id']
                    else:
                        existing = connection.execute('SELECT l.id,l.status,c.company_name,c.domain FROM leads l JOIN companies c ON c.id=l.company_id WHERE c.domain=%s', (domain,)).fetchone()
                        if existing:
                            reason = exclusions.blocked_reason(existing.get('domain', domain), existing.get('company_name'), rules)
                            if reason:
                                excluded.append({'lead_id': existing['id'], 'domain': domain, 'reason': reason})
                                continue
                        if not existing or existing['status'] not in ('discovered', 'scout_failed', 'screening', 'ready', 'research_failed'):
                            continue
                        lead_id = existing['id']
                        if existing['status'] in ('ready', 'research_failed'):
                            output.append({'lead_id': lead_id, 'domain': domain, 'company_name': result.get('title', domain)})
                            continue
                claim(lead_id, 'screening', ('discovered', 'scout_failed'))
                try:
                    scout = services.model('scout', {'url': result['url'], 'title': result.get('title', ''), 'snippet': result.get('content', '')[:1500]}, schemas.SCOUT, scout=True)
                    relevant = scout['relevant'] and scout['confidence'] >= .70
                    reason = exclusions.blocked_reason(domain, scout['company_name'], rules)
                    relevant = relevant and not reason
                    with db() as connection:
                        connection.execute('UPDATE companies SET company_name=%s,industry=%s,location=%s,updated_at=now() WHERE id=(SELECT company_id FROM leads WHERE id=%s)', (scout['company_name'], scout['industry'], scout['local_signal'], lead_id))
                        connection.execute('UPDATE leads SET scout_relevance=%s,scout_confidence=%s,scout_reason=%s,status=%s,updated_at=now() WHERE id=%s', (scout['relevant'], scout['confidence'], reason or scout['reason'], 'ready' if relevant else 'skipped', lead_id))
                    if reason:
                        excluded.append({'lead_id': lead_id, 'domain': domain, 'reason': reason})
                    if relevant:
                        output.append({'lead_id': lead_id, 'domain': domain, 'company_name': scout['company_name']})
                except Exception as exc:
                    failed(lead_id, 'scout_failed', exc)
                    errors.append({'lead_id': lead_id, 'error': str(exc)[:300]})
            except (ValueError, HTTPException) as exc:
                errors.append({'url': result.get('url', ''), 'error': str(exc)[:300]})
    return {'leads': output, 'errors': errors, 'excluded': excluded, 'queries': queries}


@app.post('/research')
def research(request: LeadInput):
    with db() as connection:
        saved = lead(connection, request.lead_id)
        guard_exclusion(saved)
        if saved['status'] in ('researched', 'needs_review'):
            return {'lead_id': request.lead_id, 'status': saved['status'], 'overall_score': saved['overall_score'], 'tier': saved['tier'], 'qualified': saved['overall_score'] >= 70}
    row = claim(request.lead_id, 'researching', ('ready', 'research_failed'))
    try:
        templates = json.loads((services.ROOT / 'config/search-query-templates.json').read_text())['research']
        search_results = []
        for query in research_queries(templates, row['company_name'], row['domain']):
            search_results.extend(services.search(query, 3))
        urls = select_research_urls(row['homepage_url'], search_results, row['domain'])
        sources, fetch_errors = {}, []
        for url in urls[:8]:
            try:
                source = services.fetch(url)
                sources[source['url']] = source
            except Exception as exc:
                fetch_errors.append(str(exc)[:200])
        if not sources:
            raise ValueError('No usable public pages: ' + '; '.join(fetch_errors))
        result = services.model('researcher', {'company': row['company_name'], 'sources': list(sources.values())}, schemas.RESEARCH)
        result = score_research(result, sources)
        contacts = services.model('contact-researcher', {'target_roles': result['target_roles'], 'sources': list(sources.values())}, schemas.CONTACTS)['contacts']
        contacts, contact_warnings = filter_contacts(contacts, sources)
        with db() as connection:
            assignments = ','.join(key + '=%s' for key in SCORE_LIMITS)
            connection.execute('UPDATE leads SET ' + assignments + ",research_summary=%s,overall_score=%s,tier=%s,suggested_cash_ask=%s,in_kind_opportunities=%s,target_contact_roles=%s,outreach_angle=%s,status='researched',researched_at=now(),updated_at=now() WHERE id=%s", tuple(result[key] for key in SCORE_LIMITS) + (evidence_summary(result['evidence']), result['overall_score'], result['tier'], result['suggested_cash_ask'], Jsonb(result['in_kind_opportunities']), Jsonb(result['target_roles']), result['outreach_angle'], request.lead_id))
            connection.execute('DELETE FROM evidence WHERE lead_id=%s', (request.lead_id,))
            for item in result['evidence']:
                connection.execute('INSERT INTO evidence(lead_id,company_id,claim,source_url,source_title,excerpt,retrieved_at) VALUES(%s,%s,%s,%s,%s,%s,to_timestamp(%s))', (request.lead_id, row['company_id'], item['claim'], item['source_url'], sources[item['source_url']]['title'], item['excerpt'], sources[item['source_url']]['retrieved_at']))
            connection.execute('DELETE FROM contacts WHERE company_id=%s', (row['company_id'],))
            for item in contacts:
                connection.execute('INSERT INTO contacts(company_id,name,title,email,public_profile_url,source_url,excerpt,confidence) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)', (row['company_id'], item['name'], item['title'], item['email'], item['public_profile_url'], item['source_url'], item['excerpt'], item['confidence']))
            warning_summary = 'Contact validation warnings: ' + json.dumps(contact_warnings) if contact_warnings else None
            connection.execute('UPDATE leads SET last_error=%s WHERE id=%s', (warning_summary, request.lead_id))
        return {'lead_id': request.lead_id, 'status': 'researched', 'overall_score': result['overall_score'], 'tier': result['tier'], 'qualified': result['overall_score'] >= 70, 'contact_warnings': contact_warnings}
    except Exception as exc:
        failed(request.lead_id, 'research_failed', exc)
        raise HTTPException(502, str(exc)[:500]) from exc


@app.post('/draft')
def draft(request: DraftInput):
    with db() as connection:
        row = lead(connection, request.lead_id)
        guard_exclusion(row)
        if row['status'] == 'needs_review':
            existing = connection.execute('SELECT id,approved FROM email_drafts WHERE lead_id=%s', (request.lead_id,)).fetchone()
            if existing:
                if not request.force:
                    return {'lead_id': request.lead_id, 'draft_id': existing['id'], 'status': 'needs_review', 'approved': existing['approved']}
                if existing['approved']:
                    raise HTTPException(409, 'Draft is already approved; cannot force a redraft')
        if (row['overall_score'] or 0) < 70:
            raise HTTPException(409, 'Drafts require score >= 70')
    allowed = ('researched', 'draft_failed', 'needs_review') if request.force else ('researched', 'draft_failed')
    claim(request.lead_id, 'drafting', allowed)
    try:
        data = get_lead(request.lead_id)
        payload = {'company_name': data['company_name'], 'evidence': [{'source_url': item['source_url'], 'excerpt': item['excerpt']} for item in data['evidence']], 'contacts': [{'name': item['name'], 'title': item['title'], 'email': item['email']} for item in data['contacts']], 'outreach_angle': data['outreach_angle'] or '', 'in_kind_opportunities': data['in_kind_opportunities'] or [], 'research_summary': data['research_summary'] or ''}
        reasons = []
        revision_notes = []
        for attempt in range(3):
            model_payload = payload if attempt == 0 else dict(payload, revision_notes=revision_notes)
            result = services.model('email-writer', model_payload, schemas.DRAFT)
            reasons = review_draft(result)
            if not reasons:
                break
            revision_notes = list(dict.fromkeys(revision_notes + reasons))
        if reasons:
            raise ValueError('Draft rejected after two revisions: ' + '; '.join(reasons))
        approval_race = False
        with db() as connection:
            inserted = connection.execute('INSERT INTO email_drafts(lead_id,subject,body,linkedin_note,followup_body) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(lead_id) DO UPDATE SET subject=EXCLUDED.subject,body=EXCLUDED.body,linkedin_note=EXCLUDED.linkedin_note,followup_body=EXCLUDED.followup_body,updated_at=now() WHERE NOT email_drafts.approved RETURNING id', (request.lead_id, result['subject'], result['body'], result['linkedin_note'], result['followup_body'])).fetchone()
            if not inserted:
                connection.execute("UPDATE leads SET status='needs_review',updated_at=now() WHERE id=%s", (request.lead_id,))
                approval_race = True
            else:
                draft_id = inserted['id']
                connection.execute("UPDATE leads SET status='needs_review',updated_at=now() WHERE id=%s", (request.lead_id,))
                connection.execute('UPDATE leads SET last_error=NULL WHERE id=%s', (request.lead_id,))
        if approval_race:
            raise HTTPException(409, 'Draft was approved before the redraft could complete')
        return {'lead_id': request.lead_id, 'draft_id': draft_id, 'status': 'needs_review', 'approved': False, 'draft_warnings': reasons}
    except HTTPException:
        raise
    except Exception as exc:
        failed(request.lead_id, 'draft_failed', exc)
        raise HTTPException(502, str(exc)[:500]) from exc


class Approval(BaseModel):
    approved_by: str = Field(..., min_length=1, max_length=200)


@app.post('/drafts/{draft_id}/approve')
def approve(draft_id: int, request: Approval):
    reviewer = request.approved_by.strip()
    if not reviewer:
        raise HTTPException(422, 'Reviewer name is required')
    with db() as connection:
        company = connection.execute('SELECT c.domain,c.company_name FROM email_drafts d JOIN leads l ON l.id=d.lead_id JOIN companies c ON c.id=l.company_id WHERE d.id=%s', (draft_id,)).fetchone()
        if not company:
            raise HTTPException(409, 'Draft not found or already approved')
        guard_exclusion(company)
        row = connection.execute("UPDATE email_drafts SET approved=true,approved_by=%s,draft_status='approved',updated_at=now() WHERE id=%s AND draft_status IN ('needs_review','pending_review') AND NOT approved RETURNING id,approved,approved_by", (reviewer, draft_id)).fetchone()
        if not row:
            raise HTTPException(409, 'Draft not found or already approved')
        return row
