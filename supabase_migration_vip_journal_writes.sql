-- Дедуп записів журналу VIP (analysis_id → рядок у Google Sheets).
-- Застосувати вручну в Supabase SQL editor.

CREATE TABLE IF NOT EXISTS vip_journal_writes (
    analysis_id text PRIMARY KEY,
    spreadsheet_id text NOT NULL,
    sheet_id bigint,
    sheet_title text,
    call_type text NOT NULL,
    row integer NOT NULL,
    project text,
    written_at timestamptz,
    is_critical_fail boolean DEFAULT false,
    critical_reasons jsonb DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS vip_journal_writes_project_type_idx
    ON vip_journal_writes (project, call_type);
