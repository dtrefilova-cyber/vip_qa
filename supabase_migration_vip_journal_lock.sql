-- Лок блоку журналу (TTL 60 с) і унікальний ключ дзвінка.
-- Застосувати вручну в Supabase. Скрипт нічого не виконує сам.

CREATE TABLE IF NOT EXISTS vip_journal_locks (
    lock_key text PRIMARY KEY,
    owner text,
    expires_at timestamptz NOT NULL
);

ALTER TABLE vip_journal_writes ADD COLUMN IF NOT EXISTS client_id text;
ALTER TABLE vip_journal_writes ADD COLUMN IF NOT EXISTS call_date date;
ALTER TABLE vip_journal_writes ADD COLUMN IF NOT EXISTS manager text;
ALTER TABLE vip_journal_writes ADD COLUMN IF NOT EXISTS status text;
ALTER TABLE vip_journal_writes ADD COLUMN IF NOT EXISTS payload jsonb;
ALTER TABLE vip_journal_writes ADD COLUMN IF NOT EXISTS actual jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS vip_journal_writes_call_key_idx
    ON vip_journal_writes (project, call_type, client_id, call_date, manager);
