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
import unittest
from datetime import datetime
from unittest import mock

import requests_mock

from libcloud.test import LibcloudTestCase
from libcloud.common.aws import (
    SignedAWSConnection,
    UNSIGNED_PAYLOAD,
    AWSRequestSignerAlgorithmV4,
    _sign,
    _hash,
)
from libcloud.utils.py3 import urlquote


class MockDriver:
    def __init__(self, region_name):
        self.region_name = region_name


class AWSSigV4OfficialTestSuiteTestCase(LibcloudTestCase):

    ACCESS_KEY = "AKIDEXAMPLE"
    SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    REGION = "us-east-1"
    SERVICE = "service"
    DATE_STR = "20150830T123600Z"

    @staticmethod
    def _make_dt(dt_str):
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ")

    def _make_signer(self, access_key=None, secret_key=None, region=None, service=None):
        access_key = access_key or self.ACCESS_KEY
        secret_key = secret_key or self.SECRET_KEY
        region = region or self.REGION
        service = service or self.SERVICE

        driver = MockDriver(region)
        SignedAWSConnection.driver = driver
        SignedAWSConnection.service_name = service
        SignedAWSConnection.version = "2013-10-15"
        self.connection = SignedAWSConnection(access_key, secret_key)

        signer = AWSRequestSignerAlgorithmV4(
            access_key=access_key,
            access_secret=secret_key,
            version="2013-10-15",
            connection=self.connection,
        )
        SignedAWSConnection.action = "/"
        SignedAWSConnection.driver = driver
        return signer

    def _sign_and_assert(self, signer, method, path, params, headers, dt_str, expected_auth):
        dt = self._make_dt(dt_str)
        auth = signer._get_authorization_v4_header(
            params=params, headers=headers, dt=dt, method=method, path=path
        )
        self.assertEqual(auth, expected_auth)
        return auth

    def _assert_auth_structure(self, auth, expected_credential=None):
        self.assertTrue(auth.startswith("AWS4-HMAC-SHA256 "))
        self.assertIn("Credential=", auth)
        self.assertIn("SignedHeaders=", auth)
        self.assertIn("Signature=", auth)
        parts = auth.split(", ")
        self.assertEqual(len(parts), 3, "Auth header should have Credential, SignedHeaders, Signature")
        sig_part = parts[2]
        self.assertEqual(len(sig_part.split("=", 1)[1]), 64,
                         "Signature should be 64 hex chars")
        if expected_credential:
            self.assertIn("Credential={}".format(expected_credential), auth)

    def _build_auth_header(self, access_key, scope, signed_headers, signature):
        return (
            "AWS4-HMAC-SHA256 "
            "Credential={}/{}, "
            "SignedHeaders={}, "
            "Signature={}"
        ).format(access_key, scope, signed_headers, signature)

    def _expected_scope(self, dt_str, region=None, service=None):
        dt = self._make_dt(dt_str)
        region = region or self.REGION
        service = service or self.SERVICE
        return "{}/{}/{}/aws4_request".format(dt.strftime("%Y%m%d"), region, service)

    def _sign_hmac(self, key, msg, hex_encode=True):
        return _sign(key, msg, hex=hex_encode)

    def _make_signing_key(self, secret, dt_str, region, service):
        dt = self._make_dt(dt_str)
        k_date = self._sign_hmac(("AWS4" + secret), dt.strftime("%Y%m%d"), hex_encode=False)
        k_region = self._sign_hmac(k_date, region, hex_encode=False)
        k_service = self._sign_hmac(k_region, service, hex_encode=False)
        k_signing = self._sign_hmac(k_service, "aws4_request", hex_encode=False)
        return k_signing

    def test_01_get_vanilla(self):
        signer = self._make_signer()
        self._sign_and_assert(
            signer=signer,
            method="GET",
            path="/",
            params={},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt_str=self.DATE_STR,
            expected_auth=(
                "AWS4-HMAC-SHA256 "
                "Credential={}/20150830/{}/{}/aws4_request, "
                "SignedHeaders=host;x-amz-date, "
                "Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31"
            ).format(self.ACCESS_KEY, self.REGION, self.SERVICE),
        )

    def test_02_post_vanilla_unsigned_payload(self):
        signer = self._make_signer()
        dt = self._make_dt(self.DATE_STR)
        headers = {"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR}

        cr = signer._get_canonical_request({}, headers, "POST", "/", None)
        self.assertIn("UNSIGNED-PAYLOAD", cr)
        self.assertIn("POST", cr)
        self.assertIn("host:example.amazonaws.com", cr)
        self.assertIn("x-amz-date:20150830T123600Z", cr)

        auth = signer._get_authorization_v4_header(
            params={}, headers=headers, dt=dt, method="POST", path="/"
        )
        self._assert_auth_structure(auth)

    def test_03_get_vanilla_query_exact_match(self):
        signer = self._make_signer()

        sts = signer._get_string_to_sign(
            params={"Test-Param": "Value!", "Another-Param": "AnotherValue"},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
            data=None,
        )
        line0, line1, line2, line3 = sts.split("\n")
        self.assertEqual(line0, "AWS4-HMAC-SHA256")
        self.assertEqual(line1, "20150830T123600Z")
        self.assertEqual(line2, "20150830/us-east-1/service/aws4_request")

        auth = signer._get_authorization_v4_header(
            params={"Test-Param": "Value!", "Another-Param": "AnotherValue"},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        self.assertIn("Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request", auth)

        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=c09527aae43a515ce0646e2f6a9b56d62f0606a4e383fa7f4f460f5606aa7411"
        )
        self.assertEqual(auth, expected)

    def test_04_get_vanilla_query_order_encoded_long(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={"a": "b+c", "d": "e+f"},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=929e7a86d8a61b32ce05a88b0a31b529a2a8b5cf35a92963e8f03482cb6899a7"
        )
        self.assertEqual(auth, expected)

    def test_05_get_unreserved_path(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/a-b.c_d~e/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=0e2f7d9fbf9e7b8bdb9c1a953a683d91f08b5f9b9e1e1c316e87fbdc196c025d"
        )
        self.assertEqual(auth, expected)

    def test_06_get_utf8_path(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/コンテンツ.txt",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=9d8c5832e8870ff0e5a6e7c4c32606e17f9508b0f042f94c3590c5f8c9f91b71"
        )
        self.assertEqual(auth, expected)

    def test_07_vanilla_empty_query_key(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={"Test-Param": ""},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=4756598fbb111f6523c2f89be3eb154c698e768b8cc4ae3f033820b7f6f3a1b2"
        )
        self.assertEqual(auth, expected)

    def test_08_vanilla_query_unreserved_param(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={"a-b_c.d~e": "f-g.h_i~j"},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=6d569370f9c458a1f307d82f30a57b49afb0efc42f2c3d32b41a90d88b01b05d"
        )
        self.assertEqual(auth, expected)

    def test_09_header_key_duplicate_values(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={},
            headers={
                "Host": "example.amazonaws.com",
                "X-Amz-Date": self.DATE_STR,
                "My-Header1": "value2, value2, value1",
            },
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;my-header1;x-amz-date, "
            "Signature=c9d5ea9f3f72853aea855b47ea873832890dbdd183b4468f858259531a5138ea"
        )
        self.assertEqual(auth, expected)

    def test_10_header_value_multiline(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={},
            headers={
                "Host": "example.amazonaws.com",
                "X-Amz-Date": self.DATE_STR,
                "My-Header1": "value1\n  value2\n    value3",
            },
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;my-header1;x-amz-date, "
            "Signature=5c491e84366f29d7a91812c69b824ed83999a1a6f0633088939e8b8f5e9f979f"
        )
        self.assertEqual(auth, expected)

    def test_11_vanilla_with_session_token(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={},
            headers={
                "Host": "example.amazonaws.com",
                "X-Amz-Date": self.DATE_STR,
                "X-Amz-Security-Token": "6e86291e8372ff2a2260956d9b8aae1d763fbf315fa00fa31553b73ebf194267",
            },
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date;x-amz-security-token, "
            "Signature=07ec1639c89043aa0e3e2de82b96708f198cceab042d4a97044c66dd9f74e7f8"
        )
        self.assertEqual(auth, expected)

    def test_12_normalize_path_preserved(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/a//b/./c/../d",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=6f59c421b4d4c08d1d9f0e30a9f4e08f9922c92c3e90f08735e461c1b06a7d6d"
        )
        self.assertEqual(auth, expected)

    def test_13_post_x_www_form_urlencoded(self):
        signer = self._make_signer()
        payload = "Param1=value1"
        auth = signer._get_authorization_v4_header(
            params={},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Host": "example.amazonaws.com",
                "X-Amz-Date": self.DATE_STR,
            },
            dt=self._make_dt(self.DATE_STR),
            method="POST",
            path="/",
            data=payload,
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=content-type;host;x-amz-date, "
            "Signature=ff11897932ad3f4e8b18135d722051e5ac45fc38421b1da7b9d196a0fe09473a"
        )
        self.assertEqual(auth, expected)

    def test_14_delete_method(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="DELETE",
            path="/objects/abc",
        )
        self._assert_auth_structure(auth)
        self.assertIn("Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request", auth)

    def test_15_put_method_with_json_body(self):
        signer = self._make_signer()
        payload = '{"key": "value"}'
        auth = signer._get_authorization_v4_header(
            params={},
            headers={
                "Content-Type": "application/json",
                "Host": "example.amazonaws.com",
                "X-Amz-Date": self.DATE_STR,
            },
            dt=self._make_dt(self.DATE_STR),
            method="PUT",
            path="/objects",
            data=payload,
        )
        self._assert_auth_structure(auth)
        self.assertIn("content-type", auth)

    def test_16_header_value_trim(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={},
            headers={
                "Host": "example.amazonaws.com",
                "X-Amz-Date": self.DATE_STR,
                "My-Header1": "   a b  c  ",
                "My-Header2": "   \"a b c\"  ",
            },
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;my-header1;my-header2;x-amz-date, "
            "Signature=9b38d3e0cf683f529e7c8e5013f9e5058f68ef4f0ef43e7baa5931b50862913e"
        )
        self.assertEqual(auth, expected)

    def test_17_midnight_date_boundary(self):
        midnight_str = "20150830T000000Z"

        signer = self._make_signer()
        dt = self._make_dt(midnight_str)

        scope = signer._get_credential_scope(dt)
        self.assertEqual(scope, "20150830/us-east-1/service/aws4_request")

        k_signing = self._make_signing_key(
            self.SECRET_KEY, midnight_str, self.REGION, self.SERVICE
        )
        self.assertEqual(len(k_signing), 32)

        k_signing_noon = self._make_signing_key(
            self.SECRET_KEY, self.DATE_STR, self.REGION, self.SERVICE
        )
        self.assertEqual(k_signing, k_signing_noon,
                         "Signing key should be identical for same date regardless of time")

        auth = signer._get_authorization_v4_header(
            params={},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": midnight_str},
            dt=dt,
            method="GET",
            path="/",
        )
        self._assert_auth_structure(auth)
        self.assertIn("Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request", auth)

    def test_18_header_value_order(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={},
            headers={
                "Host": "example.amazonaws.com",
                "X-Amz-Date": self.DATE_STR,
                "Zoo": "parrot=blue, dog=red",
                "Date": "Mon, 07 Jan 2014 20:44:32 GMT",
            },
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=date;host;x-amz-date;zoo, "
            "Signature=87e3185d78d3463a04403a89230d1c385f58d55670b5d06e31e966b33f68f9e1"
        )
        self.assertEqual(auth, expected)

    def test_19_s3_example_get_object(self):
        signer = self._make_signer(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-east-1",
            service="s3",
        )
        dt = datetime(2013, 5, 24, 0, 0, 0)
        headers = {
            "Host": "examplebucket.s3.amazonaws.com",
            "Range": "bytes=0-9",
            "X-Amz-Content-Sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "X-Amz-Date": "20130524T000000Z",
        }
        auth = signer._get_authorization_v4_header(
            params={}, headers=headers, dt=dt, method="GET", path="/test.txt"
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
            "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
            "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
        )
        self.assertEqual(auth, expected)

    def test_20_canonical_request_components(self):
        signer = self._make_signer()
        dt = self._make_dt(self.DATE_STR)

        cr = signer._get_canonical_request(
            params={"Action": "DescribeInstances", "Version": "2013-10-15"},
            headers={"Host": "ec2.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            method="GET",
            path="/",
            data=None,
        )
        lines = cr.split("\n")
        self.assertEqual(lines[0], "GET")
        self.assertEqual(lines[1], "/")
        self.assertIn("Action=DescribeInstances", lines[2])
        self.assertIn("Version=2013-10-15", lines[2])
        self.assertEqual(lines[3], "host:ec2.amazonaws.com")
        self.assertEqual(lines[4], "x-amz-date:20150830T123600Z")
        self.assertEqual(lines[5], "")
        self.assertEqual(lines[6], "host;x-amz-date")
        self.assertEqual(lines[7], "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_21_signing_key_derivation(self):
        k_signing = self._make_signing_key(
            self.SECRET_KEY, self.DATE_STR, self.REGION, self.SERVICE
        )
        self.assertEqual(len(k_signing), 32)

        k_signing2 = self._make_signing_key(
            self.SECRET_KEY, self.DATE_STR, self.REGION, self.SERVICE
        )
        self.assertEqual(k_signing, k_signing2, "Same inputs should produce same signing key")

    def test_22_credential_scope_format(self):
        signer = self._make_signer()
        dt = self._make_dt(self.DATE_STR)
        scope = signer._get_credential_scope(dt)
        self.assertEqual(scope, "20150830/us-east-1/service/aws4_request")

    def test_23_payload_hash_for_different_methods(self):
        signer = self._make_signer()

        get_hash = signer._get_payload_hash("GET")
        self.assertEqual(get_hash, _hash(""))

        delete_hash = signer._get_payload_hash("DELETE")
        self.assertEqual(delete_hash, _hash(""))

        head_hash = signer._get_payload_hash("HEAD")
        self.assertEqual(head_hash, _hash(""))

        post_nodata_hash = signer._get_payload_hash("POST")
        self.assertEqual(post_nodata_hash, UNSIGNED_PAYLOAD)

        put_nodata_hash = signer._get_payload_hash("PUT")
        self.assertEqual(put_nodata_hash, UNSIGNED_PAYLOAD)

        post_data_hash = signer._get_payload_hash("POST", data="hello")
        self.assertEqual(post_data_hash, _hash("hello"))

        put_data_hash = signer._get_payload_hash("PUT", data="world")
        self.assertEqual(put_data_hash, _hash("world"))

    def test_24_signed_headers_sorting(self):
        signer = self._make_signer()
        headers = {
            "host": "example.amazonaws.com",
            "x-amz-date": "20150830T123600Z",
            "content-type": "text/plain",
            "accept": "application/json",
        }
        signed = signer._get_signed_headers(headers)
        self.assertEqual(signed, "accept;content-type;host;x-amz-date")

    def test_25_canonical_headers_format(self):
        signer = self._make_signer()
        headers = {
            "Host": "example.amazonaws.com",
            "X-Amz-Date": "20150830T123600Z",
            "Content-Type": "text/plain",
        }
        canonical = signer._get_canonical_headers(headers)
        expected = (
            "content-type:text/plain\n"
            "host:example.amazonaws.com\n"
            "x-amz-date:20150830T123600Z\n"
        )
        self.assertEqual(canonical, expected)

    def test_26_different_region_and_service(self):
        signer = self._make_signer(region="eu-west-1", service="ec2")
        dt = self._make_dt(self.DATE_STR)
        scope = signer._get_credential_scope(dt)
        self.assertEqual(scope, "20150830/eu-west-1/ec2/aws4_request")

        auth = signer._get_authorization_v4_header(
            params={},
            headers={"Host": "ec2.eu-west-1.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=dt,
            method="GET",
            path="/",
        )
        self.assertIn("20150830/eu-west-1/ec2/aws4_request", auth)

    def test_27_request_params_url_encoding(self):
        signer = self._make_signer()

        result = signer._get_request_params({"Action": "DescribeInstances", "Port": 22})
        self.assertEqual(result, "Action=DescribeInstances&Port=22")

        result = signer._get_request_params({"Action+Reaction": "DescribeInstances"})
        self.assertEqual(result, "Action%2BReaction=DescribeInstances")

        result = signer._get_request_params(
            {"Action": "DescribeInstances&Addresses", "Port-Range": "2000 3000"}
        )
        self.assertEqual(result, "Action=DescribeInstances%26Addresses&Port-Range=2000%203000")

    def test_28_string_to_sign_format(self):
        signer = self._make_signer()
        dt = self._make_dt(self.DATE_STR)

        sts = signer._get_string_to_sign(
            params={},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=dt,
            method="GET",
            path="/",
            data=None,
        )
        lines = sts.split("\n")
        self.assertEqual(lines[0], "AWS4-HMAC-SHA256")
        self.assertEqual(lines[1], "20150830T123600Z")
        self.assertEqual(lines[2], "20150830/us-east-1/service/aws4_request")
        self.assertEqual(len(lines[3]), 64)

    def test_29_get_vanilla_utf8_query(self):
        signer = self._make_signer()
        auth = signer._get_authorization_v4_header(
            params={"\xe5\x8d\x97": "\xe5\x8c\x97"},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=self._make_dt(self.DATE_STR),
            method="GET",
            path="/",
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=host;x-amz-date, "
            "Signature=204662106c9d41475872b3df619618391201145ddc2317e61cc06f49a1d48172"
        )
        self.assertEqual(auth, expected)

    def test_30_post_header_key_sort(self):
        signer = self._make_signer()
        payload = "Param1=value1"
        auth = signer._get_authorization_v4_header(
            params={},
            headers={
                "Host": "example.amazonaws.com",
                "X-Amz-Date": self.DATE_STR,
                "content-type": "application/x-www-form-urlencoded",
            },
            dt=self._make_dt(self.DATE_STR),
            method="POST",
            path="/",
            data=payload,
        )
        expected = (
            "AWS4-HMAC-SHA256 "
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
            "SignedHeaders=content-type;host;x-amz-date, "
            "Signature=509c3f80fcf4f1a79ff3f564397e5efb739b2f8946e363a6808c3365e37081ed"
        )
        self.assertEqual(auth, expected)

    @requests_mock.Mocker()
    def test_31_integration_with_connection_get(self, mock_requests):
        mock_requests.get("https://example.amazonaws.com/", text="OK", status_code=200)

        driver = MockDriver("us-east-1")
        connection = SignedAWSConnection(self.ACCESS_KEY, self.SECRET_KEY, token=None)
        connection.driver = driver
        connection.service_name = self.SERVICE
        connection.version = "2013-10-15"
        connection.host = "example.amazonaws.com"
        connection.secure = True

        with mock.patch("libcloud.common.aws.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2015, 8, 30, 12, 36, 0)
            response = connection.request("/", method="GET")

        self.assertEqual(response.status, 200)
        request_headers = mock_requests.last_request.headers
        self.assertIn("Authorization", request_headers)
        self.assertIn("X-AMZ-Date", request_headers)
        self.assertIn("X-AMZ-Content-SHA256", request_headers)
        self.assertTrue(
            request_headers["Authorization"].startswith("AWS4-HMAC-SHA256")
        )

    def test_32_special_space_in_path(self):
        signer = self._make_signer()
        dt = self._make_dt(self.DATE_STR)
        auth = signer._get_authorization_v4_header(
            params={},
            headers={"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR},
            dt=dt,
            method="GET",
            path="/object with spaces/key with_underscores.ext",
        )
        self._assert_auth_structure(auth)
        self.assertIn(
            "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request", auth
        )

    def test_33_all_four_http_methods_exist(self):
        signer = self._make_signer()
        dt = self._make_dt(self.DATE_STR)
        common_headers = {"Host": "example.amazonaws.com", "X-Amz-Date": self.DATE_STR}

        for method in ["GET", "POST", "PUT", "DELETE"]:
            auth = signer._get_authorization_v4_header(
                params={},
                headers=common_headers,
                dt=dt,
                method=method,
                path="/",
            )
            self._assert_auth_structure(auth)
            self.assertTrue(
                auth.startswith("AWS4-HMAC-SHA256 "),
                "Auth header for {} should start with AWS4-HMAC-SHA256".format(method),
            )


if __name__ == "__main__":
    sys.exit(unittest.main())