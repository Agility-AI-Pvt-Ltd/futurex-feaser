import unittest
from unittest.mock import Mock, patch

import core.qdrant_client as qdrant_client


class QdrantClientConfigTests(unittest.TestCase):
    def tearDown(self):
        qdrant_client.close_qdrant_clients()

    @patch("core.qdrant_client._resolve_writable_qdrant_path")
    @patch("qdrant_client.QdrantClient")
    @patch("core.qdrant_client.settings")
    def test_remote_backend_uses_url_and_ignores_local_path(
        self,
        mock_settings,
        mock_qdrant_client,
        mock_resolve_path,
    ):
        mock_settings.qdrant_enabled = True
        mock_settings.qdrant_backend = "remote"
        mock_settings.QDRANT_URL = "http://qdrant-nlb.example.internal:6333"
        mock_settings.QDRANT_CLOUD_URL = ""
        mock_settings.QDRANT_API_KEY = ""
        mock_settings.QDRANT_CLOUD_API_KEY = ""

        client = Mock()
        mock_qdrant_client.return_value = client

        result = qdrant_client.get_local_qdrant_client("/data/qdrant")

        self.assertIs(result, client)
        mock_qdrant_client.assert_called_once_with(
            url="http://qdrant-nlb.example.internal:6333",
            api_key=None,
        )
        mock_resolve_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
