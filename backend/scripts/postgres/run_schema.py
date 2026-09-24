"""Legacy entry point; hosted schema changes use versioned migrations."""

raise SystemExit(
    "Run 'supabase db push --dry-run' then 'supabase db push' from the repository "
    "root after linking your project. SQL files live in supabase/migrations/."
)
