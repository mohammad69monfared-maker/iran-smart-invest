-- Market reports contain no user data. Allow the installed apps to show the
-- latest report without forcing every reader to sign in first.
begin;

do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public'
                 and tablename='daily_reports' and policyname='anon_reads_reports') then
    create policy anon_reads_reports on public.daily_reports
      for select to anon using (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public'
                 and tablename='analysis_runs' and policyname='anon_reads_runs') then
    create policy anon_reads_runs on public.analysis_runs
      for select to anon using (true);
  end if;
end $$;

grant select on public.daily_reports, public.analysis_runs to anon;

commit;
