-- Optional migration for VIP scored rubric (run in Supabase SQL editor).
-- Historical GREEN/RED rows stay valid; new columns are nullable.

ALTER TABLE vip_short_call_logs
    ADD COLUMN IF NOT EXISTS call_type text,
    ADD COLUMN IF NOT EXISTS rubric_version text,
    ADD COLUMN IF NOT EXISTS criteria_facts jsonb,
    ADD COLUMN IF NOT EXISTS criteria_scores jsonb,
    ADD COLUMN IF NOT EXISTS total_score numeric,
    ADD COLUMN IF NOT EXISTS max_score numeric,
    ADD COLUMN IF NOT EXISTS percent numeric,
    ADD COLUMN IF NOT EXISTS is_critical_fail boolean DEFAULT false;
