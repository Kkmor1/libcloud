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

__all__ = ["AlibabaBackupDriver"]

API_VERSION = "2014-05-26"
API_ENDPOINT = "ecs.aliyuncs.com"
DEFAULT_REGION = "cn-hangzhou"

SNAPSHOT_STATUS_MAP = {
    "progressing": BackupTargetJobStatusType.RUNNING,
    "accomplished": BackupTargetJobStatusType.COMPLETED,
    "failed": BackupTargetJobStatusType.FAILED,
}


class AlibabaBackupConnection(SignedAliyunConnection):
    api_version = API_VERSION
    host = API_ENDPOINT
    responseCls = AliyunXmlResponse
    service_name = "ecs"


class AlibabaBackupDriver(BackupDriver):
    name = "Alibaba Cloud Backup"
    website = "https://www.alibabacloud.com/product/ecs"
    connectionCls = AlibabaBackupConnection

    def __init__(self, key, secret=None, secure=True, host=None, port=None, region=DEFAULT_REGION, **kwargs):
        super().__init__(key=key, secret=secret, secure=secure, host=host, port=port, **kwargs)
        self.region = region

    def get_supported_target_types(self):
        return [BackupTargetType.VIRTUAL, BackupTargetType.VOLUME]

    def list_targets(self):
        params = {"Action": "DescribeInstances", "RegionId": self.region}
        data = self.connection.request("/", params=params).object
        return self._to_targets(data)

    def create_target(self, name, address, type=BackupTargetType.VIRTUAL, extra=None):
        extra = extra or {}
        if type == BackupTargetType.VOLUME:
            target_extra = {"volume-id": address, "region": self.region}
            target_extra.update(extra)
            return BackupTarget(
                id=address,
                name=name,
                address=address,
                type=type,
                driver=self,
                extra=target_extra,
            )
        target_extra = {"instance-id": address, "region": self.region}
        target_extra.update(extra)
        return BackupTarget(
            id=address,
            name=name,
            address=address,
            type=type,
            driver=self,
            extra=target_extra,
        )

    def update_target(self, target, name=None, address=None, extra=None):
        extra = extra or {}
        merged_extra = dict(target.extra)
        merged_extra.update(extra)
        return BackupTarget(
            id=target.id,
            name=name or target.name,
            address=address or target.address,
            type=target.type,
            driver=self,
            extra=merged_extra,
        )

    def delete_target(self, target):
        return True

    def list_recovery_points(self, target, start_date=None, end_date=None):
        params = {"Action": "DescribeSnapshots", "RegionId": self.region}
        if target.type == BackupTargetType.VOLUME:
            params["DiskId"] = target.address
        else:
            params["InstanceId"] = target.address
        if start_date:
            params["SnapshotType"] = "user"
        data = self.connection.request("/", params=params).object
        return self._to_recovery_points(data, target)

    def recover_target(self, target, recovery_point, path=None):
        params = {
            "Action": "CreateDisk",
            "RegionId": self.region,
            "SnapshotId": recovery_point.id,
            "DiskName": "recovery-{}".format(recovery_point.id),
        }
        data = self.connection.request("/", params=params).object
        disk_id = findtext(element=data, xpath="DiskId", namespace=None)
        return BackupTargetJob(
            id=recovery_point.id,
            status=BackupTargetJobStatusType.RUNNING,
            progress=0,
            target=target,
            driver=self,
            extra={"disk-id": disk_id, "snapshot-id": recovery_point.id},
        )

    def recover_target_out_of_place(self, target, recovery_point, recovery_target, path=None):
        params = {
            "Action": "CreateDisk",
            "RegionId": self.region,
            "SnapshotId": recovery_point.id,
            "DiskName": "recovery-{}".format(recovery_point.id),
        }
        data = self.connection.request("/", params=params).object
        disk_id = findtext(element=data, xpath="DiskId", namespace=None)
        return BackupTargetJob(
            id=recovery_point.id,
            status=BackupTargetJobStatusType.RUNNING,
            progress=0,
            target=recovery_target,
            driver=self,
            extra={"disk-id": disk_id, "snapshot-id": recovery_point.id},
        )

    def list_target_jobs(self, target):
        params = {"Action": "DescribeSnapshots", "RegionId": self.region, "Status": "progressing"}
        if target.type == BackupTargetType.VOLUME:
            params["DiskId"] = target.address
        else:
            params["InstanceId"] = target.address
        data = self.connection.request("/", params=params).object
        return self._to_jobs(data, target)

    def create_target_job(self, target, extra=None):
        extra = extra or {}
        params = {"Action": "CreateSnapshot", "RegionId": self.region}
        if target.type == BackupTargetType.VOLUME:
            params["DiskId"] = target.address
        else:
            params["InstanceId"] = target.address
        snapshot_name = extra.get("snapshot_name", "libcloud-backup-{}".format(target.id))
        params["SnapshotName"] = snapshot_name
        data = self.connection.request("/", params=params).object
        snapshot_id = findtext(element=data, xpath="SnapshotId", namespace=None)
        return BackupTargetJob(
            id=snapshot_id,
            status=BackupTargetJobStatusType.PENDING,
            progress=0,
            target=target,
            driver=self,
            extra={"snapshot-id": snapshot_id},
        )

    def cancel_target_job(self, job):
        params = {"Action": "DeleteSnapshot", "SnapshotId": job.id}
        try:
            self.connection.request("/", params=params)
            return True
        except Exception:
            return False

    def resume_target_job(self, job):
        raise NotImplementedError("resume_target_job not supported by Alibaba Cloud Backup")

    def suspend_target_job(self, job):
        raise NotImplementedError("suspend_target_job not supported by Alibaba Cloud Backup")

    def ex_delete_recovery_point(self, recovery_point):
        params = {"Action": "DeleteSnapshot", "SnapshotId": recovery_point.id}
        self.connection.request("/", params=params)
        return True

    def ex_get_recovery_point(self, recovery_point_id, target):
        params = {"Action": "DescribeSnapshots", "RegionId": self.region, "SnapshotId": recovery_point_id}
        data = self.connection.request("/", params=params).object
        points = self._to_recovery_points(data, target)
        if points:
            return points[0]
        return None

    def _to_targets(self, data):
        xpath = "Instances/Instance"
        return [self._to_target(el) for el in findall(element=data, xpath=xpath, namespace=None)]

    def _to_target(self, el):
        instance_id = findtext(element=el, xpath="InstanceId", namespace=None)
        name = findtext(element=el, xpath="InstanceName", namespace=None)
        region = findtext(element=el, xpath="RegionId", namespace=None)
        status = findtext(element=el, xpath="Status", namespace=None)
        return BackupTarget(
            id=instance_id,
            name=name,
            address=instance_id,
            type=BackupTargetType.VIRTUAL,
            driver=self,
            extra={"instance-id": instance_id, "region": region, "status": status},
        )

    def _to_recovery_points(self, data, target):
        xpath = "Snapshots/Snapshot"
        return [self._to_recovery_point(el, target) for el in findall(element=data, xpath=xpath, namespace=None)]

    def _to_recovery_point(self, el, target):
        snapshot_id = findtext(element=el, xpath="SnapshotId", namespace=None)
        date_str = findtext(element=el, xpath="CreationTime", namespace=None)
        date = parse_date(date_str) if date_str else None
        snapshot_name = findtext(element=el, xpath="SnapshotName", namespace=None)
        source_disk_id = findtext(element=el, xpath="SourceDiskId", namespace=None)
        source_disk_type = findtext(element=el, xpath="SourceDiskType", namespace=None)
        return BackupTargetRecoveryPoint(
            id=snapshot_id,
            date=date,
            target=target,
            driver=self,
            extra={
                "snapshot-name": snapshot_name,
                "source-disk-id": source_disk_id,
                "source-disk-type": source_disk_type,
            },
        )

    def _to_jobs(self, data, target):
        xpath = "Snapshots/Snapshot"
        return [self._to_job(el, target) for el in findall(element=data, xpath=xpath, namespace=None)]

    def _to_job(self, el, target):
        snapshot_id = findtext(element=el, xpath="SnapshotId", namespace=None)
        progress_str = findtext(element=el, xpath="Progress", namespace=None)
        progress = int(progress_str) if progress_str else 0
        status_str = findtext(element=el, xpath="Status", namespace=None)
        status = SNAPSHOT_STATUS_MAP.get(status_str, BackupTargetJobStatusType.PENDING)
        return BackupTargetJob(
            id=snapshot_id,
            status=status,
            progress=progress,
            target=target,
            driver=self,
            extra={"snapshot-id": snapshot_id},
        )
