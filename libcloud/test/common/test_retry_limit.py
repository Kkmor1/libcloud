# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io
import ssl
import socket
import asyncio
import logging
from unittest.mock import Mock, MagicMock, patch

from libcloud.test import unittest
from libcloud.common.base import Connection
from libcloud.utils.retry import TRANSIENT_SSL_ERROR, retry_on_exception

CONFLICT_RESPONSE_STATUS = [
    ("status", "429"),
    ("reason", "CONFLICT"),
    ("retry_after", "3"),
    ("content-type", "application/json"),
]
SIMPLE_RESPONSE_STATUS = ("HTTP/1.1", 429, "CONFLICT")


@patch("os.environ", {"LIBCLOUD_RETRY_FAILED_HTTP_REQUESTS": True})
class FailedRequestRetryTestCase(unittest.TestCase):
    def test_retry_connection(self):
        con = Connection(timeout=0.2, retry_delay=0.1)
        con.connection = Mock()
        connect_method = "libcloud.common.base.Connection.request"

        with patch(connect_method) as mock_connect:
            try:
                mock_connect.side_effect = socket.gaierror("")
                con.request("/")
            except socket.gaierror:
                pass

    def test_retry_connection_ssl_error(self):
        conn = Connection(timeout=0.2, retry_delay=0.1)

        with patch.object(conn, "connect", Mock()):
            with patch.object(conn, "connection") as connection:
                connection.request = MagicMock(
                    __name__="request", side_effect=ssl.SSLError(TRANSIENT_SSL_ERROR)
                )

                self.assertRaises(ssl.SSLError, conn.request, "/")
                self.assertGreater(connection.request.call_count, 1)


class RetryOnExceptionTestCase(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("libcloud.utils.retry")
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.old_level = self.logger.level
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.old_level)

    def test_retry_on_exception_sync_execution_count(self):
        self.assertEqual(self._run_sync_retry(0), 1)
        self.assertEqual(self._run_sync_retry(1), 1)
        self.assertEqual(self._run_sync_retry(3), 3)

    def test_retry_on_exception_async_execution_count(self):
        self.assertEqual(self._run_async_retry(0), 1)
        self.assertEqual(self._run_async_retry(1), 1)
        self.assertEqual(self._run_async_retry(3), 3)

    def test_retry_on_exception_logs_retry_details(self):
        self._run_sync_retry(3)
        log_output = self.stream.getvalue()

        self.assertIn("Retrying sync_fail (1/3)", log_output)
        self.assertIn("Retrying sync_fail (2/3)", log_output)
        self.assertIn("ValueError('sync boom')", log_output)

    def _run_sync_retry(self, max_retries):
        counter = {"count": 0}

        @retry_on_exception(exception_types=ValueError, max_retries=max_retries, retry_delay=0)
        def sync_fail():
            counter["count"] += 1
            raise ValueError("sync boom")

        with self.assertRaises(ValueError):
            sync_fail()

        return counter["count"]

    def _run_async_retry(self, max_retries):
        counter = {"count": 0}

        @retry_on_exception(exception_types=ValueError, max_retries=max_retries, retry_delay=0)
        async def async_fail():
            counter["count"] += 1
            raise ValueError("async boom")

        with self.assertRaises(ValueError):
            asyncio.run(async_fail())

        return counter["count"]


if __name__ == "__main__":
    unittest.main()
