from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.app import create_app


def test_sources_route_reads_config(tmp_path, monkeypatch):
    sources_yaml = tmp_path / "sources.yaml"
    sources_yaml.write_text(
        """
sources:
  dawn:
    url: "https://www.dawn.com"
    feed_url: "https://www.dawn.com/feeds/latest-news"
    sections: ["latest-news"]
    enabled: true
  tribune:
    url: "https://tribune.com.pk"
    feed_url: "https://tribune.com.pk/rss.xml"
    sections: ["latest"]
    enabled: false
scraping_config:
  max_articles_per_source: 50
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("SAAF_SOURCES_YAML", str(sources_yaml))

    app = create_app()
    client = TestClient(app)

    res = client.get("/api/sources")
    assert res.status_code == 200
    payload = res.json()
    assert [s["name"] for s in payload] == ["dawn", "tribune"]
    assert payload[0]["enabled"] is True
