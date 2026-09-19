"""Plain-text owner review queue from durable lead records."""
from . import exclusions

SCAN_LIMIT = 200
DISPLAY_LIMIT = 25
# Telegram rejects sendMessage text above 4096 characters; chunk well below it
# so a part counter still fits.
MESSAGE_LIMIT = 3500


def plain(value):
    return ' '.join(str(value).split())


def chunk(lines, limit=MESSAGE_LIMIT):
    """Group rendered lines into Telegram-sized bodies, splitting between lines."""
    bodies, current, length = [], [], 0
    for line in lines:
        if len(line) > limit:
            line = line[:limit - 1] + '…'
        extra = len(line) + (1 if current else 0)
        if current and length + extra > limit:
            bodies.append('\n'.join(current))
            current, length, extra = [], 0, len(line)
        current.append(line)
        length += extra
    if current:
        bodies.append('\n'.join(current))
    return bodies or ['']


def complete_lines(value, limit=MESSAGE_LIMIT):
    """Preserve complete draft text while keeping every line safe for chunk()."""
    output = []
    for line in str(value or '').replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if not line:
            output.append('')
            continue
        while len(line) > limit:
            output.append(line[:limit])
            line = line[limit:]
        output.append(line)
    return output or ['']


def format_draft(row):
    title = 'Saved sponsorship draft for Lead ' + str(row['lead_id'])
    review_status = 'approved by a human reviewer' if row.get('approved') else 'pending human approval'
    lines = [
        title,
        plain(row['company_name']) + ' (' + plain(row['domain']) + ')',
        'Draft ' + str(row['draft_id']) + ' | ' + review_status,
        '',
        'Subject:',
    ]
    lines.extend(complete_lines(row['subject']))
    lines.extend(['', 'Email body:'])
    lines.extend(complete_lines(row['body']))
    lines.extend(['', 'LinkedIn note:'])
    lines.extend(complete_lines(row['linkedin_note']))
    lines.extend(['', 'Follow-up:'])
    lines.extend(complete_lines(row['followup_body']))
    lines.extend(['', 'Review the evidence in n8n workflow 04 before approving. This draft was not sent to the company.'])
    bodies = chunk(lines)
    total = len(bodies)
    messages = [
        {'part': index + 1, 'parts': total, 'text': body if total == 1 else body + '\n\n(' + str(index + 1) + '/' + str(total) + ')'}
        for index, body in enumerate(bodies)
    ]
    return {'title': title, 'text': '\n'.join(lines), 'messages': messages, 'lead_count': 1, 'truncated': False}


def format_digest(rows, rules):
    eligible = [row for row in rows if not exclusions.blocked_reason(row['domain'], row['company_name'], rules)]
    visible = eligible[:DISPLAY_LIMIT]
    truncated = len(eligible) > DISPLAY_LIMIT or len(rows) >= SCAN_LIMIT
    title = 'Sponsorship lead review queue (' + str(len(visible)) + ')'
    lines = [title, '']
    if not visible:
        lines.append('No qualifying leads ready for review in the checked queue.')
    for row in visible:
        lines.extend([
            plain(row['company_name']) + ' (' + plain(row['domain']) + ')',
            'Lead ' + str(row['lead_id']) + ' | ' + plain(row['status']) + ' | Score ' + str(row['overall_score']) + ' | Tier ' + str(row['tier']),
            'Draft: pending human approval' if row['draft_exists'] else 'Draft: not created',
            'Persisted evidence sources (up to 10):',
        ])
        lines.extend(plain(url) for url in row.get('source_urls', []))
        lines.append('')
    lines.extend([
        'Showing ' + str(len(visible)) + ' leads from the latest ' + str(len(rows)) + ' checked qualified pending records (scan limit 200; display limit 25).',
        'Queue may contain additional leads beyond these limits.' if truncated else 'All eligible leads in the checked queue are shown.',
        '', 'Review sources and drafts using n8n workflow 04. Approve only after human review.',
        'Pending leads can repeat in each daily digest until their drafts are approved.',
    ])
    bodies = chunk(lines)
    total = len(bodies)
    messages = [{'part': index + 1, 'parts': total, 'text': body if total == 1 else body + '\n\n(' + str(index + 1) + '/' + str(total) + ')'} for index, body in enumerate(bodies)]
    return {'title': title, 'text': '\n'.join(lines), 'messages': messages, 'lead_count': len(visible), 'truncated': truncated}
