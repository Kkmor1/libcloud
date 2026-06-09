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

import unittest
from unittest.mock import MagicMock
from xml.etree import ElementTree as ET

from libcloud.backup.base import BackupTarget, BackupTargetJob, BackupTargetRecoveryPoint
from libcloud.backup.drivers.alibaba import AlibabaBackupDriver
from libcloud.backup.types import BackupTargetType, BackupTargetJobStatusType


def _xml_response(body):
    resp = MagicMock()
    resp.status = 200
    resp.object = ET.fromstring(body)
    return resp


def _error_response():
    resp = MagicMock()
    resp.status = 404
    resp.object = ET.fromstring(
        """<?xml version="1.0" encoding="UTF-8"?>
<ErrorResponse>
    <RequestId>ERR001</RequestId>
    <HostId>ecs.aliyuncs.com</HostId>
    <Code>SnapshotNotFound</Code>
    <Message>The specified snapshot does not exist.</Message>
</ErrorResponse>"""
    )
    return resp


DESCRIBE_INSTANCES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DescribeInstancesResponse>
    <RequestId>ABC123</RequestId>
    <TotalCount>2</TotalCount>
    <PageNumber>1</PageNumber>
    <PageSize>10</PageSize>
    <Instances>
        <Instance>
            <InstanceId>i-instance001</InstanceId>
            <InstanceName>web-server-01</InstanceName>
            <RegionId>cn-hangzhou</RegionId>
            <Status>Running</Status>
        </Instance>
        <Instance>
            <InstanceId>i-instance002</InstanceId>
            <InstanceName>web-server-02</InstanceName>
            <RegionId>cn-hangzhou</RegionId>
            <Status>Stopped</Status>
        </Instance>
    </Instances>
</DescribeInstancesResponse>"""

DESCRIBE_SNAPSHOTS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DescribeSnapshotsResponse>
    <RequestId>DEF456</RequestId>
    <TotalCount>2</TotalCount>
    <PageNumber>1</PageNumber>
    <PageSize>10</PageSize>
    <Snapshots>
        <Snapshot>
            <SnapshotId>s-snap001</SnapshotId>
            <SnapshotName>daily-backup</SnapshotName>
            <SourceDiskId>d-disk001</SourceDiskId>
            <SourceDiskType>data</SourceDiskType>
            <CreationTime>2025-01-15T08:00:00Z</CreationTime>
            <Status>accomplished</Status>
            <Progress>100</Progress>
        </Snapshot>
        <Snapshot>
            <SnapshotId>s-snap002</SnapshotId>
            <SnapshotName>weekly-backup</SnapshotName>
            <SourceDiskId>d-disk002</SourceDiskId>
            <SourceDiskType>system</SourceDiskType>
            <CreationTime>2025-01-16T08:00:00Z</CreationTime>
            <Status>accomplished</Status>
            <Progress>100</Progress>
        </Snapshot>
    </Snapshots>
</DescribeSnapshotsResponse>"""

DESCRIBE_SNAPSHOTS_PROGRESSING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DescribeSnapshotsResponse>
    <RequestId>GHI789</RequestId>
    <TotalCount>1</TotalCount>
    <PageNumber>1</PageNumber>
    <PageSize>10</PageSize>
    <Snapshots>
        <Snapshot>
            <SnapshotId>s-snap003</SnapshotId>
            <SnapshotName>in-progress-backup</SnapshotName>
            <SourceDiskId>d-disk001</SourceDiskId>
            <SourceDiskType>data</SourceDiskType>
            <CreationTime>2025-01-17T08:00:00Z</CreationTime>
            <Status>progressing</Status>
            <Progress>55</Progress>
        </Snapshot>
    </Snapshots>
</DescribeSnapshotsResponse>"""

CREATE_SNAPSHOT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<CreateSnapshotResponse>
    <RequestId>JKL012</RequestId>
    <SnapshotId>s-snapnew</SnapshotId>
</CreateSnapshotResponse>"""

DELETE_SNAPSHOT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DeleteSnapshotResponse>
    <RequestId>MNO345</RequestId>
</DeleteSnapshotResponse>"""

CREATE_DISK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<CreateDiskResponse>
    <RequestId>PQR678</RequestId>
    <DiskId>d-newdisk001</DiskId>
</CreateDiskResponse>"""

DESCRIBE_SNAPSHOTS_EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DescribeSnapshotsResponse>
    <RequestId>EMPTY</RequestId>
    <TotalCount>0</TotalCount>
    <PageNumber>1</PageNumber>
    <PageSize>10</PageSize>
    <Snapshots/>
</DescribeSnapshotsResponse>"""


class AlibabaBackupDriverTestCase(unittest.TestCase):
    def setUp(self):
        self.driver = AlibabaBackupDriver(key="test_key", secret="test_secret", region="cn-hangzhou")
        self.mock_target = BackupTarget(
            id="i-instance001",
            name="web-server-01",
            address="i-instance001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
            extra={"instance-id": "i-instance001", "region": "cn-hangzhou"},
        )
        self.volume_target = BackupTarget(
            id="d-disk001",
            name="data-disk-01",
            address="d-disk001",
            type=BackupTargetType.VOLUME,
            driver=self.driver,
            extra={"volume-id": "d-disk001", "region": "cn-hangzhou"},
        )

    def test_get_supported_target_types(self):
        types = self.driver.get_supported_target_types()
        self.assertEqual(types, [BackupTargetType.VIRTUAL, BackupTargetType.VOLUME])

    def test_list_targets(self):
        self.driver.connection.request = MagicMock(return_value=_xml_response(DESCRIBE_INSTANCES_XML))
        targets = self.driver.list_targets()
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0].id, "i-instance001")
        self.assertEqual(targets[0].name, "web-server-01")
        self.assertEqual(targets[0].address, "i-instance001")
        self.assertEqual(targets[0].type, BackupTargetType.VIRTUAL)
        self.assertEqual(targets[0].extra["status"], "Running")
        self.assertEqual(targets[1].id, "i-instance002")
        self.assertEqual(targets[1].name, "web-server-02")

    def test_create_target_virtual(self):
        target = self.driver.create_target(
            name="my-instance", address="i-abc123", type=BackupTargetType.VIRTUAL
        )
        self.assertEqual(target.id, "i-abc123")
        self.assertEqual(target.name, "my-instance")
        self.assertEqual(target.address, "i-abc123")
        self.assertEqual(target.type, BackupTargetType.VIRTUAL)
        self.assertEqual(target.extra["instance-id"], "i-abc123")

    def test_create_target_volume(self):
        target = self.driver.create_target(
            name="my-disk", address="d-xyz789", type=BackupTargetType.VOLUME
        )
        self.assertEqual(target.id, "d-xyz789")
        self.assertEqual(target.name, "my-disk")
        self.assertEqual(target.address, "d-xyz789")
        self.assertEqual(target.type, BackupTargetType.VOLUME)
        self.assertEqual(target.extra["volume-id"], "d-xyz789")

    def test_create_target_with_extra(self):
        target = self.driver.create_target(
            name="my-disk",
            address="d-xyz789",
            type=BackupTargetType.VOLUME,
            extra={"description": "test disk"},
        )
        self.assertEqual(target.extra["description"], "test disk")
        self.assertEqual(target.extra["volume-id"], "d-xyz789")

    def test_update_target(self):
        updated = self.driver.update_target(
            target=self.mock_target, name="new-name", address="i-new"
        )
        self.assertEqual(updated.name, "new-name")
        self.assertEqual(updated.address, "i-new")
        self.assertEqual(updated.id, "i-instance001")

    def test_update_target_with_extra(self):
        updated = self.driver.update_target(
            target=self.mock_target, extra={"new_key": "new_value"}
        )
        self.assertEqual(updated.extra["new_key"], "new_value")

    def test_delete_target(self):
        result = self.driver.delete_target(self.mock_target)
        self.assertTrue(result)

    def test_list_recovery_points(self):
        self.driver.connection.request = MagicMock(return_value=_xml_response(DESCRIBE_SNAPSHOTS_XML))
        points = self.driver.list_recovery_points(self.mock_target)
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].id, "s-snap001")
        self.assertEqual(points[0].extra["snapshot-name"], "daily-backup")
        self.assertEqual(points[0].extra["source-disk-id"], "d-disk001")
        self.assertEqual(points[0].extra["source-disk-type"], "data")
        self.assertIsNotNone(points[0].date)
        self.assertEqual(points[1].id, "s-snap002")

    def test_list_recovery_points_volume_target(self):
        self.driver.connection.request = MagicMock(return_value=_xml_response(DESCRIBE_SNAPSHOTS_XML))
        points = self.driver.list_recovery_points(self.volume_target)
        self.assertEqual(len(points), 2)

    def test_recover_target(self):
        recovery_point = BackupTargetRecoveryPoint(
            id="s-snap001", date=None, target=self.mock_target, driver=self.driver, extra={}
        )
        self.driver.connection.request = MagicMock(return_value=_xml_response(CREATE_DISK_XML))
        job = self.driver.recover_target(self.mock_target, recovery_point)
        self.assertIsInstance(job, BackupTargetJob)
        self.assertEqual(job.id, "s-snap001")
        self.assertEqual(job.status, BackupTargetJobStatusType.RUNNING)
        self.assertEqual(job.extra["disk-id"], "d-newdisk001")
        self.assertEqual(job.extra["snapshot-id"], "s-snap001")

    def test_recover_target_out_of_place(self):
        recovery_target = BackupTarget(
            id="i-instance003",
            name="recovery-server",
            address="i-instance003",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
            extra={"instance-id": "i-instance003", "region": "cn-hangzhou"},
        )
        recovery_point = BackupTargetRecoveryPoint(
            id="s-snap001", date=None, target=self.mock_target, driver=self.driver, extra={}
        )
        self.driver.connection.request = MagicMock(return_value=_xml_response(CREATE_DISK_XML))
        job = self.driver.recover_target_out_of_place(self.mock_target, recovery_point, recovery_target)
        self.assertIsInstance(job, BackupTargetJob)
        self.assertEqual(job.target.id, "i-instance003")
        self.assertEqual(job.extra["disk-id"], "d-newdisk001")

    def test_list_target_jobs(self):
        self.driver.connection.request = MagicMock(
            return_value=_xml_response(DESCRIBE_SNAPSHOTS_PROGRESSING_XML)
        )
        jobs = self.driver.list_target_jobs(self.mock_target)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "s-snap003")
        self.assertEqual(jobs[0].status, BackupTargetJobStatusType.RUNNING)
        self.assertEqual(jobs[0].progress, 55)

    def test_create_target_job(self):
        self.driver.connection.request = MagicMock(return_value=_xml_response(CREATE_SNAPSHOT_XML))
        job = self.driver.create_target_job(self.mock_target)
        self.assertIsInstance(job, BackupTargetJob)
        self.assertEqual(job.id, "s-snapnew")
        self.assertEqual(job.status, BackupTargetJobStatusType.PENDING)
        self.assertEqual(job.progress, 0)

    def test_create_target_job_with_extra(self):
        self.driver.connection.request = MagicMock(return_value=_xml_response(CREATE_SNAPSHOT_XML))
        job = self.driver.create_target_job(
            self.mock_target, extra={"snapshot_name": "my-backup"}
        )
        self.assertIsInstance(job, BackupTargetJob)
        self.assertEqual(job.id, "s-snapnew")

    def test_cancel_target_job(self):
        job = BackupTargetJob(
            id="s-snap001",
            status=BackupTargetJobStatusType.RUNNING,
            progress=50,
            target=self.mock_target,
            driver=self.driver,
            extra={},
        )
        self.driver.connection.request = MagicMock(return_value=_xml_response(DELETE_SNAPSHOT_XML))
        result = self.driver.cancel_target_job(job)
        self.assertTrue(result)

    def test_cancel_target_job_failure(self):
        job = BackupTargetJob(
            id="s-snap-nonexist",
            status=BackupTargetJobStatusType.RUNNING,
            progress=50,
            target=self.mock_target,
            driver=self.driver,
            extra={},
        )
        self.driver.connection.request = MagicMock(side_effect=Exception("Snapshot not found"))
        result = self.driver.cancel_target_job(job)
        self.assertFalse(result)

    def test_resume_target_job_not_supported(self):
        job = BackupTargetJob(
            id="s-snap001",
            status=BackupTargetJobStatusType.RUNNING,
            progress=50,
            target=self.mock_target,
            driver=self.driver,
            extra={},
        )
        with self.assertRaises(NotImplementedError):
            self.driver.resume_target_job(job)

    def test_suspend_target_job_not_supported(self):
        job = BackupTargetJob(
            id="s-snap001",
            status=BackupTargetJobStatusType.RUNNING,
            progress=50,
            target=self.mock_target,
            driver=self.driver,
            extra={},
        )
        with self.assertRaises(NotImplementedError):
            self.driver.suspend_target_job(job)

    def test_ex_delete_recovery_point(self):
        recovery_point = BackupTargetRecoveryPoint(
            id="s-snap001", date=None, target=self.mock_target, driver=self.driver, extra={}
        )
        self.driver.connection.request = MagicMock(return_value=_xml_response(DELETE_SNAPSHOT_XML))
        result = self.driver.ex_delete_recovery_point(recovery_point)
        self.assertTrue(result)

    def test_ex_get_recovery_point(self):
        self.driver.connection.request = MagicMock(return_value=_xml_response(DESCRIBE_SNAPSHOTS_XML))
        point = self.driver.ex_get_recovery_point("s-snap001", self.mock_target)
        self.assertIsNotNone(point)
        self.assertEqual(point.id, "s-snap001")
        self.assertEqual(point.extra["snapshot-name"], "daily-backup")

    def test_ex_get_recovery_point_not_found(self):
        self.driver.connection.request = MagicMock(return_value=_xml_response(DESCRIBE_SNAPSHOTS_EMPTY_XML))
        point = self.driver.ex_get_recovery_point("s-nonexist", self.mock_target)
        self.assertIsNone(point)

    def test_driver_properties(self):
        self.assertEqual(self.driver.name, "Alibaba Cloud Backup")
        self.assertEqual(self.driver.website, "https://www.alibabacloud.com/product/ecs")
        self.assertEqual(self.driver.region, "cn-hangzhou")

    def test_create_target_job_volume_target(self):
        self.driver.connection.request = MagicMock(return_value=_xml_response(CREATE_SNAPSHOT_XML))
        job = self.driver.create_target_job(self.volume_target)
        self.assertIsInstance(job, BackupTargetJob)
        self.assertEqual(job.id, "s-snapnew")

    def test_list_target_jobs_volume_target(self):
        self.driver.connection.request = MagicMock(
            return_value=_xml_response(DESCRIBE_SNAPSHOTS_PROGRESSING_XML)
        )
        jobs = self.driver.list_target_jobs(self.volume_target)
        self.assertEqual(len(jobs), 1)

    def test_list_recovery_points_with_date_filter(self):
        import datetime
        self.driver.connection.request = MagicMock(return_value=_xml_response(DESCRIBE_SNAPSHOTS_XML))
        points = self.driver.list_recovery_points(
            self.mock_target, start_date=datetime.datetime(2025, 1, 1)
        )
        self.assertEqual(len(points), 2)

    def test_update_target_preserves_existing_extra(self):
        target = BackupTarget(
            id="i-001",
            name="old-name",
            address="i-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
            extra={"existing-key": "existing-value"},
        )
        updated = self.driver.update_target(target, name="new-name", extra={"new-key": "new-value"})
        self.assertEqual(updated.extra["existing-key"], "existing-value")
        self.assertEqual(updated.extra["new-key"], "new-value")
        self.assertEqual(updated.name, "new-name")


if __name__ == "__main__":
    unittest.main()
