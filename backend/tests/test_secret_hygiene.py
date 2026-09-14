from scripts.check_secrets import scan_file


def test_detects_credentials_without_echoing_values(tmp_path):
    google_key = "AIza" + ("A" * 35)
    supabase_key = "sb_" + "secret_" + ("B" * 24)
    env_example = tmp_path / ".env.example"
    env_example.write_text(
        f"GEMINI_API_KEY={google_key}\nSUPABASE_KEY={supabase_key}\n",
        encoding="utf-8",
    )

    findings = scan_file(env_example, tmp_path)

    assert findings == [
        (".env.example", 1, "Google API key"),
        (".env.example", 2, "Supabase secret key"),
        (".env.example", 1, "non-placeholder example value"),
        (".env.example", 2, "non-placeholder example value"),
    ]
    assert google_key not in repr(findings)
    assert supabase_key not in repr(findings)


def test_accepts_secret_placeholders(tmp_path):
    env_example = tmp_path / ".env.example"
    env_example.write_text(
        "GEMINI_API_KEY=YOUR_GEMINI_API_KEY\n"
        "# SUPABASE_KEY=YOUR_SERVER_SECRET_OR_SERVICE_ROLE_KEY\n"
        "# REVALIDATE_SECRET=GENERATE_A_LONG_RANDOM_SECRET\n",
        encoding="utf-8",
    )

    assert scan_file(env_example, tmp_path) == []
