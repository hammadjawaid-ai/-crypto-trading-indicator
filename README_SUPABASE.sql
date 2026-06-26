-- ===========================================================================
-- DURABLE CLOSED-TRADE STORAGE — Supabase setup (one-time)
-- ===========================================================================
-- Streamlit Cloud wipes local files on every redeploy. This table makes the
-- closed-trade history permanent and readable directly in Supabase.
--
-- STEPS:
--   1. supabase.com → New project (free tier is fine).
--   2. SQL Editor → paste + run everything below.
--   3. Project Settings → API → copy the "Project URL" and the
--      "service_role" key (NOT the anon key — service_role bypasses RLS so
--      the server can read/write; it stays server-side in Streamlit secrets).
--   4. Streamlit secrets (app dashboard → Settings → Secrets, OR local
--      .streamlit/secrets.toml):
--          SUPABASE_URL = "https://xxxx.supabase.co"
--          SUPABASE_KEY = "eyJ... (service_role key)"
--   5. Reboot the app. Closed trades now persist + appear in
--      Table Editor → closed_trades.
-- ===========================================================================

create table if not exists closed_trades (
    id          text primary key,        -- "{bot}|{symbol}|{exit_at}"
    bot         text not null,           -- 'paper' | 'sureshot' | 'live'
    symbol      text,
    base        text,
    side        text,
    entry       double precision,
    exit        double precision,
    pnl_usd     double precision,
    pnl_pct     double precision,
    qty         double precision,
    opened_at   double precision,        -- epoch seconds
    exit_at     double precision,        -- epoch seconds
    reason      text,
    raw         jsonb,                   -- full trade dict (nothing lost)
    created_at  timestamptz default now()
);

create index if not exists closed_trades_bot_exit_idx
    on closed_trades (bot, exit_at desc);

-- The service_role key bypasses Row Level Security, so no policies are
-- needed. (If you instead used the anon key you'd have to add RLS policies.)
