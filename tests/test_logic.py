import unittest
from unittest.mock import patch
from app.logic import normalize_domain, public_url, score_research, SCORE_LIMITS, SIGNATURE_BLOCK, validate_contacts, evidence_summary, research_queries, select_research_urls, review_draft


def signed_body(text, greeting='Hi Jane,'):
    return greeting + '\n\n' + text + '\n\n' + SIGNATURE_BLOCK


def good_draft():
    return dict(
        subject='Learning about your CNC work',
        body="Hello Jane,\n\nI'm [Your Name], a student with Example Robotics Team, Team 0000 at Example City "
             "High School. I'm reaching out as part of our effort to learn from engineering and manufacturing professionals.\n\n"
             "I noticed that your team works in CNC machining. I would be interested in hearing which technical and "
             "problem-solving skills matter most for students preparing for manufacturing careers.\n\n"
             "Would you be open to a 15-minute conversation about your work and advice for students?\n\n"
             "Best,\n[Your Name]\nExample Robotics Team | Team 0000\nExample High School",
        linkedin_note="Hello Jane, I'm [Your Name], a student with Example Robotics Team. I noticed your CNC machining work and would appreciate the chance to connect and learn from your experience.",
        followup_body="Hello Jane,\n\nI wanted to follow up on my earlier message about your CNC machining work. Would you be open to a 15-minute conversation about skills students should develop for manufacturing careers?\n\nBest,\n[Your Name]\nExample Robotics Team | Team 0000\nExample High School",
    )


class LogicTests(unittest.TestCase):
    def test_domains_deduplicate_offline(self):
        self.assertEqual(normalize_domain('https://www.shop.Example.co.uk:443/page'), 'example.co.uk')
        self.assertEqual(normalize_domain('https://careers.example.com/jobs'), 'example.com')
        self.assertEqual(normalize_domain('https://bücher.de'), 'xn--bcher-kva.de')
        for url in ('http://127.0.0.1', 'http://localhost', 'https://a.local', 'ftp://example.com', 'http://user:pass@example.com'):
            with self.assertRaises(ValueError):
                normalize_domain(url)

    @patch('app.logic.socket.getaddrinfo')
    def test_private_and_mixed_dns_rejected(self, dns):
        for addresses in (['127.0.0.1'], ['169.254.169.254'], ['93.184.216.34', '10.0.0.1'], ['::1']):
            dns.return_value = [(0, 0, 0, '', (ip, 443)) for ip in addresses]
            with self.assertRaises(ValueError):
                public_url('https://example.com')
        dns.return_value = [(0, 0, 0, '', ('93.184.216.34', 443))]
        self.assertEqual(public_url('https://example.com/#x'), 'https://example.com/')

    def test_contacts_reject_guessed_email(self):
        source = {'https://example.com/': {'text': 'Jane Smith Engineering Manager email jane@example.com'}}
        contact = {'source_url': 'https://example.com/', 'excerpt': 'Jane Smith Engineering Manager',
                   'name': 'Jane Smith', 'title': 'Engineering Manager', 'email': 'jane@example.com', 'public_profile_url': ''}
        self.assertEqual(validate_contacts([contact], source), [contact])
        contact['email'] = 'jane.smith@example.com'
        with self.assertRaises(ValueError):
            validate_contacts([contact], source)

    def test_stored_summary_contains_only_cited_claims(self):
        summary = evidence_summary([{'claim': 'Makes CNC tooling', 'source_url': 'https://example.com/', 'excerpt': 'We make CNC tooling'}])
        self.assertIn('Makes CNC tooling [https://example.com/]', summary)
        self.assertIn('human review', summary)

    def test_targeted_queries_and_company_owned_url_priority(self):
        templates = ['"{company}" Illinois', 'site:{domain} STEM education', 'site:{domain} community', 'site:{domain} workforce development', 'site:{domain} FIRST Robotics', 'site:{domain} sponsorship', 'site:{domain} contact']
        queries = research_queries(templates, 'Fixture', 'example.com')
        self.assertEqual(len(queries), 5)
        self.assertIn('site:example.com FIRST Robotics', queries)
        self.assertIn('site:example.com contact', queries)
        urls = select_research_urls('https://example.com/', [{'url': 'https://news.com/fixture'}, {'url': 'https://example.com/contact'}, {'url': 'https://example.com/contact'}, {'url': 'https://careers.example.com/teams'}, {'url': 'https://notexample.com/page'}], 'example.com', 3)
        self.assertEqual(urls, ['https://example.com/', 'https://example.com/contact', 'https://careers.example.com/teams'])

    def test_exact_scores_and_untrusted_total(self):
        source = {'https://example.com/': {'text': 'We manufacture CNC equipment in Illinois.'}}
        for total, tier in ((54, 4), (55, 3), (69, 3), (70, 2), (84, 2), (85, 1), (100, 1)):
            data = {'evidence': [{'source_url': 'https://example.com/', 'excerpt': 'manufacture CNC equipment', 'claim': 'CNC'}], 'overall_score': 999, 'tier': 999}
            remaining = total
            for key, maximum in SCORE_LIMITS.items():
                data[key] = min(maximum, remaining)
                remaining -= data[key]
            self.assertEqual(score_research(data, source)['tier'], tier)
            self.assertEqual(data['overall_score'], total)
        data['evidence'][0]['source_url'] = 'https://invented.example/'
        with self.assertRaises(ValueError):
            score_research(data, source)
        data['evidence'][0]['source_url'] = 'https://example.com/'
        data['evidence'][0]['excerpt'] = 'This quote was invented.'
        with self.assertRaises(ValueError):
            score_research(data, source)

    def test_relationship_first_draft_passes_review(self):
        self.assertEqual(review_draft(good_draft()), [])

    def test_dollar_amount_flagged_in_body_and_followup(self):
        draft = good_draft()
        draft['body'] += ' We hope you can give $2,500.'
        reasons = review_draft(draft)
        self.assertIn('body states a dollar amount', reasons)
        draft = good_draft()
        draft['followup_body'] += ' A gift of 5,000 dollars would mean a lot.'
        reasons = review_draft(draft)
        self.assertIn('followup_body states a dollar amount', reasons)

    def test_hard_ask_flagged_in_subject(self):
        draft = good_draft()
        draft['subject'] = 'Sponsorship Request for Example Robotics Team'
        reasons = review_draft(draft)
        self.assertIn('subject makes a hard money ask', reasons)
        self.assertIn('subject leads with an ask', reasons)

    def test_normal_conversation_request_not_flagged(self):
        self.assertEqual(review_draft(good_draft()), [])
        draft = good_draft()
        draft['body'] = signed_body('Short note asking to connect and learn more about your work over a quick call.')
        self.assertEqual(review_draft(draft), [])

    def test_missing_signature_placeholder_flagged_in_body_and_followup(self):
        draft = good_draft()
        draft['body'] = draft['body'].replace('[Your Name]', 'Example Robotics Team')
        reasons = review_draft(draft)
        self.assertTrue(any('body' in reason and 'signature' in reason for reason in reasons))
        draft = good_draft()
        draft['followup_body'] = draft['followup_body'].replace('[Your Name]', 'Example Robotics Team')
        reasons = review_draft(draft)
        self.assertTrue(any('followup_body' in reason and 'signature' in reason for reason in reasons))

    def test_other_bracketed_placeholders_flagged(self):
        draft = good_draft()
        draft['body'] = draft['body'].replace('[Your Name]', '[Student Name]')
        reasons = review_draft(draft)
        self.assertTrue(any('[Student Name]' in reason for reason in reasons))
        draft = good_draft()
        draft['followup_body'] = draft['followup_body'].replace('[Your Name]', '[Name]')
        reasons = review_draft(draft)
        self.assertTrue(any('[Name]' in reason for reason in reasons))

    def test_repeated_placeholder_reason_is_not_duplicated(self):
        draft = good_draft()
        draft['body'] = ("Hi Jane,\n\n[Student Name] here, writing on behalf of [Student Name] and Example Robotics "
                          "Robotics.\n\nBest,\n[Student Name]")
        reasons = review_draft(draft)
        self.assertEqual(len(reasons), len(set(reasons)))
        self.assertEqual(reasons.count('body uses placeholder [Student Name] instead of [Your Name]'), 1)

    def test_broken_self_introduction_flagged(self):
        draft = good_draft()
        draft['body'] = ("Hi Jane,\n\nMy name is a member of Example Robotics Team (Team 0000), and we would "
                          "love to learn about your work.\n\nBest,\n[Your Name]")
        reasons = review_draft(draft)
        self.assertTrue(any('introduces the sender' in reason for reason in reasons))

    def test_correct_self_introduction_not_flagged(self):
        draft = good_draft()
        draft['body'] = ("Hi Jane,\n\nMy name is [Your Name], and I am a member of Example Robotics Team "
                          "(Team 0000), and we would love to learn about your work.\n\nBest,\n[Your Name]")
        reasons = review_draft(draft)
        self.assertFalse(any('introduces the sender' in reason for reason in reasons))

    def test_fabricated_following_relationship_flagged(self):
        draft = good_draft()
        draft['body'] = ("Hi Jane,\n\nWe have been following Palatine Welding's work for over 45 years and would "
                          "love to learn more.\n\nBest,\n[Your Name]")
        reasons = review_draft(draft)
        self.assertTrue(any('rapport' in reason and 'body' in reason for reason in reasons))

    def test_company_history_evidence_not_flagged(self):
        draft = good_draft()
        draft['body'] = signed_body("Palatine Welding has over 45 years in metal fabrication, and I would be interested "
                                    "in learning more about your work.")
        self.assertEqual(review_draft(draft), [])

    def test_long_time_admirer_and_neighbor_claims_flagged(self):
        draft = good_draft()
        draft['body'] = ("Hi Jane,\n\nWe are neighbors and long-time admirers of Swiss Automation, Inc., and "
                          "would love to learn more.\n\nBest,\n[Your Name]")
        reasons = review_draft(draft)
        self.assertTrue(any('rapport' in reason and 'body' in reason for reason in reasons))

    def test_prior_relationship_claims_flagged_across_tense_and_verb(self):
        claims = (
            "We have followed Palatine Welding's reputation for over 45 years.",
            "We have watched your company grow for decades.",
            "We have known your team for years.",
            "We have been following Palatine Welding's work for over 45 years.",
        )
        for claim in claims:
            draft = good_draft()
            draft['body'] = "Hi Jane,\n\n" + claim + "\n\nBest,\n[Your Name]"
            reasons = review_draft(draft)
            self.assertTrue(any('rapport' in reason and 'body' in reason for reason in reasons), claim)

    def test_admiration_language_is_flagged(self):
        for claim in ("We have long admired your work.", "We have admired your work for years."):
            draft = good_draft()
            draft['body'] = "Hi Jane,\n\n" + claim + "\n\nBest,\n[Your Name]"
            reasons = review_draft(draft)
            self.assertTrue(any('rapport' in reason and 'body' in reason for reason in reasons), claim)
        draft = good_draft()
        draft['body'] = "Hi Jane,\n\nWe admire your 45 years of fabrication work.\n\nBest,\n[Your Name]"
        self.assertIn('body uses generic praise or corporate filler', review_draft(draft))

    def test_evidence_based_and_prospective_statements_not_flagged(self):
        clean_statements = (
            "Palatine Welding has over 45 years in metal fabrication.",
            "Your family-owned company has operated since 1973.",
            "I would be interested in learning more about your apprenticeship program.",
            "We noticed Swiss Automation's commitment to the community.",
            "We are interested in your work in aerospace.",
        )
        for statement in clean_statements:
            draft = good_draft()
            draft['body'] = signed_body(statement)
            self.assertEqual(review_draft(draft), [], statement)

    def test_regression_original_plural_rapport_cases_still_flag(self):
        for claim in (
            "We have followed Palatine Welding's work for over 45 years.",
            "We are neighbors and long-time admirers of Swiss Automation, Inc.",
        ):
            draft = good_draft()
            draft['body'] = "Hi Jane,\n\n" + claim + "\n\nBest,\n[Your Name]"
            reasons = review_draft(draft)
            self.assertTrue(any('rapport' in reason and 'body' in reason for reason in reasons), claim)

    def test_company_giving_is_paraphrased_without_fundraising_terms(self):
        for statement in (
            "Your company has provided CNC equipment to Elgin Community College.",
            "Your company has a history of supporting technical education in the community.",
            "Your company supports local STEM education.",
        ):
            draft = good_draft()
            draft['body'] = signed_body(statement)
            self.assertEqual(review_draft(draft), [], statement)
        draft = good_draft()
        draft['body'] = "Hi Jane,\n\nYour donation of CNC equipment caught our attention.\n\nBest,\n[Your Name]"
        self.assertIn('body uses fundraising language in a first-contact sequence', review_draft(draft))

    def test_team_money_asks_still_flagged(self):
        asks = (
            "Please donate to our team.",
            "We are asking for a donation.",
            "Would you consider a donation to Team 0000?",
            "We are seeking donations.",
            "Please consider donating.",
            "We would appreciate a donation.",
            "Could your CNC team sponsor Team 0000?",
            "Would you sponsor our team?",
            "We are not asking for money yet.",
            "There is no pressure to give money now.",
        )
        for ask in asks:
            draft = good_draft()
            draft['body'] = "Hi Jane,\n\n" + ask + "\n\nBest,\n[Your Name]"
            reasons = review_draft(draft)
            self.assertIn('body makes a hard money ask', reasons, ask)

    def test_followup_money_ask_is_flagged(self):
        draft = good_draft()
        draft['followup_body'] = 'Following up to ask whether you would sponsor our team.\n\nBest,\n[Your Name]'
        self.assertIn('followup_body makes a hard money ask', review_draft(draft))

    def test_first_contact_fundraising_terms_are_flagged_in_every_field(self):
        for field in ('subject', 'body', 'linkedin_note', 'followup_body'):
            draft = good_draft()
            draft[field] += ' Future sponsorship.'
            self.assertIn(field + ' uses fundraising language in a first-contact sequence', review_draft(draft), field)

    def test_generic_filler_and_vague_greetings_are_flagged(self):
        draft = good_draft()
        draft['body'] = draft['body'].replace('I noticed', 'I was impressed and noticed')
        self.assertIn('body uses generic praise or corporate filler', review_draft(draft))
        draft = good_draft()
        draft['body'] = draft['body'].replace('Hello Jane,', 'Hello,')
        self.assertIn('body uses a vague greeting instead of a verified name or company team', review_draft(draft))

    def test_channel_limits_and_multiple_questions_are_flagged(self):
        draft = good_draft()
        draft['subject'] = 'A' * 56
        self.assertIn('subject is longer than 55 characters', review_draft(draft))
        draft = good_draft()
        draft['linkedin_note'] = 'A' * 281
        self.assertIn('linkedin_note is longer than 280 characters', review_draft(draft))
        draft = good_draft()
        draft['body'] += ' Could we also visit?'
        self.assertIn('body contains more than one question', review_draft(draft))

    def test_followup_cannot_invent_send_time(self):
        draft = good_draft()
        draft['followup_body'] = draft['followup_body'].replace('my earlier message', 'my message last week')
        self.assertIn('followup_body invents when the earlier message was sent', review_draft(draft))

    def test_first_person_singular_rapport_flagged(self):
        claims = (
            "I've been following Swiss Automation's work.",
            "I have followed your company for years.",
            "I have long admired your work.",
            "My team has worked with you before.",
            "I have known your team for years.",
        )
        for claim in claims:
            draft = good_draft()
            draft['body'] = "Hi Jane,\n\n" + claim + "\n\nBest,\n[Your Name]"
            reasons = review_draft(draft)
            self.assertTrue(any('rapport' in reason and 'body' in reason for reason in reasons), claim)

    def test_first_person_singular_legitimate_language_not_flagged(self):
        clean_statements = (
            "I am following up on my note from last week.",
            "I noticed your apprenticeship program.",
            "I am interested in your work in aerospace.",
            "I would be interested in learning more about your program.",
            "Following up on my earlier message.",
        )
        for statement in clean_statements:
            draft = good_draft()
            draft['body'] = signed_body(statement)
            self.assertEqual(review_draft(draft), [], statement)

if __name__ == '__main__':
    unittest.main()
