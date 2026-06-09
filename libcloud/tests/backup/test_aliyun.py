import unittest
import requests_mock
from libcloud.backup.providers import get_driver
from libcloud.backup.types import Provider, BackupTargetType, BackupTargetJobStatusType
from libcloud.backup.base import BackupTarget, BackupTargetJob, BackupTargetRecoveryPoint

class AliyunBackupTests(unittest.TestCase):
    def setUp(self):
        Backup = get_driver(Provider.ALIYUN)
        self.driver = Backup("key", "secret", region="cn-hangzhou")

    @requests_mock.Mocker()
    def test_list_targets(self, m):
        mock_response = """<?xml version="1.0" encoding="utf-8"?>
        <DescribeVaultsResponse>
            <RequestId>12345</RequestId>
            <Vaults>
                <Vault>
                    <VaultId>v-123</VaultId>
                    <VaultName>test-vault</VaultName>
                    <Description>test desc</Description>
                </Vault>
            </Vaults>
        </DescribeVaultsResponse>"""
        m.get(requests_mock.ANY, text=mock_response)

        targets = self.driver.list_targets()
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].id, "v-123")
        self.assertEqual(targets[0].name, "test-vault")
        self.assertEqual(targets[0].address, "test desc")

    @requests_mock.Mocker()
    def test_create_target(self, m):
        mock_response = """<?xml version="1.0" encoding="utf-8"?>
        <CreateVaultResponse>
            <RequestId>12345</RequestId>
            <VaultId>v-new</VaultId>
        </CreateVaultResponse>"""
        m.get(requests_mock.ANY, text=mock_response)

        target = self.driver.create_target(name="new-vault", address="new desc")
        self.assertEqual(target.id, "v-new")
        self.assertEqual(target.name, "new-vault")

    @requests_mock.Mocker()
    def test_update_target(self, m):
        mock_response = """<?xml version="1.0" encoding="utf-8"?>
        <UpdateVaultResponse>
            <RequestId>12345</RequestId>
        </UpdateVaultResponse>"""
        m.get(requests_mock.ANY, text=mock_response)

        target = BackupTarget(id="v-123", name="old", address="old", type=BackupTargetType.VIRTUAL, driver=self.driver)
        updated = self.driver.update_target(target, name="updated", address="updated desc")
        self.assertEqual(updated.name, "updated")
        self.assertEqual(updated.address, "updated desc")

    @requests_mock.Mocker()
    def test_delete_target(self, m):
        mock_response = """<?xml version="1.0" encoding="utf-8"?>
        <DeleteVaultResponse>
            <RequestId>12345</RequestId>
        </DeleteVaultResponse>"""
        m.get(requests_mock.ANY, text=mock_response)

        target = BackupTarget(id="v-123", name="old", address="old", type=BackupTargetType.VIRTUAL, driver=self.driver)
        result = self.driver.delete_target(target)
        self.assertTrue(result)

    @requests_mock.Mocker()
    def test_list_recovery_points(self, m):
        mock_response = """<?xml version="1.0" encoding="utf-8"?>
        <DescribeSnapshotsResponse>
            <RequestId>12345</RequestId>
            <Snapshots>
                <Snapshot>
                    <SnapshotId>s-123</SnapshotId>
                    <CreatedTime>2023-10-01T12:00:00Z</CreatedTime>
                </Snapshot>
            </Snapshots>
        </DescribeSnapshotsResponse>"""
        m.get(requests_mock.ANY, text=mock_response)

        target = BackupTarget(id="v-123", name="old", address="old", type=BackupTargetType.VIRTUAL, driver=self.driver)
        points = self.driver.list_recovery_points(target)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].id, "s-123")
        self.assertEqual(points[0].date, "2023-10-01T12:00:00Z")

    @requests_mock.Mocker()
    def test_recover_target(self, m):
        mock_response = """<?xml version="1.0" encoding="utf-8"?>
        <CreateRestoreJobResponse>
            <RequestId>12345</RequestId>
            <RestoreJobId>rj-123</RestoreJobId>
        </CreateRestoreJobResponse>"""
        m.get(requests_mock.ANY, text=mock_response)

        target = BackupTarget(id="v-123", name="old", address="old", type=BackupTargetType.VIRTUAL, driver=self.driver)
        point = BackupTargetRecoveryPoint(id="s-123", date="2023", target=target, driver=self.driver)
        job = self.driver.recover_target(target, point)
        self.assertEqual(job.id, "rj-123")
        self.assertEqual(job.status, BackupTargetJobStatusType.PENDING)

    @requests_mock.Mocker()
    def test_list_target_jobs(self, m):
        mock_response = """<?xml version="1.0" encoding="utf-8"?>
        <DescribeBackupJobsResponse>
            <RequestId>12345</RequestId>
            <BackupJobs>
                <BackupJob>
                    <BackupJobId>bj-123</BackupJobId>
                    <Status>COMPLETE</Status>
                    <Progress>100</Progress>
                </BackupJob>
            </BackupJobs>
        </DescribeBackupJobsResponse>"""
        m.get(requests_mock.ANY, text=mock_response)

        target = BackupTarget(id="v-123", name="old", address="old", type=BackupTargetType.VIRTUAL, driver=self.driver)
        jobs = self.driver.list_target_jobs(target)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "bj-123")
        self.assertEqual(jobs[0].status, BackupTargetJobStatusType.COMPLETED)
        self.assertEqual(jobs[0].progress, 100)

    @requests_mock.Mocker()
    def test_create_target_job(self, m):
        mock_response = """<?xml version="1.0" encoding="utf-8"?>
        <CreateBackupJobResponse>
            <RequestId>12345</RequestId>
            <BackupJobId>bj-new</BackupJobId>
        </CreateBackupJobResponse>"""
        m.get(requests_mock.ANY, text=mock_response)

        target = BackupTarget(id="v-123", name="old", address="old", type=BackupTargetType.VIRTUAL, driver=self.driver)
        job = self.driver.create_target_job(target)
        self.assertEqual(job.id, "bj-new")

    @requests_mock.Mocker()
    def test_cancel_target_job(self, m):
        mock_response = """<?xml version="1.0" encoding="utf-8"?>
        <CancelBackupJobResponse>
            <RequestId>12345</RequestId>
        </CancelBackupJobResponse>"""
        m.get(requests_mock.ANY, text=mock_response)

        target = BackupTarget(id="v-123", name="old", address="old", type=BackupTargetType.VIRTUAL, driver=self.driver)
        job = BackupTargetJob(id="bj-123", status="RUNNING", progress=10, target=target, driver=self.driver)
        result = self.driver.cancel_target_job(job)
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()
