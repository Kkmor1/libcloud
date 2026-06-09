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

import json
import datetime
from urllib.parse import parse_qs, urlparse

import requests_mock

from libcloud.test import unittest
from libcloud.backup.base import BackupTarget, BackupTargetRecoveryPoint
from libcloud.backup.types import Provider, BackupTargetType, BackupTargetJobStatusType
from libcloud.backup.providers import get_driver
from libcloud.backup.drivers.aliyun_hbr import AliyunHBRBackupDriver

XML_HEADERS = {"content-type": "application/xml"}


class AliyunHBRBackupDriverTestCase(unittest.TestCase):
    def setUp(self):
        self.driver = AliyunHBRBackupDriver("access-key", "secret")

    def test_provider_registration(self):
        driver = get_driver(Provider.ALIYUN_HBR)
        self.assertIs(driver, AliyunHBRBackupDriver)

    def test_create_target(self):
        body = """
<CreateBackupPlanResponse>
  <RequestId>req-create</RequestId>
  <Code>200</Code>
  <Message>successful</Message>
  <Success>true</Success>
  <PlanId>plan-123</PlanId>
</CreateBackupPlanResponse>
""".strip()

        def assertions(query):
            self.assertEqual(query["Action"][0], "CreateBackupPlan")
            self.assertEqual(query["PlanName"][0], "ecs-files")
            self.assertEqual(query["SourceType"][0], "ECS_FILE")
            self.assertEqual(query["VaultId"][0], "vault-001")
            self.assertEqual(query["InstanceId"][0], "i-instance-001")
            self.assertEqual(query["Schedule"][0], "I|1700000000|P1D")
            self.assertEqual(query["Retention"][0], "7")
            self.assertEqual(query["Include"][0], '["/data"]')
            self.assertEqual(query["Edition"][0], "STANDARD")

        with requests_mock.Mocker() as mocker:
            self._register_action(mocker, "POST", body, assertions)
            target = self.driver.create_target(
                name="ecs-files",
                address="i-instance-001",
                type=BackupTargetType.VIRTUAL,
                extra={
                    "vault_id": "vault-001",
                    "schedule": "I|1700000000|P1D",
                    "retention": 7,
                    "include": ["/data"],
                },
            )

        self.assertEqual(target.id, "plan-123")
        self.assertEqual(target.address, "i-instance-001")
        self.assertEqual(target.type, BackupTargetType.VIRTUAL)
        self.assertEqual(target.extra["vault_id"], "vault-001")

    def test_list_targets(self):
        body = """
<DescribeBackupPlansResponse>
  <RequestId>req-list</RequestId>
  <Success>true</Success>
  <Code>200</Code>
  <Message>successful</Message>
  <PageNumber>1</PageNumber>
  <PageSize>50</PageSize>
  <TotalCount>1</TotalCount>
  <BackupPlans>
    <BackupPlan>
      <PlanId>plan-123</PlanId>
      <PlanName>ecs-files</PlanName>
      <SourceType>ECS_FILE</SourceType>
      <VaultId>vault-001</VaultId>
      <InstanceId>i-instance-001</InstanceId>
      <BackupType>COMPLETE</BackupType>
      <Schedule>I|1700000000|P1D</Schedule>
      <Retention>7</Retention>
      <Disabled>false</Disabled>
      <Include>["/data"]</Include>
      <CreatedTime>1700000000</CreatedTime>
      <UpdatedTime>1700000100</UpdatedTime>
    </BackupPlan>
  </BackupPlans>
</DescribeBackupPlansResponse>
""".strip()

        def assertions(query):
            self.assertEqual(query["Action"][0], "DescribeBackupPlans")
            self.assertEqual(query["PageNumber"][0], "1")
            self.assertEqual(query["PageSize"][0], "50")
            self.assertEqual(query["Edition"][0], "STANDARD")

        with requests_mock.Mocker() as mocker:
            self._register_action(mocker, "GET", body, assertions)
            targets = self.driver.list_targets()

        self.assertEqual(len(targets), 1)
        target = targets[0]
        self.assertEqual(target.id, "plan-123")
        self.assertEqual(target.name, "ecs-files")
        self.assertEqual(target.address, "i-instance-001")
        self.assertEqual(target.type, BackupTargetType.VIRTUAL)
        self.assertEqual(target.extra["include"], ["/data"])

    def test_delete_target(self):
        target = self._target()
        body = """
<DeleteBackupPlanResponse>
  <RequestId>req-delete</RequestId>
  <Code>200</Code>
  <Message>successful</Message>
  <Success>true</Success>
</DeleteBackupPlanResponse>
""".strip()

        def assertions(query):
            self.assertEqual(query["Action"][0], "DeleteBackupPlan")
            self.assertEqual(query["PlanId"][0], "plan-123")
            self.assertEqual(query["VaultId"][0], "vault-001")
            self.assertEqual(query["SourceType"][0], "ECS_FILE")

        with requests_mock.Mocker() as mocker:
            self._register_action(mocker, "POST", body, assertions)
            result = self.driver.delete_target(target)

        self.assertTrue(result)

    def test_create_target_job(self):
        target = self._target()
        body = """
<ExecuteBackupPlanResponse>
  <RequestId>req-execute</RequestId>
  <Code>200</Code>
  <Message>successful</Message>
  <Success>true</Success>
  <JobId>job-123</JobId>
</ExecuteBackupPlanResponse>
""".strip()

        def assertions(query):
            self.assertEqual(query["Action"][0], "ExecuteBackupPlan")
            self.assertEqual(query["PlanId"][0], "plan-123")
            self.assertEqual(query["VaultId"][0], "vault-001")
            self.assertEqual(query["SourceType"][0], "ECS_FILE")

        with requests_mock.Mocker() as mocker:
            self._register_action(mocker, "POST", body, assertions)
            job = self.driver.create_target_job(target)

        self.assertEqual(job.id, "job-123")
        self.assertEqual(job.status, BackupTargetJobStatusType.PENDING)
        self.assertEqual(job.extra["operation"], "backup")

    def test_list_target_jobs(self):
        target = self._target()
        body = """
<DescribeBackupJobs2Response>
  <RequestId>req-jobs</RequestId>
  <Success>true</Success>
  <Code>200</Code>
  <Message>successful</Message>
  <PageNumber>1</PageNumber>
  <PageSize>50</PageSize>
  <TotalCount>1</TotalCount>
  <BackupJobs>
    <BackupJob>
      <JobId>job-123</JobId>
      <VaultId>vault-001</VaultId>
      <SourceType>ECS_FILE</SourceType>
      <Status>COMPLETE</Status>
      <Progress>7600</Progress>
      <ErrorMessage></ErrorMessage>
      <CreatedTime>1700000000</CreatedTime>
      <UpdatedTime>1700000200</UpdatedTime>
      <StartTime>1700000001</StartTime>
      <CompleteTime>1700000200</CompleteTime>
    </BackupJob>
  </BackupJobs>
</DescribeBackupJobs2Response>
""".strip()

        def assertions(query):
            self.assertEqual(query["Action"][0], "DescribeBackupJobs2")
            self.assertEqual(query["SourceType"][0], "ECS_FILE")
            self.assertEqual(query["Filters.1.Key"][0], "PlanId")
            self.assertEqual(query["Filters.1.Values.1"][0], "plan-123")
            self.assertEqual(query["Filters.1.Operator"][0], "EQUAL")

        with requests_mock.Mocker() as mocker:
            self._register_action(mocker, "GET", body, assertions)
            jobs = self.driver.list_target_jobs(target)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.id, "job-123")
        self.assertEqual(job.status, BackupTargetJobStatusType.COMPLETED)
        self.assertEqual(job.progress, 76)

    def test_list_recovery_points(self):
        target = self._target()
        start_date = datetime.datetime(2023, 11, 14, 22, 13, 20)
        end_date = datetime.datetime(2023, 11, 14, 23, 13, 20)
        body = """
<SearchHistoricalSnapshotsResponse>
  <RequestId>req-points</RequestId>
  <Success>true</Success>
  <Code>200</Code>
  <Message>successful</Message>
  <Limit>50</Limit>
  <TotalCount>1</TotalCount>
  <Snapshots>
    <Snapshot>
      <SnapshotId>snap-001</SnapshotId>
      <SnapshotHash>hash-001</SnapshotHash>
      <VaultId>vault-001</VaultId>
      <SourceType>ECS_FILE</SourceType>
      <InstanceId>i-instance-001</InstanceId>
      <Status>COMPLETE</Status>
      <Retention>7</Retention>
      <CreatedTime>1700000000</CreatedTime>
      <CompleteTime>1700000200</CompleteTime>
    </Snapshot>
  </Snapshots>
</SearchHistoricalSnapshotsResponse>
""".strip()

        def assertions(query):
            self.assertEqual(query["Action"][0], "SearchHistoricalSnapshots")
            self.assertEqual(query["SourceType"][0], "ECS_FILE")
            payload = json.loads(query["Query"][0])
            self.assertEqual(payload[0], {"field": "VaultId", "value": "vault-001", "operation": "MATCH_TERM"})
            self.assertEqual(payload[1], {"field": "PlanId", "value": "plan-123", "operation": "MATCH_TERM"})
            self.assertEqual(payload[2], {"field": "InstanceId", "value": "i-instance-001", "operation": "MATCH_TERM"})
            self.assertEqual(payload[3], {"field": "CompleteTime", "value": 1700000000, "operation": "GREATER_THAN_OR_EQUAL"})
            self.assertEqual(payload[4], {"field": "CompleteTime", "value": 1700003600, "operation": "LESS_THAN_OR_EQUAL"})

        with requests_mock.Mocker() as mocker:
            self._register_action(mocker, "GET", body, assertions)
            points = self.driver.list_recovery_points(target, start_date=start_date, end_date=end_date)

        self.assertEqual(len(points), 1)
        point = points[0]
        self.assertEqual(point.id, "snap-001")
        self.assertEqual(point.extra["snapshot_hash"], "hash-001")
        self.assertEqual(point.date, datetime.datetime.utcfromtimestamp(1700000200))

    def test_recover_target(self):
        target = self._target()
        recovery_point = self._recovery_point(target)
        body = """
<CreateRestoreJobResponse>
  <RequestId>req-restore</RequestId>
  <Code>200</Code>
  <Message>successful</Message>
  <Success>true</Success>
  <RestoreId>restore-001</RestoreId>
</CreateRestoreJobResponse>
""".strip()

        def assertions(query):
            self.assertEqual(query["Action"][0], "CreateRestoreJob")
            self.assertEqual(query["SourceType"][0], "ECS_FILE")
            self.assertEqual(query["RestoreType"][0], "ECS_FILE")
            self.assertEqual(query["VaultId"][0], "vault-001")
            self.assertEqual(query["SnapshotId"][0], "snap-001")
            self.assertEqual(query["SnapshotHash"][0], "hash-001")
            self.assertEqual(query["TargetInstanceId"][0], "i-instance-001")
            self.assertEqual(query["TargetPath"][0], "/restore")

        with requests_mock.Mocker() as mocker:
            self._register_action(mocker, "POST", body, assertions)
            job = self.driver.recover_target(target, recovery_point, path="/restore")

        self.assertEqual(job.id, "restore-001")
        self.assertEqual(job.status, BackupTargetJobStatusType.PENDING)
        self.assertEqual(job.extra["operation"], "restore")

    def test_delete_recovery_point(self):
        target = self._target()
        recovery_point = self._recovery_point(target)
        body = """
<DeleteSnapshotResponse>
  <RequestId>req-delete-snapshot</RequestId>
  <Code>200</Code>
  <Message>successful</Message>
  <Success>true</Success>
</DeleteSnapshotResponse>
""".strip()

        def assertions(query):
            self.assertEqual(query["Action"][0], "DeleteSnapshot")
            self.assertEqual(query["SnapshotId"][0], "snap-001")
            self.assertEqual(query["VaultId"][0], "vault-001")
            self.assertEqual(query["InstanceId"][0], "i-instance-001")
            self.assertEqual(query["SourceType"][0], "ECS_FILE")

        with requests_mock.Mocker() as mocker:
            self._register_action(mocker, "POST", body, assertions)
            result = self.driver.ex_delete_recovery_point(recovery_point)

        self.assertTrue(result)

    def _register_action(self, mocker, method, body, assertions):
        def matcher(request):
            query = parse_qs(urlparse(request.url).query)
            self.assertEqual(query["AccessKeyId"][0], "access-key")
            self.assertEqual(query["Format"][0], "XML")
            self.assertEqual(query["Version"][0], "2017-09-08")
            self.assertEqual(query["SignatureMethod"][0], "HMAC-SHA1")
            self.assertEqual(query["SignatureVersion"][0], "1.0")
            self.assertIn("Signature", query)
            assertions(query)
            return True

        mocker.register_uri(
            method,
            "https://hbr.aliyuncs.com/",
            text=body,
            headers=XML_HEADERS,
            additional_matcher=matcher,
        )

    def _target(self):
        return BackupTarget(
            id="plan-123",
            name="ecs-files",
            address="i-instance-001",
            type=BackupTargetType.VIRTUAL,
            driver=self.driver,
            extra={
                "plan_id": "plan-123",
                "source_type": "ECS_FILE",
                "vault_id": "vault-001",
                "instance_id": "i-instance-001",
                "schedule": "I|1700000000|P1D",
                "retention": 7,
                "edition": "STANDARD",
            },
        )

    def _recovery_point(self, target):
        return BackupTargetRecoveryPoint(
            id="snap-001",
            date=datetime.datetime.utcfromtimestamp(1700000200),
            target=target,
            driver=self.driver,
            extra={
                "snapshot_id": "snap-001",
                "snapshot_hash": "hash-001",
                "vault_id": "vault-001",
                "source_type": "ECS_FILE",
                "instance_id": "i-instance-001",
            },
        )


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
