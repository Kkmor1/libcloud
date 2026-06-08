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

__all__ = ["AliyunBackupDriver"]

from libcloud.utils.xml import findall, findtext
from libcloud.common.aliyun import AliyunXmlResponse, SignedAliyunConnection
from libcloud.backup.base import (
    BackupDriver,
    BackupTarget,
    BackupTargetJob,
    BackupTargetRecoveryPoint,
)
from libcloud.backup.types import BackupTargetType, BackupTargetJobStatusType
from libcloud.utils.iso8601 import parse_date

API_VERSION = "2017-03-01"
DEFAULT_REGION = "cn-hangzhou"
HOST_FORMAT = "hbr.{region}.aliyuncs.com"


class AliyunBackupResponse(AliyunXmlResponse):
    """
    Aliyun Backup response class.
    """

    namespace = None


class AliyunBackupConnection(SignedAliyunConnection):
    responseCls = AliyunBackupResponse
    api_version = API_VERSION

    def __init__(self, user_id, key, secure=True, host=None, port=None, **kwargs):
        super().__init__(
            user_id=user_id,
            key=key,
            secure=secure,
            host=host,
            port=port,
            api_version=API_VERSION,
            **kwargs,
        )


class AliyunBackupDriver(BackupDriver):
    name = "Aliyun Backup Driver"
    website = "https://www.aliyun.com/product/hbr"
    connectionCls = AliyunBackupConnection

    def __init__(self, access_id, secret, region=DEFAULT_REGION, **kwargs):
        self.region = region
        super().__init__(access_id, secret, **kwargs)
        self.connection.host = HOST_FORMAT.format(region=region)

    def get_supported_target_types(self):
        return [
            BackupTargetType.VOLUME,
            BackupTargetType.FILESYSTEM,
            BackupTargetType.VIRTUAL,
        ]

    def list_targets(self):
        params = {"Action": "DescribeVaults"}
        data = self.connection.request("/", params=params).object
        return self._to_targets(data)

    def create_target(self, name, address, type=BackupTargetType.VOLUME, extra=None):
        params = {
            "Action": "CreateVault",
            "VaultName": name,
            "VaultType": self._get_vault_type(type),
        }
        if extra:
            if "description" in extra:
                params["Description"] = extra["description"]
        data = self.connection.request("/", params=params).object
        return self._to_target(data)

    def update_target(self, target, name=None, address=None, extra=None):
        params = {
            "Action": "UpdateVault",
            "VaultId": target.id,
        }
        if name:
            params["VaultName"] = name
        if extra and "description" in extra:
            params["Description"] = extra["description"]
        data = self.connection.request("/", params=params).object
        return self._to_target(data)

    def delete_target(self, target):
        params = {"Action": "DeleteVault", "VaultId": target.id}
        self.connection.request("/", params=params)
        return True

    def list_recovery_points(self, target, start_date=None, end_date=None):
        params = {"Action": "DescribeBackups", "VaultId": target.id}
        if start_date:
            params["StartTime"] = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_date:
            params["EndTime"] = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        data = self.connection.request("/", params=params).object
        return self._to_recovery_points(data, target)

    def recover_target(self, target, recovery_point, path=None):
        params = {
            "Action": "CreateRestoreJob",
            "VaultId": target.id,
            "BackupId": recovery_point.id,
        }
        if path:
            params["RestorePath"] = path
        data = self.connection.request("/", params=params).object
        return self._to_job(data, target)

    def recover_target_out_of_place(self, target, recovery_point, recovery_target, path=None):
        params = {
            "Action": "CreateRestoreJob",
            "VaultId": recovery_target.id,
            "BackupId": recovery_point.id,
        }
        if path:
            params["RestorePath"] = path
        data = self.connection.request("/", params=params).object
        return self._to_job(data, recovery_target)

    def list_target_jobs(self, target):
        params = {"Action": "DescribeRestoreJobs", "VaultId": target.id}
        data = self.connection.request("/", params=params).object
        return self._to_jobs(data, target)

    def create_target_job(self, target, extra=None):
        params = {"Action": "CreateBackupJob", "VaultId": target.id}
        if extra:
            if "source" in extra:
                params["Source"] = extra["source"]
            if "backup_type" in extra:
                params["BackupType"] = extra["backup_type"]
        data = self.connection.request("/", params=params).object
        return self._to_job(data, target)

    def cancel_target_job(self, job):
        params = {"Action": "CancelRestoreJob", "RestoreJobId": job.id}
        self.connection.request("/", params=params)
        return True

    def resume_target_job(self, job):
        raise NotImplementedError("resume_target_job not supported for this driver")

    def suspend_target_job(self, job):
        raise NotImplementedError("suspend_target_job not supported for this driver")

    def _to_targets(self, data):
        xpath = "DescribeVaultsResponse/Vaults/Vault"
        return [self._to_target(el) for el in findall(element=data, xpath=xpath)]

    def _to_target(self, data):
        if findtext(element=data, xpath="CreateVaultResponse") is not None:
            data = findall(element=data, xpath="CreateVaultResponse")[0]
        id = findtext(element=data, xpath="VaultId")
        name = findtext(element=data, xpath="VaultName")
        vault_type = findtext(element=data, xpath="VaultType")
        description = findtext(element=data, xpath="Description")
        type = self._get_backup_target_type(vault_type)
        return BackupTarget(
            id=id,
            name=name,
            address=id,
            type=type,
            driver=self,
            extra={"vault_type": vault_type, "description": description},
        )

    def _to_recovery_points(self, data, target):
        xpath = "DescribeBackupsResponse/Backups/Backup"
        return [
            self._to_recovery_point(el, target)
            for el in findall(element=data, xpath=xpath)
        ]

    def _to_recovery_point(self, el, target):
        id = findtext(element=el, xpath="BackupId")
        date_str = findtext(element=el, xpath="CompleteTime")
        date = parse_date(date_str) if date_str else None
        return BackupTargetRecoveryPoint(
            id=id,
            date=date,
            target=target,
            driver=self,
            extra={
                "backup_type": findtext(element=el, xpath="BackupType"),
                "status": findtext(element=el, xpath="Status"),
            },
        )

    def _to_jobs(self, data, target):
        xpath = "DescribeRestoreJobsResponse/RestoreJobs/RestoreJob"
        return [self._to_job(el, target) for el in findall(element=data, xpath=xpath)]

    def _to_job(self, data, target=None):
        if findtext(element=data, xpath="CreateRestoreJobResponse") is not None:
            data = findall(element=data, xpath="CreateRestoreJobResponse")[0]
        elif findtext(element=data, xpath="CreateBackupJobResponse") is not None:
            data = findall(element=data, xpath="CreateBackupJobResponse")[0]
        id = findtext(element=data, xpath="RestoreJobId") or findtext(
            element=data, xpath="BackupJobId"
        )
        status_str = findtext(element=data, xpath="Status")
        status = self._get_job_status(status_str)
        progress = int(findtext(element=data, xpath="Progress") or 0)
        if not target:
            vault_id = findtext(element=data, xpath="VaultId")
            target = BackupTarget(
                id=vault_id,
                name=vault_id,
                address=vault_id,
                type=BackupTargetType.VOLUME,
                driver=self,
                extra={},
            )
        return BackupTargetJob(
            id=id,
            status=status,
            progress=progress,
            target=target,
            driver=self,
            extra={},
        )

    def _get_vault_type(self, target_type):
        type_map = {
            BackupTargetType.VOLUME: "STANDARD",
            BackupTargetType.FILESYSTEM: "FILE",
            BackupTargetType.VIRTUAL: "VM",
        }
        return type_map.get(target_type, "STANDARD")

    def _get_backup_target_type(self, vault_type):
        type_map = {
            "STANDARD": BackupTargetType.VOLUME,
            "FILE": BackupTargetType.FILESYSTEM,
            "VM": BackupTargetType.VIRTUAL,
        }
        return type_map.get(vault_type, BackupTargetType.VOLUME)

    def _get_job_status(self, status_str):
        status_map = {
            "Pending": BackupTargetJobStatusType.PENDING,
            "Running": BackupTargetJobStatusType.RUNNING,
            "Completed": BackupTargetJobStatusType.COMPLETED,
            "Failed": BackupTargetJobStatusType.FAILED,
            "Cancelled": BackupTargetJobStatusType.CANCELLED,
        }
        return status_map.get(status_str, BackupTargetJobStatusType.PENDING)
