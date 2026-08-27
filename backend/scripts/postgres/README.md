# Postgres / Supabase schema scripts

These are **not** the default setup path. Storage defaults to local SQLite and
is initialised with `python scripts/init_db.py`; see `CLAUDE.md`.

They apply `src/db/schema.sql` to a Postgres instance and exist for the
eventual move off SQLite (`SAAF_DB_BACKEND=supabase`). They were sitting in
`scripts/` alongside `init_db.py`, where they read as the setup path they no
longer are.
