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
from datetime import datetime

import requests_mock

from libcloud.test import unittest
from libcloud.utils.py3 import ET, u
from libcloud.backup.base import BackupTargetJob, BackupTargetRecoveryPoint
from libcloud.backup.types import BackupTargetType, BackupTargetJobStatusType
from libcloud.backup.drivers.aliyun import HBRBackupDriver


def _xml_response(action, content):
    root = ET.Element(action + "Response")
    request_id = ET.SubElement(root, "RequestId")
    request_id.text = str(hash(action))[:16]
    if isinstance(content, dict):
        _dict_to_xml(root, content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                _dict_to_xml(root, item)
            else:
                root.append(item)
    return ET.tostring(root, encoding="unicode")


def _dict_to_xml(parent, data):
    for key, value in data.items():
        if isinstance(value, list):
            for v in value:
                el = ET.SubElement(parent, key)
                if isinstance(v, dict):
                    _dict_to_xml(el, v)
                else:
                    el.text = str(v)
        elif isinstance(value, dict):
            el = ET.SubElement(parent, key)
            _dict_to_xml(el, value)
        else:
            el = ET.SubElement(parent, key)
            el.text = str(value)


def _build_plan_xml(plan_id, plan_name, schedule="I|1602673158|PT24H", retention=7):
    return ET.Element(
        "BackupPlan",
        attrib={
            "PlanId": plan_id,
            "PlanName": plan_name,
            "Schedule": schedule,
            "Retention": str(retention),
            "BackupType": "COMPLETE",
        },
    )


def _build_job_xml(job_id, status="COMPLETE", progress=100):
    return ET.Element(
        "Job",
        attrib={
            "JobId": job_id,
            "Status": status,
            "Progress": str(progress),
            "PlanId": "plan-001",
        },
    )


def _build_snapshot_xml(snapshot_id, created_time="2024-01-15 10:00:00"):
    return ET.Element(
        "Snapshot",
        attrib={
            "SnapshotId": snapshot_id,
            "CreatedTime": created_time,
            "Status": "COMPLETE",
            "SourceType": "ECS_FILE",
        },
    )


class HBRBackupDriverTests(unittest.TestCase):

    def setUp(self):
        self.driver = HBRBackupDriver(
            access_key_id="test-access-key",
            access_key_secret="test-access-secret",
            region="cn-hangzhou",
        )

    def test_driver_attributes(self):
        self.assertEqual(self.driver.name, "Alibaba Cloud HBR Backup Driver")
        self.assertEqual(self.driver.website, "https://www.aliyun.com/product/hbr")
        self.assertEqual(self.driver.region, "cn-hangzhou")

    def test_get_supported_target_types(self):
        types = self.driver.get_supported_target_types()
        self.assertIn(BackupTargetType.VIRTUAL, types)
        self.assertIn(BackupTargetType.PHYSICAL, types)
        self.assertIn(BackupTargetType.FILESYSTEM, types)

    @requests_mock.Mocker()
    def test_list_targets(self, m):
        plans = [
            {
                "PlanId": "plan-001",
                "PlanName": "Daily-Backup-ECS-Web",
                "Schedule": "I|1602673158|PT24H",
                "Retention": "7",
                "BackupType": "COMPLETE",
            },
            {
                "PlanId": "plan-002",
                "PlanName": "Weekly-Backup-DB",
                "Schedule": "I|1602673158|P7D",
                "Retention": "30",
                "BackupType": "COMPLETE",
            },
        ]

        def _match(request):
            return request.qs.get("Action", [""])[0] == "DescribeBackupPlans"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("DescribeBackupPlans", plans),
            status_code=200,
        )

        targets = self.driver.list_targets()
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0].id, "plan-001")
        self.assertEqual(targets[0].name, "Daily-Backup-ECS-Web")
        self.assertEqual(targets[0].extra["retention"], 7)
        self.assertEqual(targets[1].id, "plan-002")
        self.assertEqual(targets[1].name, "Weekly-Backup-DB")
        self.assertEqual(targets[1].extra["retention"], 30)

    @requests_mock.Mocker()
    def test_create_target(self, m):
        plan = {
            "PlanId": "plan-new-001",
            "PlanName": "My-Backup-Plan",
            "Schedule": "I|1602673158|PT24H",
            "Retention": "7",
            "BackupType": "COMPLETE",
        }

        def _match(request):
            return request.qs.get("Action", [""])[0] == "CreateBackupPlan"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("CreateBackupPlan", plan),
            status_code=200,
        )

        target = self.driver.create_target(name="My-Backup-Plan", address="")
        self.assertEqual(target.id, "plan-new-001")
        self.assertEqual(target.name, "My-Backup-Plan")
        self.assertEqual(target.extra["retention"], 7)
        self.assertEqual(target.type, BackupTargetType.VIRTUAL)

    @requests_mock.Mocker()
    def test_create_target_with_extra(self, m):
        plan = {
            "PlanId": "plan-new-002",
            "PlanName": "My-Custom-Plan",
            "Schedule": "I|1602673158|PT12H",
            "Retention": "14",
            "BackupType": "INCREMENTAL",
            "Detail": '{"Include":"/data"}',
        }

        def _match(request):
            return request.qs.get("Action", [""])[0] == "CreateBackupPlan"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("CreateBackupPlan", plan),
            status_code=200,
        )

        target = self.driver.create_target(
            name="My-Custom-Plan",
            address="",
            extra={
                "Schedule": "I|1602673158|PT12H",
                "Retention": 14,
                "BackupType": "INCREMENTAL",
                "Detail": {"Include": "/data"},
            },
        )
        self.assertEqual(target.id, "plan-new-002")
        self.assertEqual(target.extra["retention"], 14)
        self.assertEqual(target.extra["backup_type"], "INCREMENTAL")

    @requests_mock.Mocker()
    def test_update_target(self, m):
        plan = {
            "PlanId": "plan-001",
            "PlanName": "Updated-Plan-Name",
            "Schedule": "I|1602673158|PT12H",
            "Retention": "14",
            "BackupType": "COMPLETE",
        }

        def _match(request):
            return request.qs.get("Action", [""])[0] == "UpdateBackupPlan"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("UpdateBackupPlan", plan),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Old-Name",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        updated = self.driver.update_target(target=target, name="Updated-Plan-Name")
        self.assertEqual(updated.name, "Updated-Plan-Name")
        self.assertEqual(updated.extra["retention"], 14)

    @requests_mock.Mocker()
    def test_delete_target(self, m):
        def _match(request):
            return request.qs.get("Action", [""])[0] == "DeleteBackupPlan"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("DeleteBackupPlan", {"Success": "true"}),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Plan-To-Delete",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        result = self.driver.delete_target(target)
        self.assertTrue(result)

    @requests_mock.Mocker()
    def test_list_recovery_points(self, m):
        snapshots = [
            {
                "SnapshotId": "s-001",
                "CreatedTime": "2024-01-15 10:00:00",
                "Status": "COMPLETE",
                "SourceType": "ECS_FILE",
                "ParentSnapshotHash": "hash-abc",
            },
            {
                "SnapshotId": "s-002",
                "CreatedTime": "2024-01-16 10:00:00",
                "Status": "COMPLETE",
                "SourceType": "ECS_FILE",
                "ParentSnapshotHash": "hash-abc",
            },
        ]

        def _match(request):
            return request.qs.get("Action", [""])[0] == "DescribeSnapshots"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("DescribeSnapshots", snapshots),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        points = self.driver.list_recovery_points(target)
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].id, "s-001")
        self.assertEqual(points[1].id, "s-002")
        self.assertIsInstance(points[0], BackupTargetRecoveryPoint)
        self.assertIsInstance(points[0].date, datetime)

    @requests_mock.Mocker()
    def test_list_recovery_points_with_date_filter(self, m):
        snapshots = [
            {
                "SnapshotId": "s-001",
                "CreatedTime": "2024-01-15 10:00:00",
                "Status": "COMPLETE",
                "SourceType": "ECS_FILE",
            },
        ]

        def _match(request):
            return request.qs.get("Action", [""])[0] == "DescribeSnapshots"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("DescribeSnapshots", snapshots),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        start = datetime(2024, 1, 1)
        end = datetime(2024, 2, 1)
        points = self.driver.list_recovery_points(target, start_date=start, end_date=end)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].id, "s-001")

    @requests_mock.Mocker()
    def test_create_target_job(self, m):
        job = {
            "JobId": "job-001",
            "Status": "CREATED",
            "Progress": "0",
            "PlanId": "plan-001",
        }

        def _match(request):
            return request.qs.get("Action", [""])[0] == "ExecuteBackupPlan"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("ExecuteBackupPlan", job),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        job = self.driver.create_target_job(target)
        self.assertEqual(job.id, "job-001")
        self.assertEqual(job.status, BackupTargetJobStatusType.PENDING)
        self.assertIsInstance(job, BackupTargetJob)

    @requests_mock.Mocker()
    def test_list_target_jobs(self, m):
        jobs = [
            {"JobId": "job-001", "Status": "COMPLETE", "Progress": "100", "PlanId": "plan-001"},
            {"JobId": "job-002", "Status": "RUNNING", "Progress": "45", "PlanId": "plan-001"},
        ]

        def _match(request):
            return request.qs.get("Action", [""])[0] == "DescribeBackupJobs"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("DescribeBackupJobs", jobs),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        jobs_list = self.driver.list_target_jobs(target)
        self.assertEqual(len(jobs_list), 2)
        self.assertEqual(jobs_list[0].id, "job-001")
        self.assertEqual(jobs_list[0].status, BackupTargetJobStatusType.COMPLETED)
        self.assertEqual(jobs_list[0].progress, 100)
        self.assertEqual(jobs_list[1].id, "job-002")
        self.assertEqual(jobs_list[1].status, BackupTargetJobStatusType.RUNNING)
        self.assertEqual(jobs_list[1].progress, 45)

    @requests_mock.Mocker()
    def test_get_target_job(self, m):
        jobs = [
            {"JobId": "job-xyz", "Status": "COMPLETE", "Progress": "100", "PlanId": "plan-001"},
        ]

        def _match(request):
            return request.qs.get("Action", [""])[0] == "DescribeBackupJobs"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("DescribeBackupJobs", jobs),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        job = self.driver.get_target_job(target, "job-xyz")
        self.assertEqual(job.id, "job-xyz")
        self.assertEqual(job.status, BackupTargetJobStatusType.COMPLETED)

    @requests_mock.Mocker()
    def test_get_target_job_not_found(self, m):
        jobs = [
            {"JobId": "job-001", "Status": "COMPLETE", "Progress": "100", "PlanId": "plan-001"},
        ]

        def _match(request):
            return request.qs.get("Action", [""])[0] == "DescribeBackupJobs"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("DescribeBackupJobs", jobs),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        with self.assertRaises(ValueError):
            self.driver.get_target_job(target, "non-existent-job")

    @requests_mock.Mocker()
    def test_cancel_target_job(self, m):
        def _match(request):
            return request.qs.get("Action", [""])[0] == "CancelBackupJob"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("CancelBackupJob", {"Success": "true"}),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget, BackupTargetJob

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        job = BackupTargetJob(
            id="job-001",
            status=BackupTargetJobStatusType.RUNNING,
            progress=50,
            target=target,
            driver=self.driver,
        )
        result = self.driver.cancel_target_job(job)
        self.assertTrue(result)

    @requests_mock.Mocker()
    def test_recover_target(self, m):
        job = {
            "RestoreId": "restore-001",
            "Status": "CREATED",
            "Progress": "0",
            "PlanId": "plan-001",
        }

        def _match(request):
            return request.qs.get("Action", [""])[0] == "CreateRestoreJob"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("CreateRestoreJob", job),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget, BackupTargetRecoveryPoint

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        recovery_point = BackupTargetRecoveryPoint(
            id="s-001",
            date=datetime(2024, 1, 15),
            target=target,
            driver=self.driver,
        )
        result = self.driver.recover_target(target, recovery_point, path="/data")
        self.assertEqual(result.id, "restore-001")
        self.assertEqual(result.status, BackupTargetJobStatusType.PENDING)

    @requests_mock.Mocker()
    def test_recover_target_out_of_place(self, m):
        job = {
            "RestoreId": "restore-002",
            "Status": "CREATED",
            "Progress": "0",
            "PlanId": "plan-001",
        }

        def _match(request):
            return request.qs.get("Action", [""])[0] == "CreateRestoreJob"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("CreateRestoreJob", job),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget, BackupTargetRecoveryPoint

        target = BackupTarget(
            id="plan-001",
            name="Source-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        recovery_target = BackupTarget(
            id="plan-002",
            name="Recovery-Target",
            address="plan:plan-002",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        recovery_point = BackupTargetRecoveryPoint(
            id="s-001",
            date=datetime(2024, 1, 15),
            target=target,
            driver=self.driver,
        )
        result = self.driver.recover_target_out_of_place(
            target, recovery_point, recovery_target, path="/data"
        )
        self.assertEqual(result.id, "restore-002")
        self.assertEqual(result.status, BackupTargetJobStatusType.PENDING)

    @requests_mock.Mocker()
    def test_list_restore_jobs(self, m):
        jobs = [
            {
                "RestoreId": "restore-001",
                "Status": "COMPLETE",
                "Progress": "100",
                "PlanId": "plan-001",
            },
            {
                "RestoreId": "restore-002",
                "Status": "RUNNING",
                "Progress": "30",
                "PlanId": "plan-001",
            },
        ]

        def _match(request):
            return request.qs.get("Action", [""])[0] == "DescribeRestoreJobs"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("DescribeRestoreJobs", jobs),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        jobs_list = self.driver.list_restore_jobs(target)
        self.assertEqual(len(jobs_list), 2)
        self.assertEqual(jobs_list[0].id, "restore-001")
        self.assertEqual(jobs_list[0].status, BackupTargetJobStatusType.COMPLETED)
        self.assertEqual(jobs_list[1].id, "restore-002")

    @requests_mock.Mocker()
    def test_create_target_from_node(self, m):
        plan = {
            "PlanId": "plan-node-001",
            "PlanName": "node-web-01",
            "Schedule": "I|1602673158|PT24H",
            "Retention": "7",
            "BackupType": "COMPLETE",
        }

        def _match(request):
            return request.qs.get("Action", [""])[0] == "CreateBackupPlan"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("CreateBackupPlan", plan),
            status_code=200,
        )

        class FakeNode:
            name = "web-01"
            public_ips = ["192.168.1.100"]

        node = FakeNode()
        target = self.driver.create_target_from_node(node)
        self.assertEqual(target.id, "plan-node-001")
        self.assertEqual(target.name, "web-01")

    @requests_mock.Mocker()
    def test_create_target_from_storage_container(self, m):
        plan = {
            "PlanId": "plan-cont-001",
            "PlanName": "my-bucket",
            "Schedule": "I|1602673158|PT24H",
            "Retention": "7",
            "BackupType": "COMPLETE",
        }

        def _match(request):
            return request.qs.get("Action", [""])[0] == "CreateBackupPlan"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("CreateBackupPlan", plan),
            status_code=200,
        )

        class FakeContainer:
            name = "my-bucket"

            def get_cdn_url(self):
                return "https://my-bucket.oss-cn-hangzhou.aliyuncs.com/"

        container = FakeContainer()
        target = self.driver.create_target_from_storage_container(container)
        self.assertEqual(target.id, "plan-cont-001")
        self.assertEqual(target.name, "my-bucket")

    @requests_mock.Mocker()
    def test_status_mappings(self, m):
        job_data_list = [
            ("job-01", "COMPLETE", BackupTargetJobStatusType.COMPLETED),
            ("job-02", "RUNNING", BackupTargetJobStatusType.RUNNING),
            ("job-03", "CREATED", BackupTargetJobStatusType.PENDING),
            ("job-04", "FAILED", BackupTargetJobStatusType.FAILED),
            ("job-05", "CANCELLED", BackupTargetJobStatusType.CANCELLED),
            ("job-06", "EXPIRED", BackupTargetJobStatusType.FAILED),
            ("job-07", "PARTIAL_COMPLETE", BackupTargetJobStatusType.COMPLETED),
        ]

        jobs = [
            {"JobId": jid, "Status": status, "Progress": "100", "PlanId": "plan-001"}
            for jid, status, _ in job_data_list
        ]

        def _match(request):
            return request.qs.get("Action", [""])[0] == "DescribeBackupJobs"

        m.get(
            "https://hbr.aliyuncs.com/",
            additional_matcher=_match,
            text=_xml_response("DescribeBackupJobs", jobs),
            status_code=200,
        )

        from libcloud.backup.base import BackupTarget

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        result = self.driver.list_target_jobs(target)
        self.assertEqual(len(result), len(job_data_list))
        for i, (jid, _, expected_status) in enumerate(job_data_list):
            self.assertEqual(result[i].id, jid)
            self.assertEqual(result[i].status, expected_status)

    def test_resume_target_job_not_supported(self):
        from libcloud.backup.base import BackupTarget, BackupTargetJob

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        job = BackupTargetJob(
            id="job-001",
            status=BackupTargetJobStatusType.RUNNING,
            progress=50,
            target=target,
            driver=self.driver,
        )
        with self.assertRaises(NotImplementedError):
            self.driver.resume_target_job(job)

    def test_suspend_target_job_not_supported(self):
        from libcloud.backup.base import BackupTarget, BackupTargetJob

        target = BackupTarget(
            id="plan-001",
            name="Daily-Backup",
            address="plan:plan-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
        )
        job = BackupTargetJob(
            id="job-001",
            status=BackupTargetJobStatusType.RUNNING,
            progress=50,
            target=target,
            driver=self.driver,
        )
        with self.assertRaises(NotImplementedError):
            self.driver.suspend_target_job(job)

    @requests_mock.Mocker()
    def test_provider_registration(self, m):
        from libcloud.backup.providers import get_driver
        from libcloud.backup.types import Provider

        klass = get_driver(Provider.ALIYUN_HBR)
        self.assertEqual(klass.__name__, "HBRBackupDriver")


if __name__ == "__main__":
    sys.exit(unittest.main())