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

__all__ = ["HBR_API_VERSION", "HBRBackupDriver"]

from datetime import datetime

from libcloud.utils.py3 import u
from libcloud.utils.xml import findall, findtext
from libcloud.utils.iso8601 import parse_date
from libcloud.common.aliyun import AliyunXmlResponse, SignedAliyunConnection
from libcloud.backup.base import (
    BackupDriver,
    BackupTarget,
    BackupTargetJob,
    BackupTargetRecoveryPoint,
)
from libcloud.backup.types import BackupTargetType, BackupTargetJobStatusType

HBR_API_VERSION = "2017-09-08"
HBR_API_HOST = "hbr.aliyuncs.com"
DEFAULT_SIGNATURE_VERSION = "1.0"


STATUS_MAPPINGS = {
    "COMPLETE": BackupTargetJobStatusType.COMPLETED,
    "PARTIAL_COMPLETE": BackupTargetJobStatusType.COMPLETED,
    "FAILED": BackupTargetJobStatusType.FAILED,
    "RUNNING": BackupTargetJobStatusType.RUNNING,
    "CREATED": BackupTargetJobStatusType.PENDING,
    "PENDING": BackupTargetJobStatusType.PENDING,
    "CANCELLED": BackupTargetJobStatusType.CANCELLED,
    "EXPIRED": BackupTargetJobStatusType.FAILED,
}


class HBRResponse(AliyunXmlResponse):
    namespace = None


class HBRConnection(SignedAliyunConnection):
    api_version = HBR_API_VERSION
    host = HBR_API_HOST
    responseCls = HBRResponse
    service_name = "hbr"


class HBRBackupDriver(BackupDriver):
    """
    Alibaba Cloud Hybrid Backup Recovery (HBR) driver.

    HBR provides backup and recovery services for ECS instances,
    file systems, NAS, and other data sources.

    Example usage:

    >>> from libcloud.backup.drivers.aliyun import HBRBackupDriver
    >>> driver = HBRBackupDriver(
    ...     access_key_id='your-access-key',
    ...     access_key_secret='your-access-secret',
    ... )
    >>> targets = driver.list_targets()
    >>> for t in targets:
    ...     print(t.name, t.id)
    """

    name = "Alibaba Cloud HBR Backup Driver"
    website = "https://www.aliyun.com/product/hbr"
    connectionCls = HBRConnection

    def __init__(self, access_key_id, access_key_secret, region=None):
        """
        :param access_key_id: Alibaba Cloud Access Key ID.
        :type access_key_id: ``str``

        :param access_key_secret: Alibaba Cloud Access Key Secret.
        :type access_key_secret: ``str``

        :param region: Region ID (e.g. 'cn-hangzhou', 'cn-beijing').
                       If not provided, defaults to 'cn-hangzhou'.
        :type region: ``str``
        """
        super().__init__(key=access_key_id, secret=access_key_secret)
        self.region = region or "cn-hangzhou"

    def get_supported_target_types(self):
        return [
            BackupTargetType.VIRTUAL,
            BackupTargetType.PHYSICAL,
            BackupTargetType.FILESYSTEM,
            BackupTargetType.DATABASE,
            BackupTargetType.OBJECT,
            BackupTargetType.VOLUME,
        ]

    def list_targets(self):
        params = {"Action": "DescribeBackupPlans"}
        if self.region:
            params["RegionId"] = self.region
        data = self.connection.request("/", params=params).object
        return self._to_targets(data)

    def create_target(self, name, address, type=BackupTargetType.VIRTUAL, extra=None):
        params = {
            "Action": "CreateBackupPlan",
            "PlanName": name,
        }
        if self.region:
            params["RegionId"] = self.region

        extra = extra or {}

        schedule = extra.get("Schedule", "I|1602673158|PT24H")
        retention = extra.get("Retention", 7)
        backup_type = extra.get("BackupType", "COMPLETE")
        detail = extra.get("Detail", {})
        include = detail.get("Include", "")
        exclude = detail.get("Exclude", "")

        if backup_type and backup_type != "COMPLETE":
            params["BackupType"] = backup_type
            if detail:
                try:
                    import json

                    params["Detail"] = json.dumps(detail)
                except ImportError:
                    import json as _json

                    params["Detail"] = _json.dumps(detail)

        params["Schedule"] = schedule
        params["Retention"] = str(retention)

        rule_list = extra.get("Rule", [])
        if rule_list:
            try:
                import json
            except ImportError:
                import json as _json
                json = _json
            params["Rule"] = json.dumps(rule_list)

        data = self.connection.request("/", params=params).object
        return self._to_target(data)

    def update_target(self, target, name=None, address=None, extra=None):
        params = {"Action": "UpdateBackupPlan", "PlanId": target.id}
        if self.region:
            params["RegionId"] = self.region

        if name:
            params["PlanName"] = name

        extra = extra or {}
        if extra.get("Schedule"):
            params["Schedule"] = extra["Schedule"]
        if extra.get("Retention"):
            params["Retention"] = str(extra["Retention"])
        if extra.get("Rule"):
            try:
                import json
            except ImportError:
                import json as _json
                json = _json
            params["Rule"] = json.dumps(extra["Rule"])

        data = self.connection.request("/", params=params).object
        return self._to_target(data)

    def delete_target(self, target):
        params = {"Action": "DeleteBackupPlan", "PlanId": target.id}
        if self.region:
            params["RegionId"] = self.region
        self.connection.request("/", params=params)
        return True

    def list_recovery_points(self, target, start_date=None, end_date=None):
        params = {
            "Action": "DescribeSnapshots",
            "PlanId": target.id,
        }
        if self.region:
            params["RegionId"] = self.region
        if start_date:
            params["StartTime"] = _format_timestamp(start_date)
        if end_date:
            params["EndTime"] = _format_timestamp(end_date)

        data = self.connection.request("/", params=params).object
        return self._to_recovery_points(data, target)

    def recover_target(self, target, recovery_point, path=None):
        return self._create_restore_job(
            target=target,
            recovery_point=recovery_point,
            recovery_target=None,
            path=path,
        )

    def recover_target_out_of_place(self, target, recovery_point, recovery_target, path=None):
        return self._create_restore_job(
            target=target,
            recovery_point=recovery_point,
            recovery_target=recovery_target,
            path=path,
        )

    def get_target_job(self, target, id):
        jobs = self.list_target_jobs(target)
        result = list(filter(lambda x: x.id == id, jobs))
        if not result:
            raise ValueError("Job with id %s not found" % id)
        return result[0]

    def list_target_jobs(self, target):
        params = {
            "Action": "DescribeBackupJobs",
            "PlanId": target.id,
        }
        if self.region:
            params["RegionId"] = self.region

        data = self.connection.request("/", params=params).object
        return self._to_jobs(data, target)

    def create_target_job(self, target, extra=None):
        params = {
            "Action": "ExecuteBackupPlan",
            "PlanId": target.id,
        }
        if self.region:
            params["RegionId"] = self.region

        data = self.connection.request("/", params=params).object
        return self._to_job(data, target)

    def resume_target_job(self, job):
        raise NotImplementedError("resume_target_job not supported for this driver")

    def suspend_target_job(self, job):
        raise NotImplementedError("suspend_target_job not supported for this driver")

    def cancel_target_job(self, job):
        params = {"Action": "CancelBackupJob", "JobId": job.id}
        if self.region:
            params["RegionId"] = self.region
        self.connection.request("/", params=params)
        return True

    def list_restore_jobs(self, target):
        params = {"Action": "DescribeRestoreJobs", "PlanId": target.id}
        if self.region:
            params["RegionId"] = self.region

        data = self.connection.request("/", params=params).object
        return self._to_jobs(data, target)

    def _create_restore_job(self, target, recovery_point, recovery_target=None, path=None):
        params = {
            "Action": "CreateRestoreJob",
            "SnapshotId": recovery_point.id,
            "SourceType": "ECS_FILE",
        }
        if self.region:
            params["RegionId"] = self.region
        if recovery_target:
            params["TargetInstanceId"] = recovery_target.id
        if path:
            params["TargetPath"] = path

        data = self.connection.request("/", params=params).object
        return self._to_job(data, target)

    def _to_targets(self, data):
        elements = findall(element=data, xpath="BackupPlan", namespace=None)
        return [self._to_target(el) for el in elements]

    def _to_target(self, element):
        plan_id = findtext(element=element, xpath="PlanId")
        plan_name = findtext(element=element, xpath="PlanName")
        plan_name = plan_name or findtext(element=element, xpath="BackupPlanName")
        schedule = findtext(element=element, xpath="Schedule") or ""
        retention = findtext(element=element, xpath="Retention") or "0"
        backup_type = findtext(element=element, xpath="BackupType") or "COMPLETE"
        vault_id = findtext(element=element, xpath="VaultId") or ""
        plan_desc = findtext(element=element, xpath="Description") or ""
        create_time = findtext(element=element, xpath="CreateTime")
        update_time = findtext(element=element, xpath="UpdatedTime")

        if plan_id:
            addr = "plan:%s" % plan_id
        else:
            addr = "plan:unknown"

        extra = {
            "schedule": schedule,
            "retention": int(retention) if retention.isdigit() else 0,
            "backup_type": backup_type,
            "vault_id": vault_id,
            "description": plan_desc,
            "region_id": self.region,
        }
        if create_time:
            extra["create_time"] = create_time
        if update_time:
            extra["update_time"] = update_time
        if backup_type != "COMPLETE":
            detail = findtext(element=element, xpath="Detail") or ""
            extra["detail"] = detail

        return BackupTarget(
            id=plan_id,
            name=plan_name,
            address=addr,
            type=BackupTargetType.VIRTUAL,
            driver=self,
            extra=extra,
        )

    def _to_recovery_points(self, data, target):
        elements = findall(element=data, xpath="Snapshot", namespace=None)
        return [self._to_recovery_point(el, target) for el in elements]

    def _to_recovery_point(self, element, target):
        snapshot_id = findtext(element=element, xpath="SnapshotId")
        created_time = findtext(element=element, xpath="CreatedTime") or "1970-01-01 00:00:00"
        status = findtext(element=element, xpath="Status") or ""
        parent_snapshot_hash = findtext(element=element, xpath="ParentSnapshotHash") or ""
        source_type = findtext(element=element, xpath="SourceType") or ""

        try:
            date = parse_date(created_time)
        except (ValueError, TypeError):
            try:
                date = datetime.strptime(created_time, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                date = datetime(1970, 1, 1)

        extra = {
            "snapshot_id": snapshot_id,
            "status": status,
            "parent_snapshot_hash": parent_snapshot_hash,
            "source_type": source_type,
        }

        return BackupTargetRecoveryPoint(
            id=snapshot_id,
            date=date,
            target=target,
            driver=self,
            extra=extra,
        )

    def _to_jobs(self, data, target):
        elements = findall(element=data, xpath="Job", namespace=None)
        return [self._to_job(el, target) for el in elements]

    def _to_job(self, element, target):
        job_id = findtext(element=element, xpath="JobId") or findtext(
            element=element, xpath="RestoreId"
        )
        status = findtext(element=element, xpath="Status") or ""
        progress_str = findtext(element=element, xpath="Progress") or "0"
        plan_id = findtext(element=element, xpath="PlanId") or ""
        created_time = findtext(element=element, xpath="CreatedTime") or "1970-01-01 00:00:00"
        updated_time = findtext(element=element, xpath="UpdatedTime") or ""
        job_type = findtext(element=element, xpath="JobType") or ""

        try:
            progress_int = int(progress_str)
        except (ValueError, TypeError):
            progress_int = 0

        mapped_status = STATUS_MAPPINGS.get(status.upper(), BackupTargetJobStatusType.PENDING)

        extra = {
            "plan_id": plan_id or target.id,
            "created_time": created_time,
            "updated_time": updated_time,
            "job_type": job_type,
        }

        return BackupTargetJob(
            id=job_id,
            status=mapped_status,
            progress=progress_int,
            target=target,
            driver=self,
            extra=extra,
        )


def _format_timestamp(dt):
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return None