from .logic import SCORE_LIMITS

def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}

STRING = {'type': 'string', 'maxLength': 4000}
STRINGS = {'type': 'array', 'items': STRING, 'maxItems': 12}
CONFIDENCE = {'type': 'number', 'minimum': 0, 'maximum': 1}
SCOUT = object_schema({'company_name': STRING, 'relevant': {'type': 'boolean'}, 'confidence': CONFIDENCE,
                       'industry': STRING, 'local_signal': STRING, 'reason': STRING})
EVIDENCE = object_schema({'claim': STRING, 'source_url': STRING, 'excerpt': STRING})
RESEARCH = object_schema(dict({'company_name': STRING, 'summary': STRING,
    'overall_score': {'type': 'integer'}, 'tier': {'type': 'integer'}, 'suggested_cash_ask': STRING,
    'in_kind_opportunities': STRINGS, 'target_roles': STRINGS, 'outreach_angle': STRING,
    'evidence': {'type': 'array', 'items': EVIDENCE, 'minItems': 1, 'maxItems': 20}},
    **{key: {'type': 'integer', 'minimum': 0, 'maximum': maximum} for key, maximum in SCORE_LIMITS.items()}))
CONTACT = object_schema({'name': STRING, 'title': STRING, 'email': STRING, 'public_profile_url': STRING,
                         'source_url': STRING, 'excerpt': STRING, 'confidence': CONFIDENCE})
CONTACTS = object_schema({'contacts': {'type': 'array', 'items': CONTACT, 'maxItems': 8}})
DRAFT = object_schema({key: STRING for key in ('subject', 'body', 'linkedin_note', 'followup_body')})
