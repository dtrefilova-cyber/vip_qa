-- Optional migration for VIP scored rubric (run in Supabase SQL editor).
-- Historical GREEN/RED rows stay valid; new columns are nullable.
-- Verdict CHECK must allow both legacy colors and the new scored rubric.

ALTER TABLE vip_short_call_logs
    ADD COLUMN IF NOT EXISTS call_type text,
    ADD COLUMN IF NOT EXISTS rubric_version text,
    ADD COLUMN IF NOT EXISTS criteria_facts jsonb,
    ADD COLUMN IF NOT EXISTS criteria_scores jsonb,
    ADD COLUMN IF NOT EXISTS total_score numeric,
    ADD COLUMN IF NOT EXISTS max_score numeric,
    ADD COLUMN IF NOT EXISTS percent numeric,
    ADD COLUMN IF NOT EXISTS is_critical_fail boolean DEFAULT false,
    -- Дата перевірки (UI «Дата перевірки») — окремо від дати самого дзвінка call_date
    ADD COLUMN IF NOT EXISTS check_date date;

CREATE INDEX IF NOT EXISTS vip_short_call_logs_check_date_idx
    ON vip_short_call_logs (check_date DESC);

-- Values actually used by the app / historical rows:
--   scored — core/vip_scoring_common.ScoringResult.to_dict()
--   GREEN / RED — legacy uppercase (common CHECK / Sheets-era)
--   green / red — lowercase as read/normalized in archive & analytics
ALTER TABLE vip_short_call_logs
    DROP CONSTRAINT IF EXISTS vip_short_call_logs_verdict_check;

ALTER TABLE vip_short_call_logs
    ADD CONSTRAINT vip_short_call_logs_verdict_check
    CHECK (verdict IS NULL OR verdict IN ('GREEN', 'RED', 'green', 'red', 'scored'));
