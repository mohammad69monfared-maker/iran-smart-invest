begin;

create schema if not exists investment_private;
revoke all on schema investment_private from public;
grant usage on schema investment_private to authenticated;
create table investment_private.report_readers (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);
alter table investment_private.report_readers enable row level security;
create function investment_private.can_read_report() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(select from investment_private.report_readers where owner_id = (select auth.uid()))
$$;
revoke all on function investment_private.can_read_report() from public, anon;
grant execute on function investment_private.can_read_report() to authenticated;

create table public.analysis_runs (
  id text primary key check (length(id) between 1 and 150),
  report_date date not null,
  report jsonb not null check (jsonb_typeof(report) = 'object'),
  created_at timestamptz not null default now()
);
create index analysis_runs_date_idx on public.analysis_runs(report_date desc);
create table public.daily_reports (
  report_date date primary key,
  run_id text not null references public.analysis_runs(id),
  report jsonb not null check (jsonb_typeof(report) = 'object'),
  updated_at timestamptz not null default now()
);
create function public.publish_daily_report(p_date date, p_report jsonb, p_run_id text default null)
returns void language plpgsql set search_path = '' as $$
declare
  run_key text := coalesce(p_run_id, p_date::text || '-' || md5(p_report::text));
  saved public.analysis_runs%rowtype;
begin
  if p_report is null or jsonb_typeof(p_report) <> 'object' or p_report = '{}'::jsonb then
    raise exception 'A report object is required';
  end if;
  insert into public.analysis_runs(id,report_date,report) values(run_key,p_date,p_report)
    on conflict (id) do nothing;
  select * into strict saved from public.analysis_runs where id = run_key;
  if saved.report_date <> p_date or saved.report <> p_report then
    raise exception 'Run identifier belongs to a different report';
  end if;
  insert into public.daily_reports(report_date,run_id,report,updated_at)
    values(p_date,run_key,p_report,saved.created_at)
    on conflict (report_date) do update set run_id=excluded.run_id,report=excluded.report,
      updated_at=excluded.updated_at where public.daily_reports.updated_at < excluded.updated_at;
end $$;
revoke all on function public.publish_daily_report(date,jsonb,text) from public,anon,authenticated;
grant execute on function public.publish_daily_report(date,jsonb,text) to service_role;

create table public.portfolios (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 100),
  created_at timestamptz not null default now(),
  unique(owner_id,name)
);
create table public.portfolio_transactions (
  id uuid primary key default gen_random_uuid(),
  portfolio_id uuid not null references public.portfolios(id) on delete cascade,
  symbol_id text not null check (length(trim(symbol_id)) between 1 and 80),
  side text not null check(side in ('buy','sell')),
  quantity bigint not null check(quantity between 1 and 1000000000000),
  price numeric not null check(price > 0 and price < 1e18),
  fee numeric not null default 0 check(fee >= 0 and fee < 1e18),
  traded_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  check(side <> 'sell' or fee <= price * quantity)
);
create index transactions_history_idx on public.portfolio_transactions(portfolio_id,symbol_id,traded_at desc);
create table public.portfolio_positions (
  portfolio_id uuid not null references public.portfolios(id) on delete cascade,
  symbol_id text not null, quantity bigint not null default 0 check(quantity >= 0),
  cost_basis numeric not null default 0 check(cost_basis >= 0),
  realized_pnl numeric not null default 0,
  updated_at timestamptz not null,
  primary key(portfolio_id,symbol_id)
);
create function investment_private.book_trade() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  pos public.portfolio_positions%rowtype;
  sold_cost numeric;
begin
  if new.traded_at > clock_timestamp() then raise exception 'Future trade time'; end if;
  insert into public.portfolio_positions(portfolio_id,symbol_id,updated_at)
    values(new.portfolio_id,new.symbol_id,new.traded_at) on conflict do nothing;
  select * into strict pos from public.portfolio_positions
    where portfolio_id=new.portfolio_id and symbol_id=new.symbol_id for update;
  if new.traded_at < pos.updated_at then raise exception 'Enter trades in chronological order'; end if;
  if new.side='buy' then
    pos.quantity := pos.quantity + new.quantity;
    pos.cost_basis := pos.cost_basis + new.quantity * new.price + new.fee;
  else
    if new.quantity > pos.quantity then raise exception 'Insufficient shares'; end if;
    sold_cost := case when pos.quantity=new.quantity then pos.cost_basis
                      else (pos.cost_basis * new.quantity) / pos.quantity end;
    pos.quantity := pos.quantity - new.quantity;
    pos.cost_basis := pos.cost_basis - sold_cost;
    pos.realized_pnl := pos.realized_pnl + new.quantity * new.price - new.fee - sold_cost;
  end if;
  update public.portfolio_positions set quantity=pos.quantity, cost_basis=pos.cost_basis,
    realized_pnl=pos.realized_pnl, updated_at=new.traded_at
    where portfolio_id=new.portfolio_id and symbol_id=new.symbol_id;
  return new;
end $$;
revoke all on function investment_private.book_trade() from public, anon, authenticated;
create trigger book_trade after insert on public.portfolio_transactions
for each row execute function investment_private.book_trade();

create table public.watchlists (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  symbol_id text not null check(length(trim(symbol_id)) between 1 and 80),
  alert_price numeric check(alert_price > 0 and alert_price < 1e18),
  created_at timestamptz not null default now(), unique(owner_id,symbol_id)
);
create table public.alerts (
  id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
  symbol_id text, message text not null check(length(message) between 1 and 4000),
  is_read boolean not null default false, created_at timestamptz not null default now()
);
create index alerts_owner_date_idx on public.alerts(owner_id,created_at desc);
create table public.app_settings (
  owner_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  settings jsonb not null default '{}' check(jsonb_typeof(settings)='object'),
  updated_at timestamptz not null default now()
);
create function investment_private.touch_settings() returns trigger language plpgsql set search_path='' as $$
begin new.updated_at := now(); return new; end $$;
create trigger touch_settings before update on public.app_settings
for each row execute function investment_private.touch_settings();

do $$
declare tab text;
begin
  foreach tab in array array['analysis_runs','daily_reports','portfolios','portfolio_transactions',
    'portfolio_positions','watchlists','alerts','app_settings'] loop
    execute format('alter table public.%I enable row level security',tab);
    execute format('revoke all on table public.%I from public, anon, authenticated',tab);
    execute format('grant select on table public.%I to authenticated',tab);
    execute format('grant select, insert, update, delete on table public.%I to service_role',tab);
  end loop;
  foreach tab in array array['analysis_runs','daily_reports'] loop
    execute format('create policy operator_reads on public.%I for select to authenticated using ((select investment_private.can_read_report()))',tab);
  end loop;
  foreach tab in array array['portfolios','watchlists','alerts','app_settings'] loop
    execute format('create policy owner_rows on public.%I to authenticated using (owner_id=(select auth.uid())) with check (owner_id=(select auth.uid()))', tab);
  end loop;
end $$;
create policy owned_trades on public.portfolio_transactions to authenticated using
  (exists(select from public.portfolios p where p.id=portfolio_id and p.owner_id=(select auth.uid())))
  with check (exists(select from public.portfolios p where p.id=portfolio_id and p.owner_id=(select auth.uid())));
create policy owned_positions on public.portfolio_positions for select to authenticated using
  (exists(select from public.portfolios p where p.id=portfolio_id and p.owner_id=(select auth.uid())));
grant insert(id,owner_id,name), update(name) on public.portfolios to authenticated;
grant insert(id,portfolio_id,symbol_id,side,quantity,price,fee,traded_at) on public.portfolio_transactions to authenticated;
grant insert(id,owner_id,symbol_id,alert_price),update(alert_price,symbol_id),delete on public.watchlists to authenticated;
grant insert(owner_id,settings),update(owner_id,settings) on public.app_settings to authenticated;
grant update(is_read) on public.alerts to authenticated;
commit;
