"""Generate unsaved draft fixtures and report deterministic writing checks."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import schemas, services
from app.logic import review_draft


def word_count(value):
    return len(re.findall(r"\b[\w'-]+\b", value or ""))


def main():
    fixtures = json.loads((ROOT / 'config' / 'draft-quality-fixtures.json').read_text(encoding='utf-8'))
    reports = []
    for fixture in fixtures:
        review_history = []
        revision_notes = []
        for attempt in range(3):
            payload = fixture['payload'] if attempt == 0 else dict(fixture['payload'], revision_notes=revision_notes)
            draft = services.model('email-writer', payload, schemas.DRAFT)
            reasons = review_draft(draft)
            review_history.append(reasons)
            if not reasons:
                break
            revision_notes = list(dict.fromkeys(revision_notes + reasons))
        reports.append({
            'fixture': fixture['name'],
            'attempts': len(review_history),
            'review_history': review_history,
            'draft': draft,
            'review': review_draft(draft),
            'metrics': {
                'subject_characters': len(draft['subject']),
                'body_words_total': word_count(draft['body']),
                'linkedin_characters': len(draft['linkedin_note']),
                'followup_words_total': word_count(draft['followup_body']),
            },
        })
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
