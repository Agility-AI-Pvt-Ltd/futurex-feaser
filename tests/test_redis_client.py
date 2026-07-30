import unittest
from unittest.mock import Mock, patch

import core.redis_client as redis_client


class RedisClientTests(unittest.TestCase):
    def tearDown(self):
        redis_client._redis_client = None

    @patch("core.redis_client.settings")
    @patch("core.redis_client.aioredis")
    def test_get_redis_uses_bounded_blocking_pool(self, mock_aioredis, mock_settings):
        mock_settings.redis_enabled = True
        mock_settings.REDIS_REQUIRED = False
        mock_settings.REDIS_URL = "redis://example.com:6379/0"
        mock_settings.REDIS_MAX_CONNECTIONS = 12
        mock_settings.REDIS_POOL_TIMEOUT_SECONDS = 4.0
        mock_settings.REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS = 2.0
        mock_settings.REDIS_SOCKET_TIMEOUT_SECONDS = 2.5
        mock_settings.REDIS_HEALTH_CHECK_INTERVAL_SECONDS = 15

        mock_pool = Mock()
        mock_client = Mock()
        mock_aioredis.BlockingConnectionPool.from_url.return_value = mock_pool
        mock_aioredis.Redis.return_value = mock_client

        client = redis_client.get_redis()

        self.assertIs(client, mock_client)
        mock_aioredis.BlockingConnectionPool.from_url.assert_called_once_with(
            "redis://example.com:6379/0",
            decode_responses=True,
            max_connections=12,
            timeout=4.0,
            socket_connect_timeout=2.0,
            socket_timeout=2.5,
            health_check_interval=15,
        )
        mock_aioredis.Redis.assert_called_once_with(connection_pool=mock_pool)


if __name__ == "__main__":
    unittest.main()
