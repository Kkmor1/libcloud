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

import sys
import hmac
import hashlib
from datetime import datetime
from collections import OrderedDict
from urllib.parse import quote, parse_qsl, urlsplit
from unittest import mock

import requests
import requests_mock

from libcloud.test import LibcloudTestCase, unittest
from libcloud.common.aws import UNSIGNED_PAYLOAD, SignedAWSConnection, AWSRequestSignerAlgorithmV4


class EC2MockDriver:
    region_name = "my_region"


class FakeDriver:
    def __init__(self, region_name):
        self.region_name = region_name


class FakeConnection:
    def __init__(self, host, region_name, service_name, secure=True, port=443):
        self.host = host
        self.driver = FakeDriver(region_name=region_name)
        self.service_name = service_name
        self.secure = secure
        self.port = port


OFFICIAL_SIGNATURE_V4_CASES = [
    {
        "name": "get-vanilla",
        "request": "GET / HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "get-vanilla-query-order-key",
        "request": "GET /?Param1=value2&Param1=Value1 HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=eedbc4e291e521cf13422ffca22be7d2eb8146eecf653089df300a15b2382bd1",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "get-vanilla-query-order-key-case",
        "request": "GET /?Param2=value2&Param1=value1 HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=b97d918cfa904a5beff61c982a1b6f458b799221646efd99d3219ec94cdf2500",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "get-vanilla-query-order-value",
        "request": "GET /?Param1=value2&Param1=value1 HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=5772eed61e12b33fae39ee5e7012498b51d56abc0abb7c60486157bd471c4694",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "get-vanilla-query-unreserved",
        "request": "GET /?-._~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz=-._~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=9c3e54bfcdf0b19771a7f523ee5669cdf59bc7cc0884027167c21bb143a40197",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "get-header-key-duplicate",
        "request": "GET / HTTP/1.1\nHost:example.amazonaws.com\nMy-Header1:value2\nMy-Header1:value2\nMy-Header1:value1\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;my-header1;x-amz-date, Signature=c9d5ea9f3f72853aea855b47ea873832890dbdd183b4468f858259531a5138ea",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "get-header-value-order",
        "request": "GET / HTTP/1.1\nHost:example.amazonaws.com\nMy-Header1:value4\nMy-Header1:value1\nMy-Header1:value3\nMy-Header1:value2\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;my-header1;x-amz-date, Signature=08c7e5a9acfcfeb3ab6b2185e75ce8b1deb5e634ec47601a50643f830c755c01",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "get-header-value-trim",
        "request": "GET / HTTP/1.1\nHost:example.amazonaws.com\nMy-Header1: value1\nMy-Header2: \"a   b   c\"\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;my-header1;my-header2;x-amz-date, Signature=acc3ed3afb60bb290fc8d2dd0098b9911fcaa05412b367055dee359757a9c736",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "get-unreserved",
        "request": "GET /-._~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=07ef7494c76fa4850883e2b006601f940f8a34d404d0cfa977f52a65bbf5f24f",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "normalize-path-get-relative",
        "request": "GET /example/.. HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "normalize-path-get-space",
        "request": "GET /example space/ HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=652487583200325589f1fba4c7e578f72c47cb61beeca81406b39ddec1366741",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "post-vanilla",
        "request": "POST / HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=5da7c1a2acd57cee7505fc6676e4e544621c30862966e37dddb68e92efbe5d6b",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "post-x-www-form-urlencoded",
        "request": "POST / HTTP/1.1\nContent-Type:application/x-www-form-urlencoded\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n\nParam1=value1",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=content-type;host;x-amz-date, Signature=ff11897932ad3f4e8b18135d722051e5ac45fc38421b1da7b9d196a0fe09473a",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "post-sts-header-before",
        "request": "POST / HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\nX-Amz-Security-Token:AQoDYXdzEPT//////////wEXAMPLEtc764bNrC9SAPBSM22wDOk4x4HIZ8j4FZTwdQWLWsKWHGBuFqwAeMicRXmxfpSPfIeoIYRqTflfKD8YUuwthAx7mSEI/qkPpKPi/kMcGdQrmGdeehM4IC1NtBmUpp2wUE8phUZampKsburEDy0KPkyQDYwT7WZ0wq5VSXDvp75YU9HFvlRd8Tx6q6fE8YQcHNVXAkiY9q6d+xo0rKwT38xVqr7ZD0u0iPPkUL64lIZbqBAz+scqKmlzm8FDrypNC9Yjc8fPOLn9FX9KSYvKTr4rvx3iSIlTJabIQwj2ICCR/oLxBA==\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date;x-amz-security-token, Signature=85d96828115b5dc0cfc3bd16ad9e210dd772bbebba041836c64533a82be05ead",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "post-sts-header-after",
        "request": "POST / HTTP/1.1\nHost:example.amazonaws.com\nX-Amz-Date:20150830T123600Z\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, SignedHeaders=host;x-amz-date, Signature=5da7c1a2acd57cee7505fc6676e4e544621c30862966e37dddb68e92efbe5d6b",
        "host": "example.amazonaws.com",
        "region": "us-east-1",
        "service": "service",
        "access_key": "AKIDEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
        "transport_only_headers": {
            "X-Amz-Security-Token": "AQoDYXdzEPT//////////wEXAMPLEtc764bNrC9SAPBSM22wDOk4x4HIZ8j4FZTwdQWLWsKWHGBuFqwAeMicRXmxfpSPfIeoIYRqTflfKD8YUuwthAx7mSEI/qkPpKPi/kMcGdQrmGdeehM4IC1NtBmUpp2wUE8phUZampKsburEDy0KPkyQDYwT7WZ0wq5VSXDvp75YU9HFvlRd8Tx6q6fE8YQcHNVXAkiY9q6d+xo0rKwT38xVqr7ZD0u0iPPkUL64lIZbqBAz+scqKmlzm8FDrypNC9Yjc8fPOLn9FX9KSYvKTr4rvx3iSIlTJabIQwj2ICCR/oLxBA=="
        },
    },
    {
        "name": "s3-get-object",
        "request": "GET /test.txt HTTP/1.1\nHost:examplebucket.s3.amazonaws.com\nRange:bytes=0-9\nX-Amz-Date:20130524T000000Z\nX-Amz-Content-SHA256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41",
        "host": "examplebucket.s3.amazonaws.com",
        "region": "us-east-1",
        "service": "s3",
        "access_key": "AKIAIOSFODNN7EXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    },
    {
        "name": "s3-put-object",
        "request": "PUT /test$file.text HTTP/1.1\nHost:examplebucket.s3.amazonaws.com\nDate:Fri, 24 May 2013 00:00:00 GMT\nX-Amz-Date:20130524T000000Z\nX-Amz-Storage-Class:REDUCED_REDUNDANCY\nX-Amz-Content-SHA256:44ce7dd67c959e0d3524ffac1771dfbba87d2b6b4b4e99e42034a8b803f8b072\n",
        "expected_authorization": "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, SignedHeaders=date;host;x-amz-content-sha256;x-amz-date;x-amz-storage-class, Signature=98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd",
        "host": "examplebucket.s3.amazonaws.com",
        "region": "us-east-1",
        "service": "s3",
        "access_key": "AKIAIOSFODNN7EXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    },
]


REFERENCE_ONLY_CASES = [
    {
        "name": "delete-midnight-execute-api",
        "request": "DELETE /orders/%E2%9C%93?filter=blue%20green&mode=strict HTTP/1.1\nHost:api.example.amazonaws.com\nContent-Type:application/json\nX-Amz-Date:20240229T000000Z\n",
        "host": "api.example.amazonaws.com",
        "region": "eu-west-1",
        "service": "execute-api",
        "access_key": "AKIDDELETEEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYDELETEKEY",
    },
    {
        "name": "post-json-codepipeline",
        "request": 'POST / HTTP/1.1\nHost:codepipeline.us-west-2.amazonaws.com\nContent-Type:application/x-amz-json-1.1\nX-Amz-Date:20240601T235959Z\nX-Amz-Target:CodePipeline_20150709.ListPipelines\n\n{"maxResults":1}',
        "host": "codepipeline.us-west-2.amazonaws.com",
        "region": "us-west-2",
        "service": "codepipeline",
        "access_key": "AKIDJSONEXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYJSONEXAMPLE",
    },
]


class AWSRequestSignerAlgorithmV4TestCase(LibcloudTestCase):
    def setUp(self):
        SignedAWSConnection.driver = EC2MockDriver()
        SignedAWSConnection.service_name = "my_service"
        SignedAWSConnection.version = "2013-10-15"
        self.connection = SignedAWSConnection("my_key", "my_secret")

        self.signer = AWSRequestSignerAlgorithmV4(
            access_key="my_key",
            access_secret="my_secret",
            version="2013-10-15",
            connection=self.connection,
        )

        SignedAWSConnection.action = "/my_action/"
        SignedAWSConnection.driver = EC2MockDriver()

        self.now = datetime(2015, 3, 4, hour=17, minute=34, second=52)

    def test_v4_signature(self):
        params = {"Action": "DescribeInstances", "Version": "2013-10-15"}
        headers = {
            "Host": "ec2.eu-west-1.amazonaws.com",
            "Accept-Encoding": "gzip,deflate",
            "X-AMZ-Date": "20150304T173452Z",
            "User-Agent": "libcloud/0.17.0 (Amazon EC2 (eu-central-1)) ",
        }
        dt = self.now
        sig = self.signer._get_authorization_v4_header(
            params=params, headers=headers, dt=dt, method="GET", path="/my_action/"
        )
        self.assertEqual(
            sig,
            "AWS4-HMAC-SHA256 "
            "Credential=my_key/20150304/my_region/my_service/aws4_request, "
            "SignedHeaders=accept-encoding;host;user-agent;x-amz-date, "
            "Signature=f9868f8414b3c3f856c7955019cc1691265541f5162b9b772d26044280d39bd3",
        )

    def test_v4_signature_contains_user_id(self):
        sig = self.signer._get_authorization_v4_header(params={}, headers={}, dt=self.now)
        self.assertIn("Credential=my_key/", sig)

    def test_v4_signature_contains_credential_scope(self):
        with mock.patch(
            "libcloud.common.aws.AWSRequestSignerAlgorithmV4._get_credential_scope"
        ) as mock_get_creds:
            mock_get_creds.return_value = "my_credential_scope"
            sig = self.signer._get_authorization_v4_header(params={}, headers={}, dt=self.now)

        self.assertIn("Credential=my_key/my_credential_scope, ", sig)

    def test_v4_signature_contains_signed_headers(self):
        with mock.patch(
            "libcloud.common.aws.AWSRequestSignerAlgorithmV4._get_signed_headers"
        ) as mock_get_headers:
            mock_get_headers.return_value = "my_signed_headers"
            sig = self.signer._get_authorization_v4_header({}, {}, self.now, method="GET", path="/")
        self.assertIn("SignedHeaders=my_signed_headers, ", sig)

    def test_v4_signature_contains_signature(self):
        with mock.patch(
            "libcloud.common.aws.AWSRequestSignerAlgorithmV4._get_signature"
        ) as mock_get_signature:
            mock_get_signature.return_value = "my_signature"
            sig = self.signer._get_authorization_v4_header({}, {}, self.now)
        self.assertIn("Signature=my_signature", sig)

    def test_get_signature_(self):
        def _sign(key, msg, hex=False):
            if hex:
                return "H|{}|{}".format(key, msg)
            else:
                return "{}|{}".format(key, msg)

        with mock.patch(
            "libcloud.common.aws.AWSRequestSignerAlgorithmV4._get_key_to_sign_with"
        ) as mock_get_key:
            with mock.patch(
                "libcloud.common.aws.AWSRequestSignerAlgorithmV4._get_string_to_sign"
            ) as mock_get_string:
                with mock.patch("libcloud.common.aws._sign", new=_sign):
                    mock_get_key.return_value = "my_signing_key"
                    mock_get_string.return_value = "my_string_to_sign"
                    sig = self.signer._get_signature(
                        {}, {}, self.now, method="GET", path="/", data=None
                    )

        self.assertEqual(sig, "H|my_signing_key|my_string_to_sign")

    def test_get_string_to_sign(self):
        with mock.patch("hashlib.sha256") as mock_sha256:
            mock_sha256.return_value.hexdigest.return_value = "chksum_of_canonical_request"
            to_sign = self.signer._get_string_to_sign(
                {}, {}, self.now, method="GET", path="/", data=None
            )

        self.assertEqual(
            to_sign,
            "AWS4-HMAC-SHA256\n"
            "20150304T173452Z\n"
            "20150304/my_region/my_service/aws4_request\n"
            "chksum_of_canonical_request",
        )

    def test_get_key_to_sign_with(self):
        def _sign(key, msg, hex=False):
            return "{}|{}".format(key, msg)

        with mock.patch("libcloud.common.aws._sign", new=_sign):
            key = self.signer._get_key_to_sign_with(self.now)

        self.assertEqual(key, "AWS4my_secret|20150304|my_region|my_service|aws4_request")

    def test_get_signed_headers_contains_all_headers_lowercased(self):
        headers = {
            "Content-Type": "text/plain",
            "Host": "my_host",
            "X-Special-Header": "",
        }
        signed_headers = self.signer._get_signed_headers(headers)

        self.assertIn("content-type", signed_headers)
        self.assertIn("host", signed_headers)
        self.assertIn("x-special-header", signed_headers)

    def test_get_signed_headers_concats_headers_sorted_lexically(self):
        headers = {
            "Host": "my_host",
            "X-Special-Header": "",
            "1St-Header": "2",
            "Content-Type": "text/plain",
        }
        signed_headers = self.signer._get_signed_headers(headers)

        self.assertEqual(signed_headers, "1st-header;content-type;host;x-special-header")

    def test_get_credential_scope(self):
        scope = self.signer._get_credential_scope(self.now)
        self.assertEqual(scope, "20150304/my_region/my_service/aws4_request")

    def test_get_canonical_headers_joins_all_headers(self):
        headers = {
            "accept-encoding": "gzip,deflate",
            "host": "my_host",
        }
        self.assertEqual(
            self.signer._get_canonical_headers(headers),
            "accept-encoding:gzip,deflate\n" "host:my_host\n",
        )

    def test_get_canonical_headers_sorts_headers_lexically(self):
        headers = {
            "accept-encoding": "gzip,deflate",
            "host": "my_host",
            "1st-header": "2",
            "x-amz-date": "20150304T173452Z",
            "user-agent": "my-ua",
        }
        self.assertEqual(
            self.signer._get_canonical_headers(headers),
            "1st-header:2\n"
            "accept-encoding:gzip,deflate\n"
            "host:my_host\n"
            "user-agent:my-ua\n"
            "x-amz-date:20150304T173452Z\n",
        )

    def test_get_canonical_headers_lowercases_headers_names(self):
        headers = {"Accept-Encoding": "GZIP,DEFLATE", "User-Agent": "My-UA"}
        self.assertEqual(
            self.signer._get_canonical_headers(headers),
            "accept-encoding:GZIP,DEFLATE\n" "user-agent:My-UA\n",
        )

    def test_get_canonical_headers_trims_header_values(self):
        headers = {
            "accept-encoding": "   gzip,deflate",
            "user-agent": "libcloud/0.17.0 ",
        }
        self.assertEqual(
            self.signer._get_canonical_headers(headers),
            "accept-encoding:gzip,deflate\n" "user-agent:libcloud/0.17.0\n",
        )

    def test_get_request_params_joins_params_sorted_lexically(self):
        self.assertEqual(
            self.signer._get_request_params(
                {
                    "Action": "DescribeInstances",
                    "Filter.1.Name": "state",
                    "Version": "2013-10-15",
                }
            ),
            "Action=DescribeInstances&Filter.1.Name=state&Version=2013-10-15",
        )

    def test_get_canonical_headers_allow_numeric_header_value(self):
        headers = {"Accept-Encoding": "gzip,deflate", "Content-Length": 314}
        self.assertEqual(
            self.signer._get_canonical_headers(headers),
            "accept-encoding:gzip,deflate\n" "content-length:314\n",
        )

    def test_get_request_params_allows_integers_as_value(self):
        self.assertEqual(
            self.signer._get_request_params({"Action": "DescribeInstances", "Port": 22}),
            "Action=DescribeInstances&Port=22",
        )

    def test_get_request_params_urlquotes_params_keys(self):
        self.assertEqual(
            self.signer._get_request_params({"Action+Reaction": "DescribeInstances"}),
            "Action%2BReaction=DescribeInstances",
        )

    def test_get_request_params_urlquotes_params_values(self):
        self.assertEqual(
            self.signer._get_request_params(
                {"Action": "DescribeInstances&Addresses", "Port-Range": "2000 3000"}
            ),
            "Action=DescribeInstances%26Addresses&Port-Range=2000%203000",
        )

    def test_get_request_params_urlquotes_params_values_allows_safe_chars_in_value(
        self,
    ):
        self.assertEqual(
            "Action=a~b.c_d-e", self.signer._get_request_params({"Action": "a~b.c_d-e"})
        )

    def test_get_request_params_allows_duplicate_query_keys(self):
        self.assertEqual(
            self.signer._get_request_params([("Param1", "value2"), ("Param1", "value1")]),
            "Param1=value1&Param1=value2",
        )

    def test_get_payload_hash_returns_digest_of_empty_string_for_GET_requests(self):
        SignedAWSConnection.method = "GET"
        self.assertEqual(
            self.signer._get_payload_hash(method="GET"),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_get_payload_hash_with_data_for_PUT_requests(self):
        SignedAWSConnection.method = "PUT"
        self.assertEqual(
            self.signer._get_payload_hash(method="PUT", data="DUMMY"),
            "ceec12762e66397b56dad64fd270bb3d694c78fb9cd665354383c0626dbab013",
        )

    def test_get_payload_hash_with_empty_data_for_POST_requests(self):
        SignedAWSConnection.method = "POST"
        self.assertEqual(
            self.signer._get_payload_hash(method="POST"),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_get_payload_hash_prefers_explicit_x_amz_content_sha256_header(self):
        self.assertEqual(
            self.signer._get_payload_hash(
                method="PUT",
                data="IGNORED",
                headers={"X-Amz-Content-SHA256": UNSIGNED_PAYLOAD},
            ),
            UNSIGNED_PAYLOAD,
        )

    def test_get_canonical_request(self):
        req = self.signer._get_canonical_request(
            {"Action": "DescribeInstances", "Version": "2013-10-15"},
            {"Accept-Encoding": "gzip,deflate", "User-Agent": "My-UA"},
            method="GET",
            path="/my_action/",
            data=None,
        )
        self.assertEqual(
            req,
            "GET\n"
            "/my_action/\n"
            "Action=DescribeInstances&Version=2013-10-15\n"
            "accept-encoding:gzip,deflate\n"
            "user-agent:My-UA\n"
            "\n"
            "accept-encoding;user-agent\n"
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_post_canonical_request(self):
        req = self.signer._get_canonical_request(
            {"Action": "DescribeInstances", "Version": "2013-10-15"},
            {"Accept-Encoding": "gzip,deflate", "User-Agent": "My-UA"},
            method="POST",
            path="/my_action/",
            data="{}",
        )
        self.assertEqual(
            req,
            "POST\n"
            "/my_action/\n"
            "Action=DescribeInstances&Version=2013-10-15\n"
            "accept-encoding:gzip,deflate\n"
            "user-agent:My-UA\n"
            "\n"
            "accept-encoding;user-agent\n"
            "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        )

    def test_canonical_request_normalizes_and_urlencodes_special_paths(self):
        req = self.signer._get_canonical_request(
            [],
            {"Host": "example.amazonaws.com", "X-Amz-Date": "20150830T123600Z"},
            method="GET",
            path="/example space/../example/./file.txt",
            data=None,
        )
        self.assertEqual(
            req,
            "GET\n"
            "/example/file.txt\n"
            "\n"
            "host:example.amazonaws.com\n"
            "x-amz-date:20150830T123600Z\n"
            "\n"
            "host;x-amz-date\n"
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )


class AWSRequestSignerAlgorithmV4OfficialSuiteTestCase(LibcloudTestCase):
    def _create_signer(self, case):
        connection = FakeConnection(
            host=case["host"],
            region_name=case["region"],
            service_name=case["service"],
        )
        return AWSRequestSignerAlgorithmV4(
            access_key=case["access_key"],
            access_secret=case["secret_key"],
            version="2013-10-15",
            connection=connection,
        )

    def _parse_raw_request(self, request):
        request = request.rstrip("\n")
        head, separator, body = request.partition("\n\n")
        lines = head.splitlines()
        method, target, _ = lines[0].split(" ", 2)
        headers = []
        for line in lines[1:]:
            if not line:
                continue
            name, value = line.split(":", 1)
            headers.append((name, value.strip()))
        payload = body if separator else None
        return method, target, headers, payload

    def _parse_target(self, target):
        split = urlsplit(target)
        path = split.path or "/"
        params = parse_qsl(split.query, keep_blank_values=True)
        return path, params

    def _get_datetime(self, headers):
        for key, value in headers:
            if key.lower() == "x-amz-date":
                return datetime.strptime(value.strip(), "%Y%m%dT%H%M%SZ")
        raise AssertionError("x-amz-date header is required")

    def _prepare_transport_headers(self, headers, extra_headers=None):
        grouped = OrderedDict()
        for key, value in headers:
            grouped.setdefault(key, []).append(value)

        prepared = OrderedDict(
            (key, ",".join(values)) for key, values in grouped.items()
        )
        if extra_headers:
            prepared.update(extra_headers)
        return prepared

    def _expected_reference_authorization(self, case):
        method, target, headers, payload = self._parse_raw_request(case["request"])
        path, params = self._parse_target(target)
        amz_date = None
        canonical_headers = OrderedDict()

        for key, value in headers:
            lower_key = key.lower()
            canonical_headers.setdefault(lower_key, []).append(value.strip())
            if lower_key == "x-amz-date":
                amz_date = value.strip()

        payload_hash = canonical_headers.get("x-amz-content-sha256", [None])[0]
        if payload_hash is None:
            payload_hash = hashlib.sha256((payload or "").encode("utf-8")).hexdigest()

        canonical_query = []
        for key, value in params:
            canonical_query.append(
                (
                    quote(key, safe="-_.~"),
                    quote(value, safe="-_.~"),
                )
            )
        canonical_query.sort()
        canonical_query_string = "&".join(
            ["{}={}".format(key, value) for key, value in canonical_query]
        )

        normalized_path = self._normalize_reference_path(path)
        canonical_path = quote(normalized_path, safe="/-_.~")
        canonical_header_string = "\n".join(
            [
                "{}:{}".format(key, ",".join(canonical_headers[key]))
                for key in sorted(canonical_headers.keys())
            ]
        ) + "\n"
        signed_headers = ";".join(sorted(canonical_headers.keys()))
        canonical_request = "\n".join(
            [
                method,
                canonical_path,
                canonical_query_string,
                canonical_header_string,
                signed_headers,
                payload_hash,
            ]
        )
        date_stamp = amz_date[:8]
        credential_scope = "{}/{}/{}/aws4_request".format(
            date_stamp, case["region"], case["service"]
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        k_date = hmac.new(
            ("AWS4" + case["secret_key"]).encode("utf-8"),
            date_stamp.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        k_region = hmac.new(k_date, case["region"].encode("utf-8"), hashlib.sha256).digest()
        k_service = hmac.new(k_region, case["service"].encode("utf-8"), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        return (
            "AWS4-HMAC-SHA256 Credential={}/{}, SignedHeaders={}, Signature={}"
        ).format(case["access_key"], credential_scope, signed_headers, signature)

    def _normalize_reference_path(self, path):
        if not path:
            return "/"
        trailing_slash = path.endswith("/")
        segments = []
        for segment in path.split("/"):
            if segment in ("", "."):
                continue
            if segment == "..":
                if segments:
                    segments.pop()
                continue
            segments.append(segment)
        normalized = "/" + "/".join(segments)
        if trailing_slash and normalized != "/":
            normalized += "/"
        return normalized or "/"

    def _assert_authorization_header(self, case, expected_authorization=None):
        signer = self._create_signer(case)
        method, target, headers, payload = self._parse_raw_request(case["request"])
        path, params = self._parse_target(target)
        dt = self._get_datetime(headers)
        authorization = signer._get_authorization_v4_header(
            params=params, headers=headers, dt=dt, method=method, path=path, data=payload
        )
        transport_headers = self._prepare_transport_headers(
            headers=headers,
            extra_headers=case.get("transport_only_headers"),
        )
        transport_headers["Authorization"] = authorization
        raw_url = "https://{}{}".format(case["host"], target)
        prepared_url = requests.Request(method, raw_url).prepare().url

        with requests_mock.Mocker() as mocker:
            mocker.request(method, prepared_url, text="OK")
            response = requests.request(method, raw_url, headers=transport_headers, data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mocker.last_request.headers["Authorization"], authorization)
        if expected_authorization is not None:
            self.assertEqual(authorization, expected_authorization)

    def test_official_signature_v4_suite_matches_expected_authorization_headers(self):
        self.assertEqual(len(OFFICIAL_SIGNATURE_V4_CASES), 17)
        for case in OFFICIAL_SIGNATURE_V4_CASES:
            with self.subTest(case=case["name"]):
                self._assert_authorization_header(
                    case=case,
                    expected_authorization=case["expected_authorization"],
                )

    def test_reference_cases_cover_delete_midnight_and_alternate_services(self):
        for case in REFERENCE_ONLY_CASES:
            with self.subTest(case=case["name"]):
                self._assert_authorization_header(
                    case=case,
                    expected_authorization=self._expected_reference_authorization(case),
                )


if __name__ == "__main__":
    sys.exit(unittest.main())
