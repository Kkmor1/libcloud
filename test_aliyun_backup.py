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
from datetime import datetime
from unittest import mock

import requests_mock

from libcloud.backup.types import Provider, BackupTargetType, BackupTargetJobStatusType
from libcloud.backup.providers import get_driver
from libcloud.backup.drivers.aliyun import AliyunBackupDriver


class AliyunBackupDriverTestCase(unittest.TestCase):
    def setUp(self):
        self.driver = AliyunBackupDriver(
            "access_key_id",
            "access_key_secret",
            region="cn-hangzhou"
        )
        self.base_url = "https://hbr.cn-hangzhou.aliyuncs.com/"

    def test_get_supported_target_types(self):
        types = self.driver.get_supported_target_types()
        self.assertEqual(len(types), 3)
        self.assertIn(BackupTargetType.VOLUME, types)
        self.assertIn(BackupTargetType.FILESYSTEM, types)
        self.assertIn(BackupTargetType.VIRTUAL, types)

    @requests_mock.Mocker()
    def test_list_targets(self, m):
        response_xml = """<?xml version="1.0" encoding="UTF-8"?>
<DescribeVaultsResponse>
    <RequestId>12345</RequestId>
    <Vaults>
        <Vault>
            <VaultId>vault-1</VaultId>
            <VaultName>test-vault-1</VaultName>
            <VaultType>STANDARD</VaultType>
            <Description>Test Vault 1</Description>
        </Vault>
        <Vault>
            <VaultId>vault-2</VaultId>
            <VaultName>test-vault-2</VaultName>
            <VaultType>FILE</VaultType>
            <Description>Test Vault 2</Description>
        </Vault>
    </Vaults>
</DescribeVaultsResponse>"""
        m.get(self.base_url, text=response_xml)
        
        targets = self.driver.list_targets()
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0].id, "vault-1")
        self.assertEqual(targets[0].name, "test-vault-1")
        self.assertEqual(targets[0].type, BackupTargetType.VOLUME)
        self.assertEqual(targets[1].id, "vault-2")
        self.assertEqual(targets[1].name, "test-vault-2")
        self.assertEqual(targets[1].type, BackupTargetType.FILESYSTEM)

    @requests_mock.Mocker()
    def test_create_target(self, m):
        response_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CreateVaultResponse>
    <RequestId>12345</RequestId>
    <VaultId>new-vault</VaultId>
    <VaultName>new-test-vault</VaultName>
    <VaultType>STANDARD</VaultType>
    <Description>New Test Vault</Description>
</CreateVaultResponse>"""
        m.get(self.base_url, text=response_xml)
        
        target = self.driver.create_target(
            name="new-test-vault",
            address="",
            type=BackupTargetType.VOLUME,
            extra={"description": "New Test Vault"}
        )
        self.assertEqual(target.id, "new-vault")
        self.assertEqual(target.name, "new-test-vault")
        self.assertEqual(target.type, BackupTargetType.VOLUME)

    @requests_mock.Mocker()
    def test_delete_target(self, m):
        response_xml = """<?xml version="1.0" encoding="UTF-8"?>
<DeleteVaultResponse>
    <RequestId>12345</RequestId>
</DeleteVaultResponse>"""
        m.get(self.base_url, text=response_xml)
        
        # 创建一个临时目标用于测试
        from libcloud.backup.base import BackupTarget
        test_target = BackupTarget(
            id="test-vault-id",
            name="test-vault",
            address="test-vault-id",
            type=BackupTargetType.VOLUME,
            driver=self.driver,
            extra={}
        )
        
        result = self.driver.delete_target(target=test_target)
        self.assertTrue(result)

    @requests_mock.Mocker()
    def test_list_recovery_points(self, m):
        response_xml = """<?xml version="1.0" encoding="UTF-8"?>
<DescribeBackupsResponse>
    <RequestId>12345</RequestId>
    <Backups>
        <Backup>
            <BackupId>backup-1</BackupId>
            <BackupType>FULL</BackupType>
            <Status>COMPLETED</Status>
            <CompleteTime>2023-01-01T00:00:00Z</CompleteTime>
        </Backup>
        <Backup>
            <BackupId>backup-2</BackupId>
            <BackupType>INCREMENTAL</BackupType>
            <Status>COMPLETED</Status>
            <CompleteTime>2023-01-02T00:00:00Z</CompleteTime>
        </Backup>
    </Backups>
</DescribeBackupsResponse>"""
        m.get(self.base_url, text=response_xml)
        
        # 创建一个临时目标用于测试
        from libcloud.backup.base import BackupTarget
        test_target = BackupTarget(
            id="test-vault-id",
            name="test-vault",
            address="test-vault-id",
            type=BackupTargetType.VOLUME,
            driver=self.driver,
            extra={}
        )
        
        recovery_points = self.driver.list_recovery_points(target=test_target)
        self.assertEqual(len(recovery_points), 2)
        self.assertEqual(recovery_points[0].id, "backup-1")
        self.assertEqual(recovery_points[0].extra["backup_type"], "FULL")
        self.assertEqual(recovery_points[1].id, "backup-2")
        self.assertEqual(recovery_points[1].extra["backup_type"], "INCREMENTAL")

    @requests_mock.Mocker()
    def test_create_target_job(self, m):
        response_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CreateBackupJobResponse>
    <RequestId>12345</RequestId>
    <BackupJobId>job-1</BackupJobId>
    <Status>PENDING</Status>
    <Progress>0</Progress>
</CreateBackupJobResponse>"""
        m.get(self.base_url, text=response_xml)
        
        # 创建一个临时目标用于测试
        from libcloud.backup.base import BackupTarget
        test_target = BackupTarget(
            id="test-vault-id",
            name="test-vault",
            address="test-vault-id",
            type=BackupTargetType.VOLUME,
            driver=self.driver,
            extra={}
        )
        
        job = self.driver.create_target_job(
            target=test_target,
            extra={"source": "source-id", "backup_type": "FULL"}
        )
        self.assertEqual(job.id, "job-1")
        self.assertEqual(job.status, BackupTargetJobStatusType.PENDING)
        self.assertEqual(job.progress, 0)

    @requests_mock.Mocker()
    def test_recover_target(self, m):
        response_xml = """<?xml version="1.0" encoding="UTF-8"?>
<CreateRestoreJobResponse>
    <RequestId>12345</RequestId>
    <RestoreJobId>restore-job-1</RestoreJobId>
    <Status>PENDING</Status>
    <Progress>0</Progress>
</CreateRestoreJobResponse>"""
        m.get(self.base_url, text=response_xml)
        
        # 创建临时目标和恢复点用于测试
        from libcloud.backup.base import BackupTarget, BackupTargetRecoveryPoint
        test_target = BackupTarget(
            id="test-vault-id",
            name="test-vault",
            address="test-vault-id",
            type=BackupTargetType.VOLUME,
            driver=self.driver,
            extra={}
        )
        test_recovery_point = BackupTargetRecoveryPoint(
            id="test-backup-id",
            date=datetime.now(),
            target=test_target,
            driver=self.driver,
            extra={}
        )
        
        job = self.driver.recover_target(
            target=test_target,
            recovery_point=test_recovery_point,
            path="/"
        )
        self.assertEqual(job.id, "restore-job-1")
        self.assertEqual(job.status, BackupTargetJobStatusType.PENDING)


if __name__ == "__main__":
    unittest.main()
