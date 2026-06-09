from libcloud.common.aliyun import SignedAliyunConnection, AliyunXmlResponse
from libcloud.backup.base import (
    BackupDriver,
    BackupTarget,
    BackupTargetJob,
    BackupTargetRecoveryPoint,
)
from libcloud.backup.types import (
    Provider,
    BackupTargetType,
    BackupTargetJobStatusType,
)

class AliyunBackupResponse(AliyunXmlResponse):
    pass

class AliyunBackupConnection(SignedAliyunConnection):
    responseCls = AliyunBackupResponse
    host = "hbr.aliyuncs.com"
    api_version = "2017-09-08"

class AliyunBackupDriver(BackupDriver):
    name = "Alibaba Cloud Backup"
    website = "https://www.alibabacloud.com/product/cloud-backup"
    connectionCls = AliyunBackupConnection
    type = Provider.ALIYUN

    def __init__(self, key, secret=None, secure=True, host=None, port=None, region="cn-hangzhou", **kwargs):
        self.region = region
        host = host or "hbr.{}.aliyuncs.com".format(region)
        super().__init__(key=key, secret=secret, secure=secure, host=host, port=port, **kwargs)

    def get_supported_target_types(self):
        return [BackupTargetType.VIRTUAL, BackupTargetType.FILESYSTEM, BackupTargetType.DATABASE]

    def list_targets(self):
        params = {"Action": "DescribeVaults"}
        response = self.connection.request("/", params=params).object
        targets = []
        for vault in response.findall(".//Vault"):
            targets.append(self._to_target(vault))
        return targets

    def create_target(self, name, address, type=BackupTargetType.VIRTUAL, extra=None):
        params = {
            "Action": "CreateVault",
            "VaultName": name,
            "VaultType": "STANDARD",
            "Description": address,
        }
        if extra:
            params.update(extra)
        response = self.connection.request("/", params=params).object
        vault_id = response.findtext("VaultId")
        return BackupTarget(
            id=vault_id,
            name=name,
            address=address,
            type=type,
            driver=self,
            extra=extra
        )

    def update_target(self, target, name, address, extra=None):
        params = {
            "Action": "UpdateVault",
            "VaultId": target.id,
            "VaultName": name,
            "Description": address,
        }
        if extra:
            params.update(extra)
        self.connection.request("/", params=params)
        target.name = name
        target.address = address
        if extra:
            target.extra.update(extra)
        return target

    def delete_target(self, target):
        params = {
            "Action": "DeleteVault",
            "VaultId": target.id,
        }
        response = self.connection.request("/", params=params)
        return response.success()

    def list_recovery_points(self, target, start_date=None, end_date=None):
        params = {
            "Action": "DescribeSnapshots",
            "VaultId": target.id,
        }
        response = self.connection.request("/", params=params).object
        recovery_points = []
        for snapshot in response.findall(".//Snapshot"):
            recovery_points.append(self._to_recovery_point(snapshot, target))
        return recovery_points

    def recover_target(self, target, recovery_point, path=None):
        params = {
            "Action": "CreateRestoreJob",
            "VaultId": target.id,
            "SnapshotId": recovery_point.id,
            "TargetClientId": target.extra.get("clientId") if target.extra else "",
            "TargetPath": path or "/",
        }
        response = self.connection.request("/", params=params).object
        job_id = response.findtext("RestoreJobId")
        return BackupTargetJob(
            id=job_id,
            status=BackupTargetJobStatusType.PENDING,
            progress=0,
            target=target,
            driver=self,
        )

    def recover_target_out_of_place(self, target, recovery_point, recovery_target, path=None):
        params = {
            "Action": "CreateRestoreJob",
            "VaultId": target.id,
            "SnapshotId": recovery_point.id,
            "TargetClientId": recovery_target.extra.get("clientId") if recovery_target.extra else "",
            "TargetPath": path or "/",
        }
        response = self.connection.request("/", params=params).object
        job_id = response.findtext("RestoreJobId")
        return BackupTargetJob(
            id=job_id,
            status=BackupTargetJobStatusType.PENDING,
            progress=0,
            target=target,
            driver=self,
        )

    def list_target_jobs(self, target):
        params = {
            "Action": "DescribeBackupJobs",
            "VaultId": target.id,
        }
        response = self.connection.request("/", params=params).object
        jobs = []
        for job in response.findall(".//BackupJob"):
            jobs.append(self._to_job(job, target))
        return jobs

    def create_target_job(self, target, extra=None):
        params = {
            "Action": "CreateBackupJob",
            "VaultId": target.id,
        }
        if extra:
            params.update(extra)
        response = self.connection.request("/", params=params).object
        job_id = response.findtext("BackupJobId")
        return BackupTargetJob(
            id=job_id,
            status=BackupTargetJobStatusType.PENDING,
            progress=0,
            target=target,
            driver=self,
            extra=extra
        )

    def resume_target_job(self, job):
        raise NotImplementedError("resume_target_job not supported by Aliyun HBR")

    def suspend_target_job(self, job):
        raise NotImplementedError("suspend_target_job not supported by Aliyun HBR")

    def cancel_target_job(self, job):
        params = {
            "Action": "CancelBackupJob",
            "VaultId": job.target.id,
            "JobId": job.id,
        }
        response = self.connection.request("/", params=params)
        return response.success()

    def _to_target(self, element):
        vault_id = element.findtext("VaultId")
        name = element.findtext("VaultName")
        address = element.findtext("Description")
        return BackupTarget(
            id=vault_id,
            name=name,
            address=address,
            type=BackupTargetType.VIRTUAL,
            driver=self,
        )

    def _to_recovery_point(self, element, target):
        snapshot_id = element.findtext("SnapshotId")
        created_time = element.findtext("CreatedTime")
        return BackupTargetRecoveryPoint(
            id=snapshot_id,
            date=created_time,
            target=target,
            driver=self,
        )

    def _to_job(self, element, target):
        job_id = element.findtext("BackupJobId")
        status_str = element.findtext("Status")
        progress = int(element.findtext("Progress") or "0")
        
        status_map = {
            "RUNNING": BackupTargetJobStatusType.RUNNING,
            "COMPLETE": BackupTargetJobStatusType.COMPLETED,
            "FAILED": BackupTargetJobStatusType.FAILED,
            "CANCELED": BackupTargetJobStatusType.CANCELLED,
            "PENDING": BackupTargetJobStatusType.PENDING,
        }
        status = status_map.get(status_str, BackupTargetJobStatusType.PENDING)
        
        return BackupTargetJob(
            id=job_id,
            status=status,
            progress=progress,
            target=target,
            driver=self,
        )
