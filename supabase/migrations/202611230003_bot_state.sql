-- Telegram bot runtime state shared between workflow runs.
begin;

create table public.telegram_bot_state (
  id text primary key check (length(trim(id)) between 1 and 40),
  cursor bigint not null default 0 check (cursor >= 0),
  updated_at timestamptz not null default now()
);

alter table public.telegram_bot_state enable row level security;
revoke all on table public.telegram_bot_state from public, anon, authenticated;
grant all on table public.telegram_bot_state to service_role;

commit;
