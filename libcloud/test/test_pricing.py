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
import os.path
import unittest
from unittest import mock

import libcloud.pricing

PRICING_FILE_PATH = os.path.join(os.path.dirname(__file__), "pricing_test.json")


class PricingTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()

        libcloud.pricing.PRICING_DATA = {"compute": {}, "storage": {}}
        libcloud.pricing._PRICING_FILE_CACHE = {}

    def test_get_pricing_success(self):
        self.assertFalse("foo" in libcloud.pricing.PRICING_DATA["compute"])

        pricing = libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )
        self.assertEqual(pricing["1"], 1.0)
        self.assertEqual(pricing["2"], 2.0)

        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"]["foo"]["1"], 1.0)
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"]["foo"]["2"], 2.0)

    def test_get_pricing_invalid_file_path(self):
        try:
            libcloud.pricing.get_pricing(
                driver_type="compute",
                driver_name="bar",
                pricing_file_path="inexistent.json",
            )
        except OSError:
            pass
        else:
            self.fail("Invalid pricing file path provided, but an exception was not" " thrown")

    def test_get_pricing_invalid_driver_type(self):
        try:
            libcloud.pricing.get_pricing(
                driver_type="invalid_type",
                driver_name="bar",
                pricing_file_path="inexistent.json",
            )
        except AttributeError:
            pass
        else:
            self.fail("Invalid driver_type provided, but an exception was not" " thrown")

    def test_get_pricing_not_in_cache(self):
        try:
            libcloud.pricing.get_pricing(
                driver_type="compute",
                driver_name="inexistent",
                pricing_file_path=PRICING_FILE_PATH,
            )
        except KeyError:
            pass
        else:
            self.fail("Invalid driver provided, but an exception was not" " thrown")

    def test_get_size_price(self):
        libcloud.pricing.PRICING_DATA["compute"]["foo"] = {2: 2, "3": 3}
        price1 = libcloud.pricing.get_size_price(
            driver_type="compute", driver_name="foo", size_id=2
        )
        price2 = libcloud.pricing.get_size_price(
            driver_type="compute", driver_name="foo", size_id="3"
        )
        self.assertEqual(price1, 2)
        self.assertEqual(price2, 3)

    def test_invalid_pricing_cache(self):
        libcloud.pricing.PRICING_DATA["compute"]["foo"] = {2: 2}
        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])

        libcloud.pricing.invalidate_pricing_cache()
        self.assertFalse("foo" in libcloud.pricing.PRICING_DATA["compute"])

    def test_invalid_module_pricing_cache(self):
        libcloud.pricing.PRICING_DATA["compute"]["foo"] = {1: 1}

        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])

        libcloud.pricing.invalidate_module_pricing_cache(driver_type="compute", driver_name="foo")
        self.assertFalse("foo" in libcloud.pricing.PRICING_DATA["compute"])
        libcloud.pricing.invalidate_module_pricing_cache(driver_type="compute", driver_name="foo1")

    def test_set_pricing(self):
        self.assertFalse("foo" in libcloud.pricing.PRICING_DATA["compute"])

        libcloud.pricing.set_pricing(driver_type="compute", driver_name="foo", pricing={"foo": 1})
        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])

    def test_clear_pricing_cache(self):
        libcloud.pricing.PRICING_DATA["compute"]["foo"] = {"1": 1.0}
        libcloud.pricing._PRICING_FILE_CACHE["/fake/path"] = {"compute": {}}

        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])
        self.assertTrue("/fake/path" in libcloud.pricing._PRICING_FILE_CACHE)

        libcloud.pricing.clear_pricing_cache()

        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})
        self.assertEqual(libcloud.pricing.PRICING_DATA["storage"], {})
        self.assertEqual(libcloud.pricing._PRICING_FILE_CACHE, {})

    def test_pricing_file_cache_populated_on_first_load(self):
        self.assertEqual(libcloud.pricing._PRICING_FILE_CACHE, {})

        libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )

        self.assertTrue(PRICING_FILE_PATH in libcloud.pricing._PRICING_FILE_CACHE)
        cached_content = libcloud.pricing._PRICING_FILE_CACHE[PRICING_FILE_PATH]
        self.assertIsInstance(cached_content, str)
        self.assertIn('"foo"', cached_content)
        self.assertIn('"1"', cached_content)

    def test_pricing_file_cache_reused_for_subsequent_drivers(self):
        pricing = libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )
        self.assertEqual(pricing["1"], 1.0)

        self.assertTrue(PRICING_FILE_PATH in libcloud.pricing._PRICING_FILE_CACHE)

        call_count = [0]
        original_open = open

        def counting_open(*args, **kwargs):
            call_count[0] += 1
            return original_open(*args, **kwargs)

        with mock.patch("builtins.open", side_effect=counting_open):
            pricing = libcloud.pricing.get_pricing(
                driver_type="compute",
                driver_name="baz",
                pricing_file_path=PRICING_FILE_PATH,
            )
            self.assertEqual(pricing["1"], 5.0)

        self.assertEqual(call_count[0], 0)

    def test_custom_pricing_file_cached_separately(self):
        custom_path = os.path.join(os.path.dirname(__file__), "pricing_test_custom.json")
        test_data = {
            "compute": {"custom_driver": {"small": 0.01}},
            "updated": 1,
        }
        import json

        with open(custom_path, "w") as f:
            json.dump(test_data, f)

        try:
            libcloud.pricing.get_pricing(
                driver_type="compute",
                driver_name="foo",
                pricing_file_path=PRICING_FILE_PATH,
            )
            libcloud.pricing.get_pricing(
                driver_type="compute",
                driver_name="custom_driver",
                pricing_file_path=custom_path,
            )

            self.assertTrue(PRICING_FILE_PATH in libcloud.pricing._PRICING_FILE_CACHE)
            self.assertTrue(custom_path in libcloud.pricing._PRICING_FILE_CACHE)
            cached_custom = libcloud.pricing._PRICING_FILE_CACHE[custom_path]
            self.assertIsInstance(cached_custom, str)
            self.assertIn("custom_driver", cached_custom)
            self.assertIn("0.01", cached_custom)
        finally:
            os.remove(custom_path)

    def test_get_size_price_lazy_loading(self):
        self.assertEqual(libcloud.pricing._PRICING_FILE_CACHE, {})

        with mock.patch(
            "libcloud.pricing.get_pricing_file_path", return_value=PRICING_FILE_PATH
        ):
            price = libcloud.pricing.get_size_price(
                driver_type="compute",
                driver_name="foo",
                size_id="1",
            )

        self.assertEqual(price, 1.0)

    def test_lazy_loading_only_caches_requested_driver(self):
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})

        libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )

        self.assertIn("foo", libcloud.pricing.PRICING_DATA["compute"])
        self.assertNotIn("bar", libcloud.pricing.PRICING_DATA["compute"])
        self.assertNotIn("baz", libcloud.pricing.PRICING_DATA["compute"])
        self.assertEqual(len(libcloud.pricing.PRICING_DATA["compute"]), 1)

    def test_lazy_loading_multiple_drivers_cached_independently(self):
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})

        libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )
        libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="bar",
            pricing_file_path=PRICING_FILE_PATH,
        )

        self.assertIn("foo", libcloud.pricing.PRICING_DATA["compute"])
        self.assertIn("bar", libcloud.pricing.PRICING_DATA["compute"])
        self.assertNotIn("baz", libcloud.pricing.PRICING_DATA["compute"])
        self.assertEqual(len(libcloud.pricing.PRICING_DATA["compute"]), 2)

    def test_lazy_loading_storage_driver_type(self):
        storage_pricing_path = os.path.join(
            os.path.dirname(__file__), "pricing_test_storage.json"
        )
        test_data = {
            "storage": {"test_storage_driver": {"volume_1": 10.0, "volume_2": 25.0}},
            "updated": 1,
        }
        import json

        with open(storage_pricing_path, "w") as f:
            json.dump(test_data, f)

        try:
            pricing = libcloud.pricing.get_pricing(
                driver_type="storage",
                driver_name="test_storage_driver",
                pricing_file_path=storage_pricing_path,
            )

            self.assertEqual(pricing["volume_1"], 10.0)
            self.assertEqual(pricing["volume_2"], 25.0)
            self.assertIn(
                "test_storage_driver", libcloud.pricing.PRICING_DATA["storage"]
            )
            self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})
        finally:
            os.remove(storage_pricing_path)

    def test_lazy_loading_size_price_through_api(self):
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})

        with mock.patch(
            "libcloud.pricing.get_pricing_file_path", return_value=PRICING_FILE_PATH
        ):
            price = libcloud.pricing.get_size_price(
                driver_type="compute",
                driver_name="foo",
                size_id="2",
            )

        self.assertEqual(price, 2.0)
        self.assertIn("foo", libcloud.pricing.PRICING_DATA["compute"])
        self.assertNotIn("bar", libcloud.pricing.PRICING_DATA["compute"])

    def test_lazy_loading_custom_pricing_file(self):
        custom_path = os.path.join(
            os.path.dirname(__file__), "pricing_test_lazy_custom.json"
        )
        test_data = {
            "compute": {
                "driver_a": {"small": 5.0, "medium": 10.0},
                "driver_b": {"tiny": 1.0, "huge": 100.0},
            },
            "updated": 1,
        }
        import json

        with open(custom_path, "w") as f:
            json.dump(test_data, f)

        try:
            libcloud.pricing.get_pricing(
                driver_type="compute",
                driver_name="driver_a",
                pricing_file_path=custom_path,
            )

            self.assertIn("driver_a", libcloud.pricing.PRICING_DATA["compute"])
            self.assertNotIn("driver_b", libcloud.pricing.PRICING_DATA["compute"])

            pricing_b = libcloud.pricing.get_pricing(
                driver_type="compute",
                driver_name="driver_b",
                pricing_file_path=custom_path,
            )
            self.assertEqual(pricing_b["tiny"], 1.0)
            self.assertIn("driver_b", libcloud.pricing.PRICING_DATA["compute"])
        finally:
            os.remove(custom_path)

    def test_lazy_loading_clear_and_reload(self):
        libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )
        self.assertIn("foo", libcloud.pricing.PRICING_DATA["compute"])

        libcloud.pricing.clear_pricing_cache()

        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})
        self.assertEqual(libcloud.pricing._PRICING_FILE_CACHE, {})

        pricing = libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )
        self.assertEqual(pricing["1"], 1.0)
        self.assertIn("foo", libcloud.pricing.PRICING_DATA["compute"])
        self.assertNotIn("bar", libcloud.pricing.PRICING_DATA["compute"])

    def test_lazy_loading_cache_all_still_works(self):
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})

        pricing = libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
            cache_all=True,
        )
        self.assertEqual(pricing["1"], 1.0)

        self.assertIn("foo", libcloud.pricing.PRICING_DATA["compute"])
        self.assertIn("bar", libcloud.pricing.PRICING_DATA["compute"])
        self.assertIn("baz", libcloud.pricing.PRICING_DATA["compute"])
        self.assertEqual(len(libcloud.pricing.PRICING_DATA["compute"]), 3)

    def test_lazy_loading_module_level_cache_all(self):
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})

        libcloud.pricing.CACHE_ALL_PRICING_DATA = True

        try:
            pricing = libcloud.pricing.get_pricing(
                driver_type="compute",
                driver_name="foo",
                pricing_file_path=PRICING_FILE_PATH,
            )
            self.assertEqual(pricing["1"], 1.0)

            self.assertIn("foo", libcloud.pricing.PRICING_DATA["compute"])
            self.assertIn("bar", libcloud.pricing.PRICING_DATA["compute"])
            self.assertIn("baz", libcloud.pricing.PRICING_DATA["compute"])
        finally:
            libcloud.pricing.CACHE_ALL_PRICING_DATA = False

    def test_clear_pricing_cache_clears_file_cache(self):
        libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )
        self.assertTrue(PRICING_FILE_PATH in libcloud.pricing._PRICING_FILE_CACHE)
        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])

        libcloud.pricing.clear_pricing_cache()

        self.assertEqual(libcloud.pricing._PRICING_FILE_CACHE, {})
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})

    def test_invalidate_pricing_cache_clears_file_cache(self):
        libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )
        self.assertTrue(PRICING_FILE_PATH in libcloud.pricing._PRICING_FILE_CACHE)
        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])

        libcloud.pricing.invalidate_pricing_cache()

        self.assertEqual(libcloud.pricing._PRICING_FILE_CACHE, {})
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})

    def test_clear_pricing_data_clears_file_cache(self):
        libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )
        self.assertTrue(PRICING_FILE_PATH in libcloud.pricing._PRICING_FILE_CACHE)

        libcloud.pricing.clear_pricing_data()

        self.assertEqual(libcloud.pricing._PRICING_FILE_CACHE, {})

    def test_get_pricing_data_caching(self):
        # Ensure we only cache pricing data in memory for requested drivers
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})
        self.assertEqual(libcloud.pricing.PRICING_DATA["storage"], {})

        pricing = libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
        )
        self.assertEqual(pricing["1"], 1.0)
        self.assertEqual(pricing["2"], 2.0)

        self.assertEqual(len(libcloud.pricing.PRICING_DATA["compute"]), 1)
        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])

        pricing = libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="baz",
            pricing_file_path=PRICING_FILE_PATH,
        )
        self.assertEqual(pricing["1"], 5.0)
        self.assertEqual(pricing["2"], 6.0)

        self.assertEqual(len(libcloud.pricing.PRICING_DATA["compute"]), 2)
        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])
        self.assertTrue("baz" in libcloud.pricing.PRICING_DATA["compute"])

    def test_get_pricing_data_module_level_variable_is_true(self):
        # Ensure we only cache pricing data in memory for requested drivers
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})
        self.assertEqual(libcloud.pricing.PRICING_DATA["storage"], {})

        libcloud.pricing.CACHE_ALL_PRICING_DATA = True

        pricing = libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
            cache_all=False,
        )
        self.assertEqual(pricing["1"], 1.0)
        self.assertEqual(pricing["2"], 2.0)

        self.assertEqual(len(libcloud.pricing.PRICING_DATA["compute"]), 3)
        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])
        self.assertTrue("bar" in libcloud.pricing.PRICING_DATA["compute"])
        self.assertTrue("baz" in libcloud.pricing.PRICING_DATA["compute"])

    def test_get_pricing_data_caching_cache_all(self):
        # Ensure we only cache pricing data in memory for requested drivers
        self.assertEqual(libcloud.pricing.PRICING_DATA["compute"], {})
        self.assertEqual(libcloud.pricing.PRICING_DATA["storage"], {})

        pricing = libcloud.pricing.get_pricing(
            driver_type="compute",
            driver_name="foo",
            pricing_file_path=PRICING_FILE_PATH,
            cache_all=True,
        )
        self.assertEqual(pricing["1"], 1.0)
        self.assertEqual(pricing["2"], 2.0)

        self.assertEqual(len(libcloud.pricing.PRICING_DATA["compute"]), 3)
        self.assertTrue("foo" in libcloud.pricing.PRICING_DATA["compute"])
        self.assertTrue("bar" in libcloud.pricing.PRICING_DATA["compute"])
        self.assertTrue("baz" in libcloud.pricing.PRICING_DATA["compute"])

    def test_get_gce_image_price_non_premium_image(self):
        image_name = "debian-10-buster-v20220519"
        cores = 4
        size_name = "c2d-standard-4"
        price = libcloud.pricing.get_image_price("gce_images", image_name, size_name, cores)
        self.assertTrue(price == 0)

    def test_get_gce_image_price_RHEL_image(self):
        cores = 2
        image_name = "rhel-7-v20220519"
        size_name = "n2d-highcpu-2"
        prices = libcloud.pricing.get_pricing("compute", "gce_images")
        correct_price = float(prices["RHEL"]["4vcpu or less"]["price"])
        fetched_price = libcloud.pricing.get_image_price("gce_images", image_name, size_name, cores)
        self.assertTrue(fetched_price == correct_price)

    def test_get_gce_image_price_Windows_image(self):
        cores = 2
        image_name = "windows-server-2012-r2-dc-core-v20220513"
        size_name = "n2d-highcpu-2"
        prices = libcloud.pricing.get_pricing("compute", "gce_images")
        correct_price = float(prices["Windows Server"]["any"]["price"]) * 2
        fetched_price = libcloud.pricing.get_image_price("gce_images", image_name, size_name, cores)
        self.assertTrue(fetched_price == correct_price)

    def test_get_gce_image_price_SLES_SAP_image(self):
        cores = 2
        image_name = "sles-15-sap-v20220126"
        size_name = "n2d-highcpu-2"
        prices = libcloud.pricing.get_pricing("compute", "gce_images")
        correct_price = float(prices["SLES for SAP"]["1-2vcpu"]["price"])
        fetched_price = libcloud.pricing.get_image_price("gce_images", image_name, size_name, cores)
        self.assertTrue(fetched_price == correct_price)

    def test_get_gce_image_price_SQL_image(self):
        image_name = "sql-2012-standard-windows-2012-r2-dc-v20220513"
        size_name = "g1 small"
        prices = libcloud.pricing.get_pricing("compute", "gce_images")
        correct_price = float(prices["SQL Server"]["standard"]["price"])
        fetched_price = libcloud.pricing.get_image_price("gce_images", image_name, size_name)
        self.assertTrue(fetched_price == correct_price)


if __name__ == "__main__":
    sys.exit(unittest.main())
