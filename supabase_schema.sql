create table if not exists public.user_dashboards (
    user_id uuid not null references auth.users (id) on delete cascade,
    profile_key text not null,
    payload jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default timezone('utc', now()),
    primary key (user_id, profile_key)
);

create or replace function public.set_user_dashboards_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

drop trigger if exists set_user_dashboards_updated_at on public.user_dashboards;

create trigger set_user_dashboards_updated_at
before update on public.user_dashboards
for each row
execute function public.set_user_dashboards_updated_at();

alter table public.user_dashboards enable row level security;

grant usage on schema public to authenticated;
grant select, insert, update on table public.user_dashboards to authenticated;

drop policy if exists "Users can read their own dashboards" on public.user_dashboards;
create policy "Users can read their own dashboards"
on public.user_dashboards
for select
using (auth.uid() = user_id);

drop policy if exists "Users can insert their own dashboards" on public.user_dashboards;
create policy "Users can insert their own dashboards"
on public.user_dashboards
for insert
with check (auth.uid() = user_id);

drop policy if exists "Users can update their own dashboards" on public.user_dashboards;
create policy "Users can update their own dashboards"
on public.user_dashboards
for update
using (auth.uid() = user_id)
with check (auth.uid() = user_id);
