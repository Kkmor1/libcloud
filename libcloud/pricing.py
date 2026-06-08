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
A class which handles loading the pricing files.
"""

import re
import os.path
from typing import Dict, Union, Optional
from os.path import join as pjoin

try:
    import simplejson as json

    try:
        JSONDecodeError = json.JSONDecodeError
    except AttributeError:
        JSONDecodeError = ValueError  # type: ignore
except ImportError:
    import json  # type: ignore

    JSONDecodeError = ValueError  # type: ignore

__all__ = [
    "get_pricing",
    "get_size_price",
    "get_storage_price",
    "get_image_price",
    "set_pricing",
    "clear_pricing_cache",
    "clear_pricing_data",
    "download_pricing_file",
]

DEFAULT_FILE_URL_GIT = "https://git.apache.org/repos/asf?p=libcloud.git;a=blob_plain;f=libcloud/data/pricing.json"  # NOQA

DEFAULT_FILE_URL_S3_BUCKET = "https://libcloud-pricing-data.s3.amazonaws.com/pricing.json"  # NOQA

CURRENT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRICING_FILE_PATH = pjoin(CURRENT_DIRECTORY, "data/pricing.json")
CUSTOM_PRICING_FILE_PATH = os.path.expanduser("~/.libcloud/pricing.json")

PRICING_DATA = {"compute": {}, "storage": {}}  # type: Dict[str, Dict]
_FILE_PRICING_CACHE = {}  # type: Dict[str, Dict[str, Dict[str, dict]]]

VALID_PRICING_DRIVER_TYPES = ["compute", "storage"]

CACHE_ALL_PRICING_DATA = False


class _JSONStreamReader:
    def __init__(self, file_handle):
        self.file_handle = file_handle
        self.buffer = ""
        self.chunk_size = 8192

    def read(self, size=1):
        while len(self.buffer) < size:
            chunk = self.file_handle.read(max(self.chunk_size, size - len(self.buffer)))
            if not chunk:
                break
            self.buffer += chunk

        result = self.buffer[:size]
        self.buffer = self.buffer[size:]
        return result

    def peek(self):
        self._fill_buffer()
        if not self.buffer:
            return ""
        return self.buffer[0]

    def _fill_buffer(self):
        if self.buffer:
            return

        chunk = self.file_handle.read(self.chunk_size)
        if chunk:
            self.buffer += chunk

    def skip_whitespace(self):
        while True:
            char = self.peek()
            if not char or not char.isspace():
                return
            self.read(1)

    def expect(self, expected):
        actual = self.read(1)
        if actual != expected:
            raise ValueError("Invalid pricing data")

    def read_string(self):
        return json.loads(self.read_string_text())

    def read_string_text(self):
        self.skip_whitespace()
        self.expect('"')

        result = ['"']
        escaped = False

        while True:
            char = self.read(1)
            if not char:
                raise ValueError("Invalid pricing data")

            result.append(char)

            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
            elif char == '"':
                break

        return "".join(result)

    def read_value_text(self):
        self.skip_whitespace()
        char = self.peek()

        if char in ["{", "["]:
            return self.read_container_text()

        if char == '"':
            return self.read_string_text()

        return self.read_primitive_text()

    def read_container_text(self):
        self.skip_whitespace()
        first_char = self.read(1)
        if first_char not in ["{", "["]:
            raise ValueError("Invalid pricing data")

        result = [first_char]
        stack = [first_char]
        escaped = False
        in_string = False

        while stack:
            char = self.read(1)
            if not char:
                raise ValueError("Invalid pricing data")

            result.append(char)

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char in ["{", "["]:
                stack.append(char)
            elif char in ["}", "]"]:
                expected = "}" if stack[-1] == "{" else "]"
                if char != expected:
                    raise ValueError("Invalid pricing data")
                stack.pop()

        return "".join(result)

    def read_primitive_text(self):
        self.skip_whitespace()

        result = []
        while True:
            char = self.peek()
            if not char or char.isspace() or char in [",", "}", "]"]:
                break
            result.append(self.read(1))

        if not result:
            raise ValueError("Invalid pricing data")

        return "".join(result)

    def skip_value(self):
        self.read_value_text()


def _normalize_pricing_file_path(pricing_file_path=None):
    # type: (Optional[str]) -> str
    pricing_file_path = pricing_file_path or get_pricing_file_path(file_path=pricing_file_path)
    pricing_file_path = os.path.expanduser(pricing_file_path)
    return os.path.abspath(pricing_file_path)


def _get_file_pricing_cache(pricing_file_path):
    # type: (str) -> Dict[str, Dict[str, dict]]
    return _FILE_PRICING_CACHE.setdefault(pricing_file_path, {"compute": {}, "storage": {}})


def _read_value_from_object(reader, target_key):
    # type: (_JSONStreamReader, str) -> dict
    reader.skip_whitespace()
    reader.expect("{")
    reader.skip_whitespace()

    if reader.peek() == "}":
        reader.read(1)
        raise KeyError(target_key)

    while True:
        key = reader.read_string()
        reader.skip_whitespace()
        reader.expect(":")

        if key == target_key:
            return json.loads(reader.read_value_text())

        reader.skip_value()
        reader.skip_whitespace()

        delimiter = reader.read(1)
        if delimiter == "}":
            break
        if delimiter != ",":
            raise ValueError("Invalid pricing data")

    raise KeyError(target_key)


def _load_driver_pricing(pricing_file_path, driver_type, driver_name):
    # type: (str, str, str) -> dict
    with open(pricing_file_path) as file_handle:
        reader = _JSONStreamReader(file_handle=file_handle)
        reader.skip_whitespace()
        reader.expect("{")
        reader.skip_whitespace()

        if reader.peek() == "}":
            reader.read(1)
            raise KeyError(driver_type)

        while True:
            key = reader.read_string()
            reader.skip_whitespace()
            reader.expect(":")

            if key == driver_type:
                return _read_value_from_object(reader=reader, target_key=driver_name)

            reader.skip_value()
            reader.skip_whitespace()

            delimiter = reader.read(1)
            if delimiter == "}":
                break
            if delimiter != ",":
                raise ValueError("Invalid pricing data")

    raise KeyError(driver_type)


def _load_all_pricing_data(pricing_file_path):
    # type: (str) -> dict
    with open(pricing_file_path) as file_handle:
        return json.load(file_handle)


def get_pricing_file_path(file_path=None):
    # type: (Optional[str]) -> str
    if os.path.exists(CUSTOM_PRICING_FILE_PATH) and os.path.isfile(CUSTOM_PRICING_FILE_PATH):
        return CUSTOM_PRICING_FILE_PATH

    return DEFAULT_PRICING_FILE_PATH


def get_pricing(driver_type, driver_name, pricing_file_path=None, cache_all=False):
    # type: (str, str, Optional[str], bool) -> Optional[dict]
    """
    Return pricing for the provided driver.

    NOTE: This method will also cache data for the requested driver
    memory.

    We intentionally only cache data for the requested driver and not all the
    pricing data since the whole pricing data is quite large (~2 MB). This
    way we avoid unnecessary memory overhead.

    :type driver_type: ``str``
    :param driver_type: Driver type ('compute' or 'storage')

    :type driver_name: ``str``
    :param driver_name: Driver name

    :type pricing_file_path: ``str``
    :param pricing_file_path: Custom path to a price file. If not provided
                              it uses a default path.

    :type cache_all: ``bool``
    :param cache_all: True to cache pricing data in memory for all the drivers
                      and not just for the requested one.

    :rtype: ``dict``
    :return: Dictionary with pricing where a key name is size ID and
             the value is a price.
    """
    cache_all = cache_all or CACHE_ALL_PRICING_DATA

    if driver_type not in VALID_PRICING_DRIVER_TYPES:
        raise AttributeError("Invalid driver type: %s", driver_type)

    resolved_pricing_file_path = _normalize_pricing_file_path(pricing_file_path=pricing_file_path)
    file_cache = _get_file_pricing_cache(pricing_file_path=resolved_pricing_file_path)

    if pricing_file_path is None and driver_name in PRICING_DATA[driver_type]:
        return PRICING_DATA[driver_type][driver_name]

    if driver_name in file_cache[driver_type]:
        return file_cache[driver_type][driver_name]

    if cache_all:
        pricing_data = _load_all_pricing_data(pricing_file_path=resolved_pricing_file_path)

        for current_driver_type in VALID_PRICING_DRIVER_TYPES:
            pricing = pricing_data.get(current_driver_type, None)

            if not pricing:
                continue

            file_cache[current_driver_type] = pricing
            PRICING_DATA[current_driver_type].update(pricing)

        return file_cache[driver_type][driver_name]

    driver_pricing = _load_driver_pricing(
        pricing_file_path=resolved_pricing_file_path,
        driver_type=driver_type,
        driver_name=driver_name,
    )

    file_cache[driver_type][driver_name] = driver_pricing
    PRICING_DATA[driver_type][driver_name] = driver_pricing

    return driver_pricing


def set_pricing(driver_type, driver_name, pricing):
    # type: (str, str, dict) -> None
    """
    Populate the driver pricing dictionary.

    :type driver_type: ``str``
    :param driver_type: Driver type ('compute' or 'storage')

    :type driver_name: ``str``
    :param driver_name: Driver name

    :type pricing: ``dict``
    :param pricing: Dictionary where a key is a size ID and a value is a price.
    """

    PRICING_DATA[driver_type][driver_name] = pricing


def get_size_price(driver_type, driver_name, size_id, region=None):
    # type: (str, str, Union[str,int], Optional[str]) -> Optional[float]
    """
    Return price for the provided size.

    :type driver_type: ``str``
    :param driver_type: Driver type ('compute' or 'storage')

    :type driver_name: ``str``
    :param driver_name: Driver name

    :type size_id: ``str`` or ``int``
    :param size_id: Unique size ID (can be an integer or a string - depends on
                    the driver)

    :rtype: ``float``
    :return: Size price.
    """
    pricing = get_pricing(driver_type=driver_type, driver_name=driver_name)
    assert pricing is not None

    price = None  # Type: Optional[float]

    try:
        if region is None:
            price = float(pricing[size_id])
        else:
            price = float(pricing[size_id][region])
    except KeyError:
        price = None

    return price


def get_storage_price(driver_name, size_id, region=None):
    # type: (str, Union[str,int], Optional[str]) -> Optional[float]
    """
    Return price for the provided storage size.
    """
    return get_size_price(
        driver_type="storage",
        driver_name=driver_name,
        size_id=size_id,
        region=region,
    )


def get_image_price(driver_name, image_name, size_name=None, cores=1):
    if driver_name == "gce_images":
        return _get_gce_image_price(image_name=image_name, size_name=size_name, cores=cores)

    return 0


def _get_gce_image_price(image_name, size_name, cores=1):
    """
    Return price per hour for an gce image.
    Price depends on the size of the VM.

    :type image_name: ``str``
    :param image_name: GCE image full name.
                       Can be found from GCENodeImage.name

    :type size_name: ``str``
    :param size_name: Size name of the machine running the image.
                      Can be found from GCENodeSize.name

    :type cores: ``int``
    :param cores: The number of the CPUs the machine running the image has.
                  Can be found from GCENodeSize.extra['guestCpus']

    :rtype: ``float``
    :return: Image price
    """

    def _get_gce_image_family(image_name):
        image_family = None

        if "sql" in image_name:
            image_family = "SQL Server"
        elif "windows" in image_name:
            image_family = "Windows Server"
        elif "rhel" in image_name and "sap" in image_name:
            image_family = "RHEL with Update Services"
        elif "sles" in image_name and "sap" in image_name:
            image_family = "SLES for SAP"
        elif "rhel" in image_name:
            image_family = "RHEL"
        elif "sles" in image_name:
            image_family = "SLES"
        return image_family

    image_family = _get_gce_image_family(image_name)
    if not image_family:
        return 0

    pricing = get_pricing(driver_type="compute", driver_name="gce_images")
    try:
        price_dict = pricing[image_family]
    except KeyError:
        return 0

    size_type = "any"
    if "f1" in size_name:
        size_type = "f1"
    elif "g1" in size_name:
        size_type = "g1"

    price_dict_keys = price_dict.keys()

    for key in price_dict_keys:
        if key == "description":
            continue
        if re.search(".{1}vcpu or less", key) and cores <= int(key[0]):
            return float(price_dict[key]["price"])
        if re.search(".{1}-.{1}vcpu", key) and str(cores) in key:
            return float(price_dict[key]["price"])
        if re.search(".{1}vcpu or more", key) and cores >= int(key[0]):
            return float(price_dict[key]["price"])
        if key in {"standard", "enterprise", "web"} and key in image_name:
            return float(price_dict[key]["price"])
        if key in {"f1", "g1"} and size_type == key:
            return float(price_dict[key]["price"])
        elif key == "any":
            price = float(price_dict[key]["price"])
            return price * cores if "sles" not in image_name else price
    return 0


def invalidate_pricing_cache():
    # type: () -> None
    """
    Invalidate pricing cache for all the drivers.
    """
    PRICING_DATA["compute"] = {}
    PRICING_DATA["storage"] = {}
    _FILE_PRICING_CACHE.clear()


def clear_pricing_cache():
    # type: () -> None
    """
    Invalidate pricing cache for all the drivers.
    """
    invalidate_pricing_cache()


def clear_pricing_data():
    # type: () -> None
    """
    Invalidate pricing cache for all the drivers.

    Note: This method does the same thing as invalidate_pricing_cache and is
    here for backward compatibility reasons.
    """
    invalidate_pricing_cache()


def invalidate_module_pricing_cache(driver_type, driver_name):
    # type: (str, str) -> None
    """
    Invalidate the cache for the specified driver.

    :type driver_type: ``str``
    :param driver_type: Driver type ('compute' or 'storage')

    :type driver_name: ``str``
    :param driver_name: Driver name
    """
    if driver_name in PRICING_DATA[driver_type]:
        del PRICING_DATA[driver_type][driver_name]

    for pricing_data in _FILE_PRICING_CACHE.values():
        if driver_name in pricing_data[driver_type]:
            del pricing_data[driver_type][driver_name]


def download_pricing_file(file_url=DEFAULT_FILE_URL_S3_BUCKET, file_path=CUSTOM_PRICING_FILE_PATH):
    # type: (str, str) -> None
    """
    Download pricing file from the file_url and save it to file_path.

    :type file_url: ``str``
    :param file_url: URL pointing to the pricing file.

    :type file_path: ``str``
    :param file_path: Path where a download pricing file will be saved.
    """
    from libcloud.utils.connection import get_response_object

    dir_name = os.path.dirname(file_path)

    if not os.path.exists(dir_name):
        msg = "Can't write to {}, directory {}, doesn't exist".format(file_path, dir_name)
        raise ValueError(msg)

    if os.path.exists(file_path) and os.path.isdir(file_path):
        msg = "Can't write to %s file path because it's a" " directory" % (file_path)
        raise ValueError(msg)

    response = get_response_object(file_url)
    body = response.body

    try:
        data = json.loads(body)
    except JSONDecodeError:
        msg = "Provided URL doesn't contain valid pricing data"
        raise Exception(msg)

    if not data.get("updated", None):
        msg = "Provided URL doesn't contain valid pricing data"
        raise Exception(msg)

    with open(file_path, "w") as file_handle:
        file_handle.write(body)
