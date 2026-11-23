-- Supplemental schema: market data provenance, fundamentals, signals, backtests.
-- Heavy OHLCV history is archived locally in SQLite (see engine/reporting.py);
-- only compact observations and derived records are synchronized here.
begin;

create table public.user_profiles (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  display_name text check (display_name is null or length(trim(display_name)) between 1 and 80),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.market_symbols (
  code text primary key check (length(trim(code)) between 1 and 40),
  symbol text not null check (length(trim(symbol)) between 1 and 80),
  name text,
  sector text,
  flow numeric,
  updated_at timestamptz not null default now()
);
create index market_symbols_symbol_idx on public.market_symbols(symbol);

create table public.market_daily_prices (
  code text not null references public.market_symbols(code) on delete cascade,
  day date not null,
  open numeric, high numeric, low numeric,
  close numeric, raw_close numeric, adjusted_close numeric,
  volume numeric check (volume is null or volume >= 0),
  value numeric check (value is null or value >= 0),
  source text not null,
  fetched_at timestamptz not null,
  valid boolean not null default true,
  completeness numeric check (completeness is null or completeness between 0 and 1),
  primary key (code, day)
);
create index market_daily_prices_day_idx on public.market_daily_prices(day desc);

create table public.market_intraday_snapshots (
  code text not null references public.market_symbols(code) on delete cascade,
  observed_at timestamptz not null,
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  source text not null,
  primary key (code, observed_at)
);
create index market_intraday_observed_idx on public.market_intraday_snapshots(observed_at desc);

create table public.market_fundamentals (
  symbol text not null check (length(trim(symbol)) between 1 and 80),
  period text not null check (length(trim(period)) between 4 and 20),
  metrics jsonb not null check (jsonb_typeof(metrics) = 'object'),
  published_at text,
  source text not null,
  fetched_at timestamptz not null default now(),
  primary key (symbol, period)
);

create table public.financial_disclosures (
  tracking_number text primary key,
  symbol text not null check (length(trim(symbol)) between 1 and 80),
  title text not null check (length(trim(title)) between 1 and 1000),
  published_at text,
  url text check (url is null or url like 'https://codal.ir/%' or url like 'https://www.codal.ir/%'),
  audited boolean,
  fetched_at timestamptz not null default now()
);
create index disclosures_symbol_date_idx on public.financial_disclosures(symbol, published_at desc);

create table public.data_sources (
  name text primary key check (length(trim(name)) between 1 and 80),
  description text,
  enabled boolean not null default true,
  last_checked_at timestamptz
);

create table public.data_quality_logs (
  id bigint generated always as identity primary key,
  source text not null,
  symbol text,
  day date,
  valid boolean not null,
  completeness numeric check (completeness between 0 and 1),
  errors jsonb not null default '[]'::jsonb check (jsonb_typeof(errors) = 'array'),
  fetched_at timestamptz not null default now()
);
create index data_quality_source_day_idx on public.data_quality_logs(source, day desc);
create index data_quality_symbol_idx on public.data_quality_logs(symbol, day desc);

create table public.strategies (
  id text primary key check (length(trim(id)) between 1 and 120),
  name text not null check (length(trim(name)) between 1 and 200),
  description text,
  created_at timestamptz not null default now()
);
create table public.strategy_versions (
  id text primary key check (length(trim(id)) between 1 and 160),
  strategy_id text not null references public.strategies(id) on delete cascade,
  parameters jsonb not null check (jsonb_typeof(parameters) = 'object'),
  created_at timestamptz not null default now()
);
create index strategy_versions_strategy_idx on public.strategy_versions(strategy_id, created_at desc);

create table public.signals (
  id text primary key check (length(trim(id)) between 1 and 100),
  version_id text not null references public.strategy_versions(id),
  symbol text not null check (length(trim(symbol)) between 1 and 80),
  signal_date date not null,
  score numeric check (score is null or score between 0 and 100),
  entry_low numeric check (entry_low is null or entry_low > 0),
  entry_high numeric check (entry_high is null or entry_high >= entry_low),
  stop_loss numeric check (stop_loss is null or stop_loss > 0),
  target1 numeric check (target1 is null or target1 > entry_high),
  target2 numeric check (target2 is null or target2 >= target1),
  status text not null default 'مشروط',
  expires date not null,
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  created_at timestamptz not null default now(),
  check (expires >= signal_date)
);
create index signals_date_idx on public.signals(signal_date desc);
create index signals_symbol_idx on public.signals(symbol, signal_date desc);

create table public.signal_events (
  id bigint generated always as identity primary key,
  signal_id text not null references public.signals(id) on delete cascade,
  kind text not null check (kind in ('pending','open','invalidated','expired','stop','target')),
  event_date date not null,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  created_at timestamptz not null default now(),
  unique (signal_id, kind, event_date)
);
create index signal_events_signal_idx on public.signal_events(signal_id, event_date);

create table public.notification_deliveries (
  id bigint generated always as identity primary key,
  channel text not null check (channel in ('telegram','local','cloud')),
  recipient text,
  subject text,
  status text not null check (status in ('sent','failed','skipped')),
  delivered_at timestamptz not null default now()
);
create index notification_deliveries_date_idx on public.notification_deliveries(delivered_at desc);

create table public.backtest_runs (
  id text primary key check (length(trim(id)) between 1 and 120),
  symbol text not null check (length(trim(symbol)) between 1 and 80),
  parameters jsonb not null check (jsonb_typeof(parameters) = 'object'),
  metrics jsonb not null check (jsonb_typeof(metrics) = 'object'),
  created_at timestamptz not null default now()
);
create index backtest_runs_symbol_idx on public.backtest_runs(symbol, created_at desc);

create table public.backtest_trades (
  id bigint generated always as identity primary key,
  run_id text not null references public.backtest_runs(id) on delete cascade,
  symbol text not null,
  entry_date date not null,
  exit_date date not null,
  net_return numeric not null,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  check (exit_date >= entry_date)
);
create index backtest_trades_run_idx on public.backtest_trades(run_id);

-- Reference/derived tables are readable by signed-in users; only the server
-- role may write them. Personal profile rows are restricted to their owner.
do $$
declare tab text;
begin
  foreach tab in array array[
    'market_symbols','market_daily_prices','market_intraday_snapshots',
    'market_fundamentals','financial_disclosures','data_sources',
    'data_quality_logs','strategies','strategy_versions','signals',
    'signal_events','notification_deliveries','backtest_runs','backtest_trades'
  ] loop
    execute format('alter table public.%I enable row level security', tab);
    execute format('revoke all on table public.%I from public, anon, authenticated', tab);
    execute format('grant select on table public.%I to authenticated', tab);
    execute format('grant all on table public.%I to service_role', tab);
    execute format('create policy read_reference on public.%I for select to authenticated using (true)', tab);
  end loop;
end $$;

alter table public.user_profiles enable row level security;
revoke all on table public.user_profiles from public, anon, authenticated;
grant select, insert, update on table public.user_profiles to authenticated;
grant all on table public.user_profiles to service_role;
create policy own_profile on public.user_profiles to authenticated
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

commit;
