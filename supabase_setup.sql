-- Rode este script no SQL Editor do painel do Supabase (projeto novo, free tier)
-- depois de criar o projeto em https://supabase.com

create extension if not exists pgcrypto;

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    username text unique not null,
    password_hash text not null,
    display_name text,
    created_at timestamptz not null default now(),
    failed_login_attempts int not null default 0,
    locked_until timestamptz
);

-- Re-running this file on an existing project is safe; these no-op if the columns already exist.
alter table users add column if not exists failed_login_attempts int not null default 0;
alter table users add column if not exists locked_until timestamptz;

create table if not exists attempts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    username text not null,
    created_at timestamptz not null default now(),
    mode text,
    language_version text,
    topic_filter text,
    total_questions int not null,
    correct_count int not null,
    score_pct numeric not null,
    topic_scores jsonb not null default '{}'::jsonb,
    answers jsonb
);

create index if not exists attempts_username_idx on attempts (username, created_at);

create table if not exists questions (
    id uuid primary key default gen_random_uuid(),
    version text not null,
    enunciado text not null,
    alternativas jsonb not null,
    resposta_correta text not null,
    explicacao text,
    tema text not null default 'General',
    referencia jsonb,
    added_by text,
    created_at timestamptz not null default now()
);

create index if not exists questions_version_idx on questions (version);

-- Security: the app only ever talks to Supabase using the service_role key
-- (server-side, never exposed to the browser), which bypasses RLS entirely.
-- Enabling RLS with zero policies blocks all access via the public anon key
-- without affecting the app, closing the "publicly accessible table" warning.
alter table users enable row level security;
alter table attempts enable row level security;
alter table questions enable row level security;
