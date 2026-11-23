-- Run after the migration in a disposable Supabase database. All writes roll back.
begin;
insert into auth.users(id) values ('00000000-0000-4000-b001-000000000001'),('00000000-0000-4000-b001-000000000002');
insert into investment_private.report_readers(owner_id) values ('00000000-0000-4000-b001-000000000001');
set local role service_role;
select public.publish_daily_report('2020-01-02','{"status":"test"}','test-rls-daily');
select public.publish_daily_report('2020-01-02','{"status":"test"}','test-rls-daily');
reset role;
set local role authenticated;
select set_config('request.jwt.claim.sub','00000000-0000-4000-b001-000000000001',true);
insert into public.portfolios(id,name) values ('00000000-0000-4000-b001-000000000003','Test');
insert into public.portfolio_transactions(portfolio_id,symbol_id,side,quantity,price,fee,traded_at) values
 ('00000000-0000-4000-b001-000000000003','T','buy',10,100,10,'2020-01-01T00:00:00Z');
insert into public.portfolio_transactions(portfolio_id,symbol_id,side,quantity,price,fee,traded_at) values
 ('00000000-0000-4000-b001-000000000003','T','sell',4,120,2,'2020-01-02T00:00:00Z');
do $$ begin
  if not exists(select from public.daily_reports where run_id='test-rls-daily') then raise exception 'Reader cannot see report'; end if;
  if not exists(select from public.portfolio_positions where portfolio_id='00000000-0000-4000-b001-000000000003' and quantity=6 and cost_basis=606 and realized_pnl=74) then
    raise exception 'Incorrect fees or moving cost basis';
  end if;
  begin
    insert into public.portfolio_transactions(portfolio_id,symbol_id,side,quantity,price) values
      ('00000000-0000-4000-b001-000000000003','T','sell',7,120);
    raise exception 'Oversell unexpectedly allowed';
  exception when raise_exception then
    if sqlerrm <> 'Insufficient shares' then raise; end if;
  end;
end $$;
select set_config('request.jwt.claim.sub','00000000-0000-4000-b001-000000000002',true);
do $$ begin
  if exists(select from public.portfolios where id='00000000-0000-4000-b001-000000000003')
    or exists(select from public.portfolio_positions where portfolio_id='00000000-0000-4000-b001-000000000003')
    or exists(select from public.portfolio_transactions where portfolio_id='00000000-0000-4000-b001-000000000003')
    or exists(select from public.daily_reports where run_id='test-rls-daily') then
    raise exception 'Non-owner can read private records';
  end if;
  begin
    insert into public.portfolio_transactions(portfolio_id,symbol_id,side,quantity,price)
    values ('00000000-0000-4000-b001-000000000003','T','buy',1,1);
    raise exception 'Other user can write private transactions';
  exception when insufficient_privilege then null; end;
  begin
    perform public.publish_daily_report('2020-01-02','{"forged":true}','forged');
    raise exception 'Authenticated account can publish reports';
  exception when insufficient_privilege then null; end;
end $$;
rollback;
