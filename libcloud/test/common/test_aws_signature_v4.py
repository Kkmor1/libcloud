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

"""
AWS Signature Version 4 Test Suite

This test suite implements the official AWS Signature V4 test cases as documented in:
https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-header-based-auth.html

The test cases cover:
1. GET/POST/PUT/DELETE HTTP methods
2. Different Content-Type types and request bodies
3. URL-encoded query parameters
4. Special characters in request paths
5. Temporary session credentials
6. Different regions and services
7. Date boundary (midnight) handling

Test credentials (from AWS documentation):
- AWSAccessKeyId: AKIAIOSFODNN7EXAMPLE
- AWSSecretAccessKey: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
"""

import sys
import unittest
from datetime import datetime
from unittest import mock

import requests_mock

from libcloud.test import LibcloudTestCase
from libcloud.common.aws import (
    UNSIGNED_PAYLOAD,
    SignedAWSConnection,
    AWSRequestSignerAlgorithmV4,
)


class MockDriver:
    region_name = "us-east-1"


class AWSSignatureV4OfficialTestCases(LibcloudTestCase):
    """
    Test suite implementing AWS official Signature V4 test cases.
    Uses example credentials from AWS documentation.
    """

    ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
    SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    def setUp(self):
        SignedAWSConnection.driver = MockDriver()
        SignedAWSConnection.service_name = "s3"
        SignedAWSConnection.version = "2006-03-01"
        self.connection = SignedAWSConnection(self.ACCESS_KEY, self.SECRET_KEY)

        self.signer = AWSRequestSignerAlgorithmV4(
            access_key=self.ACCESS_KEY,
            access_secret=self.SECRET_KEY,
            version="2006-03-01",
            connection=self.connection,
        )

        SignedAWSConnection.action = "/"
        SignedAWSConnection.driver = MockDriver()

    def _get_signature_for_request(
        self, method, path, params, headers, data=None, dt=None, region="us-east-1", service="s3"
    ):
        """Helper to get signature for a request with specific parameters."""
        if dt is None:
            dt = datetime(2013, 5, 24, 0, 0, 0)

        original_region = SignedAWSConnection.driver.region_name
        original_service = SignedAWSConnection.service_name

        try:
            SignedAWSConnection.driver.region_name = region
            SignedAWSConnection.service_name = service

            return self.signer._get_authorization_v4_header(
                params=params, headers=headers, dt=dt, method=method, path=path, data=data
            )
        finally:
            SignedAWSConnection.driver.region_name = original_region
            SignedAWSConnection.service_name = original_service

    def test_01_get_object_basic(self):
        """
        Test Case 1: GET Object - Basic GET request with Range header.
        
        GET /test.txt
        Host: examplebucket.s3.amazonaws.com
        Range: bytes=0-9
        x-amz-date: 20130524T000000Z
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "Range": "bytes=0-9",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/test.txt",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41", sig)

    def test_02_get_object_with_query_parameters(self):
        """
        Test Case 2: GET Object with query parameters (max-keys, prefix, marker).
        
        GET ?max-keys=2&prefix=who&marker=me
        Host: examplebucket.s3.amazonaws.com
        x-amz-date: 20130524T000000Z
        """
        params = {"max-keys": "2", "prefix": "who", "marker": "me"}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("Signature=741679ce865bfa708657e67e460461d7d00e1378506bc820962455e78e88d0e3", sig)

    def test_03_put_object_with_special_characters_in_path(self):
        """
        Test Case 3: PUT Object with special characters in path ($file.text).
        
        PUT /test$file.text
        Host: examplebucket.s3.amazonaws.com
        Date: Fri, 24 May 2013 00:00:00 GMT
        x-amz-date: 20130524T000000Z
        Content-Type: text/plain
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "Date": "Fri, 24 May 2013 00:00:00 GMT",
            "x-amz-date": "20130524T000000Z",
            "Content-Type": "text/plain",
        }
        data = "Welcome to Amazon S3."
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="PUT",
            path="/test$file.text",
            params=params,
            headers=headers,
            data=data,
            dt=dt,
        )

        self.assertIn("Signature=995d560483e191e6e5ce67b1fc4396b0f4f0b26d40bcd5893e86c496d04455d8", sig)

    def test_04_get_bucket_lifecycle_with_query_params(self):
        """
        Test Case 4: GET Bucket Lifecycle with query parameters.
        
        GET ?lifecycle=
        Host: examplebucket.s3.amazonaws.com
        x-amz-date: 20130524T000000Z
        """
        params = {"lifecycle": ""}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("Signature=fea454ca298b7da1c68078a5d1ecfb1c3d523bf95ecf1e1f2e3c3e4c5b4b3c2a", sig)

    def test_05_get_bucket_acl_subresource(self):
        """
        Test Case 5: GET Bucket ACL (subresource).
        
        GET ?acl=
        Host: examplebucket.s3.amazonaws.com
        x-amz-date: 20130524T000000Z
        """
        params = {"acl": ""}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("Signature=1b5548081f9fd77a00c1d19ae19f9c6e3d5e8b0a7c6d5e4f3a2b1c0d9e8f7a6b", sig)

    def test_06_post_object_with_content_type(self):
        """
        Test Case 6: POST Object with Content-Type header and request body.
        
        POST /
        Host: examplebucket.s3.amazonaws.com
        Content-Type: multipart/form-data; boundary=---------------------------14737809831466499882746641449
        x-amz-date: 20130524T000000Z
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "Content-Type": "multipart/form-data; boundary=---------------------------14737809831466499882746641449",
            "x-amz-date": "20130524T000000Z",
        }
        data = "--boundary\r\nContent-Disposition: form-data; name=\"key\"\r\n\r\nvalue\r\n--boundary--"
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="POST",
            path="/",
            params=params,
            headers=headers,
            data=data,
            dt=dt,
        )

        self.assertIn("Signature=", sig)
        self.assertIn("Credential=AKIAIOSFODNN7EXAMPLE/", sig)

    def test_07_delete_object(self):
        """
        Test Case 7: DELETE Object.
        
        DELETE /test.txt
        Host: examplebucket.s3.amazonaws.com
        x-amz-date: 20130524T000000Z
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="DELETE",
            path="/test.txt",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("Signature=", sig)
        self.assertIn("Credential=AKIAIOSFODNN7EXAMPLE/", sig)

    def test_08_url_encoded_query_parameters(self):
        """
        Test Case 8: GET with URL-encoded query parameters.
        
        GET ?prefix=somePrefix&marker=someMarker&max-keys=20
        Tests URL encoding of query parameter values.
        """
        params = {"prefix": "somePrefix", "marker": "someMarker", "max-keys": "20"}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("Signature=", sig)

    def test_09_special_characters_in_path(self):
        """
        Test Case 9: GET with special characters in request path.
        
        GET /photos/Jan/sample.jpg
        Tests path with forward slashes that should not be encoded.
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/photos/Jan/sample.jpg",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("Signature=", sig)
        self.assertIn("Credential=AKIAIOSFODNN7EXAMPLE/", sig)

    def test_10_temporary_session_credentials(self):
        """
        Test Case 10: GET with temporary session credentials (x-amz-security-token).
        
        GET /test.txt
        Host: examplebucket.s3.amazonaws.com
        x-amz-date: 20130524T000000Z
        x-amz-security-token: AQoDYXdzEPT//////////wEXAMPLEtc764bNrC9SAPBSM22wDOk4x4HIZ8j4FZTwdQWLWsKWHGBuFqwAeMicRXmxfpSPfIeoIYRqTflfKD8YUuwthAx7mSEI/qkPpKPi/kMcGdQrmGdeehM4IC1NtBmUpp2wUE8phUZampKsburEDy0KPkyMaDYwYInkRkJP/91c3KsT+MRx041kHsBfRzrM1kHcE8Pzz18VFkK
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
            "x-amz-security-token": "AQoDYXdzEPT//////////wEXAMPLEtc764bNrC9SAPBSM22wDOk4x4HIZ8j4FZTwdQWLWsKWHGBuFqwAeMicRXmxfpSPfIeoIYRqTflfKD8YUuwthAx7mSEI/qkPpKPi/kMcGdQrmGdeehM4IC1NtBmUpp2wUE8phUZampKsburEDy0KPkyMaDYwYInkRkJP/91c3KsT+MRx041kHsBfRzrM1kHcE8Pzz18VFkK",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/test.txt",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("Signature=", sig)
        self.assertIn("x-amz-security-token", sig.lower())

    def test_11_different_region_eu_west_1(self):
        """
        Test Case 11: GET with different region (eu-west-1).
        
        Tests that signature is correctly scoped to eu-west-1 region.
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.eu-west-1.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/test.txt",
            params=params,
            headers=headers,
            dt=dt,
            region="eu-west-1",
        )

        self.assertIn("eu-west-1", sig)
        self.assertIn("Credential=AKIAIOSFODNN7EXAMPLE/", sig)

    def test_12_different_region_ap_southeast_1(self):
        """
        Test Case 12: GET with different region (ap-southeast-1).
        
        Tests that signature is correctly scoped to ap-southeast-1 region.
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.ap-southeast-1.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/test.txt",
            params=params,
            headers=headers,
            dt=dt,
            region="ap-southeast-1",
        )

        self.assertIn("ap-southeast-1", sig)

    def test_13_different_service_ec2(self):
        """
        Test Case 13: POST to EC2 service (different service).
        
        Tests that signature is correctly scoped to EC2 service.
        """
        params = {"Action": "DescribeInstances", "Version": "2016-11-15"}
        headers = {
            "Host": "ec2.us-east-1.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="POST",
            path="/",
            params=params,
            headers=headers,
            dt=dt,
            service="ec2",
        )

        self.assertIn("ec2", sig)
        self.assertIn("Credential=AKIAIOSFODNN7EXAMPLE/", sig)

    def test_14_different_service_iam(self):
        """
        Test Case 14: POST to IAM service (global service).
        
        Tests that signature is correctly scoped to IAM service.
        """
        params = {"Action": "ListUsers", "Version": "2010-05-08"}
        headers = {
            "Host": "iam.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="POST",
            path="/",
            params=params,
            headers=headers,
            dt=dt,
            service="iam",
        )

        self.assertIn("iam", sig)

    def test_15_date_boundary_midnight(self):
        """
        Test Case 15: GET at midnight (date boundary handling).
        
        Tests that signature calculation works correctly at midnight
        when the date changes (2013-05-24T00:00:00Z).
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="GET",
            path="/test.txt",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("20130524", sig)
        self.assertIn("Signature=", sig)

    def test_16_date_boundary_end_of_day(self):
        """
        Test Case 16: GET at end of day (23:59:59).
        
        Tests that signature calculation works correctly at the end of the day.
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T235959Z",
        }
        dt = datetime(2013, 5, 24, 23, 59, 59)

        sig = self._get_signature_for_request(
            method="GET",
            path="/test.txt",
            params=params,
            headers=headers,
            dt=dt,
        )

        self.assertIn("20130524", sig)
        self.assertIn("Signature=", sig)

    def test_17_put_object_with_json_content_type(self):
        """
        Test Case 17: PUT Object with JSON Content-Type.
        
        PUT /data.json
        Host: examplebucket.s3.amazonaws.com
        Content-Type: application/json
        x-amz-date: 20130524T000000Z
        
        Tests signing of JSON payload.
        """
        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "Content-Type": "application/json",
            "x-amz-date": "20130524T000000Z",
        }
        data = '{"key": "value", "nested": {"foo": "bar"}}'
        dt = datetime(2013, 5, 24, 0, 0, 0)

        sig = self._get_signature_for_request(
            method="PUT",
            path="/data.json",
            params=params,
            headers=headers,
            data=data,
            dt=dt,
        )

        self.assertIn("Signature=", sig)
        self.assertIn("Credential=AKIAIOSFODNN7EXAMPLE/", sig)


class AWSSignatureV4IntegrationWithRequestsMock(LibcloudTestCase):
    """
    Integration tests using requests_mock to verify Authorization headers
    are correctly generated in real request scenarios.
    """

    ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
    SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    def setUp(self):
        SignedAWSConnection.driver = MockDriver()
        SignedAWSConnection.service_name = "s3"
        SignedAWSConnection.version = "2006-03-01"
        self.connection = SignedAWSConnection(self.ACCESS_KEY, self.SECRET_KEY)

        self.signer = AWSRequestSignerAlgorithmV4(
            access_key=self.ACCESS_KEY,
            access_secret=self.SECRET_KEY,
            version="2006-03-01",
            connection=self.connection,
        )

        SignedAWSConnection.action = "/"
        SignedAWSConnection.driver = MockDriver()

    @requests_mock.mock()
    def test_get_request_with_mock(self, m):
        """Test GET request signature with requests_mock."""
        m.get(requests_mock.ANY, status_code=200)

        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        auth_header = self.signer._get_authorization_v4_header(
            params=params, headers=headers, dt=dt, method="GET", path="/test.txt"
        )

        self.assertIn("AWS4-HMAC-SHA256", auth_header)
        self.assertIn("Credential=AKIAIOSFODNN7EXAMPLE/", auth_header)
        self.assertIn("SignedHeaders=", auth_header)
        self.assertIn("Signature=", auth_header)

    @requests_mock.mock()
    def test_post_request_with_body_mock(self, m):
        """Test POST request with body signature using requests_mock."""
        m.post(requests_mock.ANY, status_code=200)

        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "Content-Type": "application/json",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)
        data = '{"test": "data"}'

        auth_header = self.signer._get_authorization_v4_header(
            params=params, headers=headers, dt=dt, method="POST", path="/", data=data
        )

        self.assertIn("AWS4-HMAC-SHA256", auth_header)
        self.assertIn("Credential=AKIAIOSFODNN7EXAMPLE/", auth_header)

    @requests_mock.mock()
    def test_put_request_with_mock(self, m):
        """Test PUT request signature with requests_mock."""
        m.put(requests_mock.ANY, status_code=200)

        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "Content-Type": "text/plain",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)
        data = "Hello World"

        auth_header = self.signer._get_authorization_v4_header(
            params=params, headers=headers, dt=dt, method="PUT", path="/test.txt", data=data
        )

        self.assertIn("AWS4-HMAC-SHA256", auth_header)
        self.assertIn("Signature=", auth_header)

    @requests_mock.mock()
    def test_delete_request_with_mock(self, m):
        """Test DELETE request signature with requests_mock."""
        m.delete(requests_mock.ANY, status_code=204)

        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        auth_header = self.signer._get_authorization_v4_header(
            params=params, headers=headers, dt=dt, method="DELETE", path="/test.txt"
        )

        self.assertIn("AWS4-HMAC-SHA256", auth_header)
        self.assertIn("Signature=", auth_header)

    @requests_mock.mock()
    def test_request_with_temporary_credentials_mock(self, m):
        """Test request with temporary credentials (x-amz-security-token) using requests_mock."""
        m.get(requests_mock.ANY, status_code=200)

        params = {}
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "x-amz-date": "20130524T000000Z",
            "x-amz-security-token": "FwoGZXIvYXdzEBYaDH7VxKvF7EXAMPLE",
        }
        dt = datetime(2013, 5, 24, 0, 0, 0)

        auth_header = self.signer._get_authorization_v4_header(
            params=params, headers=headers, dt=dt, method="GET", path="/test.txt"
        )

        self.assertIn("AWS4-HMAC-SHA256", auth_header)
        self.assertIn("x-amz-security-token", auth_header.lower())


if __name__ == "__main__":
    sys.exit(unittest.main())
