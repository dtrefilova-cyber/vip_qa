-- Хто завантажив VIP-дзвінок + контекст відділу (окремо від Retention).
-- Застосувати вручну в Supabase SQL editor.

ALTER TABLE vip_short_call_logs
    ADD COLUMN IF NOT EXISTS qa_manager text,
    ADD COLUMN IF NOT EXISTS ret_manager text,
    ADD COLUMN IF NOT EXISTS project text,
    ADD COLUMN IF NOT EXISTS tl_name text,
    ADD COLUMN IF NOT EXISTS department text DEFAULT 'VIP';

CREATE INDEX IF NOT EXISTS vip_short_call_logs_qa_manager_idx
    ON vip_short_call_logs (qa_manager);

CREATE INDEX IF NOT EXISTS vip_short_call_logs_department_check_date_idx
    ON vip_short_call_logs (department, check_date DESC);
