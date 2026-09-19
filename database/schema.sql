CREATE SCHEMA IF NOT EXISTS n8n;
CREATE SCHEMA IF NOT EXISTS fundraising;
SET search_path TO fundraising;
CREATE TABLE IF NOT EXISTS companies (
 id BIGSERIAL PRIMARY KEY, domain TEXT NOT NULL UNIQUE, company_name TEXT NOT NULL,
 homepage_url TEXT NOT NULL, industry TEXT, location TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS leads (
 id BIGSERIAL PRIMARY KEY, company_id BIGINT NOT NULL UNIQUE REFERENCES companies(id),
 scout_relevance BOOLEAN, scout_confidence DOUBLE PRECISION CHECK (scout_confidence BETWEEN 0 AND 1), scout_reason TEXT,
 research_summary TEXT, geographic_fit INTEGER CHECK (geographic_fit BETWEEN 0 AND 20),
 technical_relevance INTEGER CHECK (technical_relevance BETWEEN 0 AND 20), stem_alignment INTEGER CHECK (stem_alignment BETWEEN 0 AND 20),
 company_capacity INTEGER CHECK (company_capacity BETWEEN 0 AND 15), education_connection INTEGER CHECK (education_connection BETWEEN 0 AND 10),
 contactability INTEGER CHECK (contactability BETWEEN 0 AND 10), in_kind_value INTEGER CHECK (in_kind_value BETWEEN 0 AND 5),
 overall_score INTEGER CHECK (overall_score BETWEEN 0 AND 100), tier INTEGER CHECK (tier BETWEEN 1 AND 4),
 suggested_cash_ask TEXT, in_kind_opportunities JSONB NOT NULL DEFAULT '[]', target_contact_roles JSONB NOT NULL DEFAULT '[]', outreach_angle TEXT,
 status TEXT NOT NULL DEFAULT 'discovered' CHECK (status IN ('discovered','screening','skipped','scout_failed','ready','researching','research_failed','researched','drafting','draft_failed','needs_review')),
 attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, stage_started_at TIMESTAMPTZ,
 discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(), researched_at TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CONSTRAINT coherent_scores CHECK (
   (geographic_fit IS NULL AND technical_relevance IS NULL AND stem_alignment IS NULL AND company_capacity IS NULL AND education_connection IS NULL AND contactability IS NULL AND in_kind_value IS NULL AND overall_score IS NULL AND tier IS NULL)
   OR (geographic_fit IS NOT NULL AND technical_relevance IS NOT NULL AND stem_alignment IS NOT NULL AND company_capacity IS NOT NULL AND education_connection IS NOT NULL AND contactability IS NOT NULL AND in_kind_value IS NOT NULL AND overall_score IS NOT NULL AND tier IS NOT NULL)
 ),
 CHECK (overall_score IS NULL OR overall_score = geographic_fit + technical_relevance + stem_alignment + company_capacity + education_connection + contactability + in_kind_value),
 CHECK (overall_score IS NULL OR tier = CASE WHEN overall_score >= 85 THEN 1 WHEN overall_score >= 70 THEN 2 WHEN overall_score >= 55 THEN 3 ELSE 4 END)
);
CREATE TABLE IF NOT EXISTS evidence (
 id BIGSERIAL PRIMARY KEY, lead_id BIGINT NOT NULL REFERENCES leads(id), company_id BIGINT NOT NULL REFERENCES companies(id),
 claim TEXT NOT NULL, source_url TEXT NOT NULL, source_title TEXT, excerpt TEXT NOT NULL,
 retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS contacts (
 id BIGSERIAL PRIMARY KEY, company_id BIGINT NOT NULL REFERENCES companies(id),
 name TEXT, title TEXT, email TEXT, public_profile_url TEXT, source_url TEXT NOT NULL, excerpt TEXT NOT NULL,
 confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1), verification_status TEXT NOT NULL DEFAULT 'public_source_matched',
 UNIQUE(company_id, source_url, email, name)
);
CREATE TABLE IF NOT EXISTS email_drafts (
 id BIGSERIAL PRIMARY KEY, lead_id BIGINT NOT NULL UNIQUE REFERENCES leads(id), contact_id BIGINT REFERENCES contacts(id),
 subject TEXT NOT NULL, body TEXT NOT NULL, linkedin_note TEXT NOT NULL, followup_body TEXT NOT NULL,
 draft_status TEXT NOT NULL DEFAULT 'needs_review', approved BOOLEAN NOT NULL DEFAULT false, approved_by TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CHECK (NOT approved OR approved_by IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS leads_status_idx ON leads(status);
CREATE INDEX IF NOT EXISTS leads_score_idx ON leads(overall_score DESC);
CREATE INDEX IF NOT EXISTS evidence_lead_idx ON evidence(lead_id);
CREATE INDEX IF NOT EXISTS contacts_company_idx ON contacts(company_id);
CREATE INDEX IF NOT EXISTS drafts_lead_idx ON email_drafts(lead_id);

CREATE TABLE IF NOT EXISTS telegram_commands (
 update_id BIGINT PRIMARY KEY, message_id BIGINT NOT NULL, chat_id BIGINT NOT NULL,
 command TEXT NOT NULL CHECK (command IN ('search','draft','status')),
 query TEXT, lead_id BIGINT,
 claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 CHECK ((command='draft' AND lead_id IS NOT NULL AND query IS NULL)
     OR (command='search' AND lead_id IS NULL)
     OR (command='status' AND lead_id IS NULL AND query IS NULL))
);

CREATE TABLE IF NOT EXISTS telegram_poll_state (
 id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id=1),
 next_offset BIGINT NOT NULL DEFAULT -1 CHECK (next_offset>=-1),
 initialized BOOLEAN NOT NULL DEFAULT false,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='coherent_scores' AND conrelid='fundraising.leads'::regclass) THEN
  ALTER TABLE fundraising.leads ADD CONSTRAINT coherent_scores CHECK (
   num_nonnulls(geographic_fit,technical_relevance,stem_alignment,company_capacity,education_connection,contactability,in_kind_value,overall_score,tier) IN (0,9)
  );
 END IF;
END $$;
