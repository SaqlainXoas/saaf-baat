"""
Tests for embedding parsing behavior in SupabaseClient.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.db.client import SupabaseClient


def test_get_articles_without_clusters_parses_embedding_vector():
    """Ensure embedding string from DB is parsed to list[float]."""
    with patch.dict("os.environ", {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_KEY": "test-key"}):
        client = SupabaseClient(test_mode=True)

    # Mock Supabase response with embedding as Postgres vector string
    response = MagicMock()
    response.data = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "source": "dawn",
            "url": "https://dawn.com/news/1",
            "headline": "Test",
            "main_text": "Text " * 20,
            "embedding": "[0.1,0.2,0.3]",
        }
    ]

    table_mock = MagicMock()
    table_mock.select.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = response

    with patch.object(client, "_client", MagicMock()):
        client._client.table.return_value = table_mock
        articles = client.get_articles_without_clusters()

    assert len(articles) == 1
    assert isinstance(articles[0].embedding, list)
    assert articles[0].embedding == [0.1, 0.2, 0.3]
