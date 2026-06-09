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
import calendar
import datetime

from libcloud.utils.xml import findall, findtext
from libcloud.common.types import LibcloudError
from libcloud.common.aliyun import AliyunXmlResponse, SignedAliyunConnection
from libcloud.backup.base import (
    BackupDriver,
    BackupTarget,
    BackupTargetJob,
    BackupTargetRecoveryPoint,
)
from libcloud.backup.types import BackupTargetType, BackupTargetJobStatusType

__all__ = ["AliyunHBRBackupDriver"]

HBR_API_VERSION = "2017-09-08"
HBR_API_HOST = "hbr.aliyuncs.com"
DEFAULT_PAGE_SIZE = 50


class HBRConnection(SignedAliyunConnection):
    api_version = HBR_API_VERSION
    host = HBR_API_HOST
    responseCls = AliyunXmlResponse
    service_name = "hbr"


class AliyunHBRBackupDriver(BackupDriver):
    name = "Alibaba Cloud Backup"
    website = "https://www.alibabacloud.com/product/cloud-backup"
    connectionCls = HBRConnection
    path = "/"
    namespace = None

    TARGET_TYPE_TO_SOURCE_TYPE = {
        BackupTargetType.VIRTUAL: "ECS_FILE",
        BackupTargetType.FILESYSTEM: "NAS",
        BackupTargetType.OBJECT: "OSS",
    }

    SOURCE_TYPE_TO_TARGET_TYPE = {
        "ECS_FILE": BackupTargetType.VIRTUAL,
        "NAS": BackupTargetType.FILESYSTEM,
        "OSS": BackupTargetType.OBJECT,
    }

    JOB_STATUS_MAP = {
        "COMPLETE": BackupTargetJobStatusType.COMPLETED,
        "PARTIAL_COMPLETE": BackupTargetJobStatusType.COMPLETED,
        "FAILED": BackupTargetJobStatusType.FAILED,
        "CANCELLED": BackupTargetJobStatusType.CANCELLED,
        "RUNNING": BackupTargetJobStatusType.RUNNING,
        "IN_PROGRESS": BackupTargetJobStatusType.RUNNING,
        "PROCESSING": BackupTargetJobStatusType.RUNNING,
        "INIT": BackupTargetJobStatusType.PENDING,
        "CREATED": BackupTargetJobStatusType.PENDING,
        "PENDING": BackupTargetJobStatusType.PENDING,
        "WAITING": BackupTargetJobStatusType.PENDING,
    }

    def __init__(self, key, secret, region=None, edition="STANDARD", **kwargs):
        self.region = region
        self.edition = edition
        super().__init__(key=key, secret=secret, region=region, **kwargs)

    def get_supported_target_types(self):
        return [BackupTargetType.VIRTUAL, BackupTargetType.FILESYSTEM, BackupTargetType.OBJECT]

    def list_targets(self):
        return self._list_backup_plans()

    def create_target(self, name, address, type=BackupTargetType.VIRTUAL, extra=None):
        extra = extra or {}
        source_type = self._get_source_type(type=type, extra=extra)
        params = self._build_create_plan_params(
            name=name,
            address=address,
            source_type=source_type,
            extra=extra,
        )
        response = self._request(action="CreateBackupPlan", params=params, method="POST")
        plan_id = findtext(element=response, xpath="PlanId", namespace=self.namespace)
        target_extra = self._build_target_extra(
            plan_id=plan_id,
            source_type=source_type,
            address=address,
            extra=extra,
        )
        return BackupTarget(
            id=plan_id,
            name=name,
            address=self._get_target_address(source_type=source_type, extra=target_extra),
            type=self.SOURCE_TYPE_TO_TARGET_TYPE[source_type],
            driver=self,
            extra=target_extra,
        )

    def update_target(self, target, name=None, address=None, extra=None):
        merged_extra = dict(target.extra)
        merged_extra.update(extra or {})
        current_address = self._get_target_address(
            source_type=merged_extra["source_type"], extra=merged_extra
        )
        updated_address = address or current_address
        if updated_address != current_address:
            raise ValueError("Updating backup source address is not supported by this driver")

        params = self._build_update_plan_params(
            target=target,
            name=name or target.name,
            extra=merged_extra,
        )
        self._request(action="UpdateBackupPlan", params=params, method="POST")

        return BackupTarget(
            id=target.id,
            name=name or target.name,
            address=current_address,
            type=target.type,
            driver=self,
            extra=merged_extra,
        )

    def delete_target(self, target):
        params = {
            "PlanId": target.id,
            "SourceType": target.extra["source_type"],
            "VaultId": self._get_required_extra(target.extra, "vault_id"),
        }
        self._add_common_request_params(params=params, extra=target.extra)
        self._request(action="DeleteBackupPlan", params=params, method="POST")
        return True

    def list_recovery_points(self, target, start_date=None, end_date=None):
        query = self._build_snapshot_query(target=target, start_date=start_date, end_date=end_date)
        params = {
            "SourceType": target.extra["source_type"],
            "Query": json.dumps(query, separators=(",", ":")),
            "Limit": DEFAULT_PAGE_SIZE,
            "Order": "DESC",
            "SortBy": "CreatedTime",
        }
        self._add_common_request_params(params=params, extra=target.extra)
        recovery_points = []
        next_token = None

        while True:
            request_params = dict(params)
            if next_token:
                request_params["NextToken"] = next_token
            response = self._request(action="SearchHistoricalSnapshots", params=request_params)
            recovery_points.extend(self._to_recovery_points(element=response, target=target))
            next_token = findtext(element=response, xpath="NextToken", namespace=self.namespace)
            if not next_token:
                break

        return recovery_points

    def recover_target(self, target, recovery_point, path=None):
        return self.recover_target_out_of_place(
            target=target,
            recovery_point=recovery_point,
            recovery_target=target,
            path=path,
        )

    def recover_target_out_of_place(self, target, recovery_point, recovery_target, path=None):
        params = self._build_restore_params(
            target=target,
            recovery_point=recovery_point,
            recovery_target=recovery_target,
            path=path,
        )
        response = self._request(action="CreateRestoreJob", params=params, method="POST")
        restore_id = findtext(element=response, xpath="RestoreId", namespace=self.namespace)
        job_extra = {
            "operation": "restore",
            "restore_id": restore_id,
            "vault_id": recovery_point.extra.get("vault_id") or target.extra.get("vault_id"),
            "snapshot_id": recovery_point.id,
            "source_type": target.extra["source_type"],
        }
        return BackupTargetJob(
            id=restore_id,
            status=BackupTargetJobStatusType.PENDING,
            progress=0,
            target=recovery_target,
            driver=self,
            extra=job_extra,
        )

    def get_target_job(self, target, id):
        params = {
            "SourceType": target.extra["source_type"],
            "PageNumber": 1,
            "PageSize": 1,
            "Filters": [
                {
                    "Key": "JobId",
                    "Values": [id],
                    "Operator": "EQUAL",
                }
            ],
        }
        self._add_common_request_params(params=params, extra=target.extra)
        response = self._request(action="DescribeBackupJobs2", params=params)
        jobs = self._to_backup_jobs(element=response, target=target)
        if not jobs:
            raise ValueError("Backup job %s was not found" % (id))
        return jobs[0]

    def list_target_jobs(self, target):
        return self._list_backup_jobs(target=target)

    def create_target_job(self, target, extra=None):
        params = {
            "PlanId": target.id,
            "SourceType": target.extra["source_type"],
            "VaultId": self._get_required_extra(target.extra, "vault_id"),
        }
        request_extra = dict(target.extra)
        request_extra.update(extra or {})
        rule_id = request_extra.get("rule_id")
        if rule_id:
            params["RuleId"] = rule_id
        self._add_common_request_params(params=params, extra=request_extra)
        response = self._request(action="ExecuteBackupPlan", params=params, method="POST")
        job_id = findtext(element=response, xpath="JobId", namespace=self.namespace)
        return BackupTargetJob(
            id=job_id,
            status=BackupTargetJobStatusType.PENDING,
            progress=0,
            target=target,
            driver=self,
            extra={
                "operation": "backup",
                "job_id": job_id,
                "vault_id": target.extra.get("vault_id"),
                "source_type": target.extra["source_type"],
            },
        )

    def resume_target_job(self, job):
        raise NotImplementedError("resume_target_job not supported for this driver")

    def suspend_target_job(self, job):
        raise NotImplementedError("suspend_target_job not supported for this driver")

    def cancel_target_job(self, job):
        if job.extra.get("operation") == "restore":
            action = "CancelRestoreJob"
            params = {"RestoreId": job.id}
        else:
            action = "CancelBackupJob"
            params = {"JobId": job.id}

        self._add_common_request_params(params=params, extra=job.extra)
        self._request(action=action, params=params, method="POST")
        return True

    def ex_delete_recovery_point(self, recovery_point):
        target = recovery_point.target
        params = {
            "SnapshotId": recovery_point.id,
            "SourceType": target.extra["source_type"],
            "VaultId": recovery_point.extra.get("vault_id") or target.extra.get("vault_id"),
        }

        if target.extra["source_type"] == "ECS_FILE":
            instance_id = recovery_point.extra.get("instance_id") or target.extra.get("instance_id")
            if instance_id:
                params["InstanceId"] = instance_id
            client_id = recovery_point.extra.get("client_id") or target.extra.get("client_id")
            if client_id:
                params["ClientId"] = client_id

        self._add_common_request_params(params=params, extra=recovery_point.extra)
        self._request(action="DeleteSnapshot", params=params, method="POST")
        return True

    def ex_list_restore_jobs(self, target, page_size=DEFAULT_PAGE_SIZE):
        params = {
            "RestoreType": target.extra["source_type"],
            "PageNumber": 1,
            "PageSize": page_size,
        }
        self._add_common_request_params(params=params, extra=target.extra)
        return self._list_restore_jobs(target=target, params=params)

    def _list_backup_plans(self):
        params = {"PageNumber": 1, "PageSize": DEFAULT_PAGE_SIZE}
        plans = []

        while True:
            response = self._request(action="DescribeBackupPlans", params=params)
            plans.extend(self._to_targets(element=response))
            total_count = self._to_int(findtext(response, "TotalCount", namespace=self.namespace))
            page_number = self._to_int(findtext(response, "PageNumber", namespace=self.namespace))
            page_size = self._to_int(findtext(response, "PageSize", namespace=self.namespace))
            if not total_count or not page_size or page_number * page_size >= total_count:
                break
            params["PageNumber"] = page_number + 1

        return plans

    def _list_backup_jobs(self, target):
        params = {
            "SourceType": target.extra["source_type"],
            "PageNumber": 1,
            "PageSize": DEFAULT_PAGE_SIZE,
            "Filters": [
                {
                    "Key": "PlanId",
                    "Values": [target.id],
                    "Operator": "EQUAL",
                }
            ],
        }
        self._add_common_request_params(params=params, extra=target.extra)

        jobs = []
        while True:
            response = self._request(action="DescribeBackupJobs2", params=params)
            jobs.extend(self._to_backup_jobs(element=response, target=target))
            total_count = self._to_int(findtext(response, "TotalCount", namespace=self.namespace))
            page_number = self._to_int(findtext(response, "PageNumber", namespace=self.namespace))
            page_size = self._to_int(findtext(response, "PageSize", namespace=self.namespace))
            if not total_count or not page_size or page_number * page_size >= total_count:
                break
            params["PageNumber"] = page_number + 1

        return jobs

    def _list_restore_jobs(self, target, params):
        jobs = []
        request_params = dict(params)
        while True:
            response = self._request(action="DescribeRestoreJobs2", params=request_params)
            jobs.extend(self._to_restore_jobs(element=response, target=target))
            total_count = self._to_int(findtext(response, "TotalCount", namespace=self.namespace))
            page_number = self._to_int(findtext(response, "PageNumber", namespace=self.namespace))
            page_size = self._to_int(findtext(response, "PageSize", namespace=self.namespace))
            if not total_count or not page_size or page_number * page_size >= total_count:
                break
            request_params["PageNumber"] = page_number + 1
        return jobs

    def _build_create_plan_params(self, name, address, source_type, extra):
        params = {
            "SourceType": source_type,
            "PlanName": name,
            "BackupType": extra.get("backup_type", "COMPLETE"),
            "VaultId": self._get_required_extra(extra, "vault_id"),
        }
        self._add_plan_configuration(params=params, extra=extra)
        self._add_source_specific_create_params(
            params=params,
            source_type=source_type,
            address=address,
            extra=extra,
        )
        return params

    def _build_update_plan_params(self, target, name, extra):
        params = {"PlanId": target.id, "PlanName": name, "SourceType": target.extra["source_type"]}
        params["VaultId"] = extra.get("vault_id") or self._get_required_extra(target.extra, "vault_id")
        self._add_plan_configuration(params=params, extra=extra)
        return params

    def _add_plan_configuration(self, params, extra):
        schedule = extra.get("schedule")
        retention = extra.get("retention")
        rules = extra.get("rules")

        if schedule is not None:
            params["Schedule"] = schedule
        if retention is not None:
            params["Retention"] = retention
        if rules:
            params["Rule"] = [self._normalize_rule(rule) for rule in rules]
        elif schedule is None or retention is None:
            raise ValueError("extra must include schedule and retention, or a non-empty rules list")

        detail = extra.get("detail")
        if detail is not None:
            params["Detail"] = self._json_value(detail)

        speed_limit = extra.get("speed_limit")
        if speed_limit is not None:
            params["SpeedLimit"] = speed_limit

        include = extra.get("include")
        if include is not None:
            params["Include"] = self._json_value(include)

        exclude = extra.get("exclude")
        if exclude is not None:
            params["Exclude"] = self._json_value(exclude)

        options = extra.get("options")
        if options is not None:
            params["Options"] = self._json_value(options)

        paths = extra.get("paths") or extra.get("path")
        if paths is not None:
            params["Path"] = paths

        keep_latest = extra.get("keep_latest_snapshots")
        if keep_latest is not None:
            params["KeepLatestSnapshots"] = keep_latest

        disabled = extra.get("disabled")
        if disabled is not None:
            params["Disabled"] = disabled

    def _add_source_specific_create_params(self, params, source_type, address, extra):
        if source_type == "ECS_FILE":
            params["InstanceId"] = extra.get("instance_id", address)
        elif source_type == "NAS":
            params["FileSystemId"] = extra.get("file_system_id", address)
            params["CreateTime"] = self._get_required_extra(extra, "create_time")
        elif source_type == "OSS":
            params["Bucket"] = extra.get("bucket", address)
            prefix = extra.get("prefix")
            if prefix is not None:
                params["Prefix"] = prefix
        else:
            raise ValueError("Unsupported source_type: %s" % (source_type))

    def _build_target_extra(self, plan_id, source_type, address, extra):
        target_extra = dict(extra)
        target_extra["plan_id"] = plan_id
        target_extra["source_type"] = source_type
        target_extra.setdefault("edition", self._get_edition(extra))

        if source_type == "ECS_FILE":
            target_extra.setdefault("instance_id", address)
        elif source_type == "NAS":
            target_extra.setdefault("file_system_id", address)
        elif source_type == "OSS":
            target_extra.setdefault("bucket", address)

        return target_extra

    def _build_snapshot_query(self, target, start_date=None, end_date=None):
        query = [
            {
                "field": "VaultId",
                "value": self._get_required_extra(target.extra, "vault_id"),
                "operation": "MATCH_TERM",
            },
            {"field": "PlanId", "value": target.id, "operation": "MATCH_TERM"},
        ]
        source_type = target.extra["source_type"]
        if source_type == "ECS_FILE":
            query.append(
                {
                    "field": "InstanceId",
                    "value": self._get_required_extra(target.extra, "instance_id"),
                    "operation": "MATCH_TERM",
                }
            )
        elif source_type == "NAS":
            query.append(
                {
                    "field": "FileSystemId",
                    "value": self._get_required_extra(target.extra, "file_system_id"),
                    "operation": "MATCH_TERM",
                }
            )
            query.append(
                {
                    "field": "CreateTime",
                    "value": self._get_required_extra(target.extra, "create_time"),
                    "operation": "MATCH_TERM",
                }
            )
        elif source_type == "OSS":
            query.append(
                {
                    "field": "Bucket",
                    "value": self._get_required_extra(target.extra, "bucket"),
                    "operation": "MATCH_TERM",
                }
            )
        else:
            raise ValueError("Unsupported source_type: %s" % (source_type))

        if start_date is not None:
            query.append(
                {
                    "field": "CompleteTime",
                    "value": self._datetime_to_timestamp(start_date),
                    "operation": "GREATER_THAN_OR_EQUAL",
                }
            )

        if end_date is not None:
            query.append(
                {
                    "field": "CompleteTime",
                    "value": self._datetime_to_timestamp(end_date),
                    "operation": "LESS_THAN_OR_EQUAL",
                }
            )

        return query

    def _build_restore_params(self, target, recovery_point, recovery_target, path=None):
        source_type = target.extra["source_type"]
        params = {
            "SourceType": source_type,
            "RestoreType": source_type,
            "VaultId": recovery_point.extra.get("vault_id") or target.extra.get("vault_id"),
            "SnapshotId": recovery_point.id,
        }
        snapshot_hash = recovery_point.extra.get("snapshot_hash")
        if snapshot_hash:
            params["SnapshotHash"] = snapshot_hash

        self._add_common_request_params(params=params, extra=recovery_target.extra)

        if source_type == "ECS_FILE":
            params["TargetInstanceId"] = recovery_target.extra.get(
                "target_instance_id", recovery_target.extra.get("instance_id")
            )
            target_path = (
                path
                or recovery_target.extra.get("target_path")
                or recovery_target.extra.get("restore_path")
            )
            if target_path:
                params["TargetPath"] = target_path
            include = recovery_target.extra.get("restore_include")
            if include is not None:
                params["Include"] = self._json_value(include)
            exclude = recovery_target.extra.get("restore_exclude")
            if exclude is not None:
                params["Exclude"] = self._json_value(exclude)
            options = recovery_target.extra.get("restore_options")
            if options is not None:
                params["Options"] = self._json_value(options)
        elif source_type == "NAS":
            params["TargetFileSystemId"] = recovery_target.extra.get(
                "target_file_system_id", recovery_target.extra.get("file_system_id")
            )
            params["TargetCreateTime"] = recovery_target.extra.get(
                "target_create_time", recovery_target.extra.get("create_time")
            )
        elif source_type == "OSS":
            params["TargetBucket"] = recovery_target.extra.get(
                "target_bucket", recovery_target.extra.get("bucket")
            )
            target_prefix = (
                path
                or recovery_target.extra.get("target_prefix")
                or recovery_target.extra.get("prefix")
            )
            if target_prefix is not None:
                params["TargetPrefix"] = target_prefix
        else:
            raise ValueError("Unsupported source_type: %s" % (source_type))

        return params

    def _request(self, action, params=None, method="GET"):
        request_params = {"Action": action}
        encoded_params = self._encode_request_params(params or {})
        request_params.update(encoded_params)
        if "Edition" not in request_params and self.edition:
            request_params["Edition"] = self.edition
        return self.connection.request(self.path, params=request_params, method=method).object

    def _encode_request_params(self, params):
        encoded = {}
        for key, value in params.items():
            self._flatten_param(key, value, encoded)
        return encoded

    def _flatten_param(self, prefix, value, container):
        if value is None:
            return

        if isinstance(value, dict):
            for key in sorted(value.keys()):
                self._flatten_param("%s.%s" % (prefix, key), value[key], container)
            return

        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value, start=1):
                self._flatten_param("%s.%d" % (prefix, index), item, container)
            return

        container[prefix] = self._serialize_value(value)

    def _to_targets(self, element):
        plans = findall(element=element, xpath="BackupPlans/BackupPlan", namespace=self.namespace)
        return [self._to_target(item) for item in plans]

    def _to_target(self, element):
        source_type = findtext(element=element, xpath="SourceType", namespace=self.namespace)
        target_type = self.SOURCE_TYPE_TO_TARGET_TYPE.get(source_type)
        if target_type is None:
            raise LibcloudError("Unsupported backup source type: %s" % (source_type), driver=self)

        extra = {
            "plan_id": findtext(element=element, xpath="PlanId", namespace=self.namespace),
            "source_type": source_type,
            "vault_id": findtext(element=element, xpath="VaultId", namespace=self.namespace),
            "backup_type": findtext(element=element, xpath="BackupType", namespace=self.namespace),
            "schedule": findtext(element=element, xpath="Schedule", namespace=self.namespace),
            "retention": self._to_int(
                findtext(element=element, xpath="Retention", namespace=self.namespace)
            ),
            "created_time": self._to_int(
                findtext(element=element, xpath="CreatedTime", namespace=self.namespace)
            ),
            "updated_time": self._to_int(
                findtext(element=element, xpath="UpdatedTime", namespace=self.namespace)
            ),
            "disabled": self._to_bool(
                findtext(element=element, xpath="Disabled", namespace=self.namespace)
            ),
            "edition": self.edition,
        }

        instance_id = findtext(element=element, xpath="InstanceId", namespace=self.namespace)
        if instance_id:
            extra["instance_id"] = instance_id

        client_id = findtext(element=element, xpath="ClientId", namespace=self.namespace)
        if client_id:
            extra["client_id"] = client_id

        file_system_id = findtext(element=element, xpath="FileSystemId", namespace=self.namespace)
        if file_system_id:
            extra["file_system_id"] = file_system_id

        create_time = findtext(element=element, xpath="CreateTime", namespace=self.namespace)
        if create_time:
            extra["create_time"] = self._to_int(create_time)

        bucket = findtext(element=element, xpath="Bucket", namespace=self.namespace)
        if bucket:
            extra["bucket"] = bucket

        prefix = findtext(element=element, xpath="Prefix", namespace=self.namespace)
        if prefix:
            extra["prefix"] = prefix

        include = self._safe_json(findtext(element=element, xpath="Include", namespace=self.namespace))
        if include is not None:
            extra["include"] = include

        exclude = self._safe_json(findtext(element=element, xpath="Exclude", namespace=self.namespace))
        if exclude is not None:
            extra["exclude"] = exclude

        options = self._safe_json(findtext(element=element, xpath="Options", namespace=self.namespace))
        if options is not None:
            extra["options"] = options

        detail = self._safe_json(findtext(element=element, xpath="Detail", namespace=self.namespace))
        if detail is not None:
            extra["detail"] = detail

        paths = [path.text for path in findall(element, "Paths/Path", namespace=self.namespace) if path.text]
        if paths:
            extra["paths"] = paths

        rules = [self._to_rule(rule) for rule in findall(element, "Rules/Rule", namespace=self.namespace)]
        if rules:
            extra["rules"] = rules

        return BackupTarget(
            id=extra["plan_id"],
            name=findtext(element=element, xpath="PlanName", namespace=self.namespace),
            address=self._get_target_address(source_type=source_type, extra=extra),
            type=target_type,
            driver=self,
            extra=extra,
        )

    def _to_rule(self, element):
        return {
            "rule_id": findtext(element=element, xpath="RuleId", namespace=self.namespace),
            "rule_name": findtext(element=element, xpath="RuleName", namespace=self.namespace),
            "schedule": findtext(element=element, xpath="Schedule", namespace=self.namespace),
            "retention": self._to_int(
                findtext(element=element, xpath="Retention", namespace=self.namespace)
            ),
            "disabled": self._to_bool(
                findtext(element=element, xpath="Disabled", namespace=self.namespace)
            ),
            "backup_type": findtext(element=element, xpath="BackupType", namespace=self.namespace),
            "do_copy": self._to_bool(findtext(element=element, xpath="DoCopy", namespace=self.namespace)),
            "destination_region_id": findtext(
                element=element, xpath="DestinationRegionId", namespace=self.namespace
            ),
            "destination_retention": self._to_int(
                findtext(element=element, xpath="DestinationRetention", namespace=self.namespace)
            ),
        }

    def _to_backup_jobs(self, element, target):
        jobs = findall(element=element, xpath="BackupJobs/BackupJob", namespace=self.namespace)
        return [self._to_backup_job(item, target) for item in jobs]

    def _to_backup_job(self, element, target):
        raw_status = findtext(element=element, xpath="Status", namespace=self.namespace)
        progress = self._to_progress(findtext(element=element, xpath="Progress", namespace=self.namespace))
        job_id = findtext(element=element, xpath="JobId", namespace=self.namespace)
        extra = {
            "operation": "backup",
            "job_id": job_id,
            "vault_id": findtext(element=element, xpath="VaultId", namespace=self.namespace)
            or target.extra.get("vault_id"),
            "source_type": findtext(element=element, xpath="SourceType", namespace=self.namespace)
            or target.extra["source_type"],
            "raw_status": raw_status,
            "error_message": findtext(element=element, xpath="ErrorMessage", namespace=self.namespace),
            "created_time": self._to_int(
                findtext(element=element, xpath="CreatedTime", namespace=self.namespace)
            ),
            "updated_time": self._to_int(
                findtext(element=element, xpath="UpdatedTime", namespace=self.namespace)
            ),
            "start_time": self._to_int(
                findtext(element=element, xpath="StartTime", namespace=self.namespace)
            ),
            "complete_time": self._to_int(
                findtext(element=element, xpath="CompleteTime", namespace=self.namespace)
            ),
        }
        snapshot_id = findtext(element=element, xpath="SnapshotId", namespace=self.namespace)
        if snapshot_id:
            extra["snapshot_id"] = snapshot_id

        return BackupTargetJob(
            id=job_id,
            status=self._map_job_status(raw_status),
            progress=progress,
            target=target,
            driver=self,
            extra=extra,
        )

    def _to_restore_jobs(self, element, target):
        jobs = findall(element=element, xpath="RestoreJobs/RestoreJob", namespace=self.namespace)
        return [self._to_restore_job(item, target) for item in jobs]

    def _to_restore_job(self, element, target):
        raw_status = findtext(element=element, xpath="Status", namespace=self.namespace)
        restore_id = findtext(element=element, xpath="RestoreId", namespace=self.namespace)
        return BackupTargetJob(
            id=restore_id,
            status=self._map_job_status(raw_status),
            progress=self._to_progress(findtext(element=element, xpath="Progress", namespace=self.namespace)),
            target=target,
            driver=self,
            extra={
                "operation": "restore",
                "restore_id": restore_id,
                "vault_id": findtext(element=element, xpath="VaultId", namespace=self.namespace)
                or target.extra.get("vault_id"),
                "source_type": findtext(element=element, xpath="SourceType", namespace=self.namespace)
                or target.extra["source_type"],
                "raw_status": raw_status,
                "error_message": findtext(
                    element=element, xpath="ErrorMessage", namespace=self.namespace
                ),
                "snapshot_id": findtext(element=element, xpath="SnapshotId", namespace=self.namespace),
            },
        )

    def _to_recovery_points(self, element, target):
        snapshots = findall(element=element, xpath="Snapshots/Snapshot", namespace=self.namespace)
        return [self._to_recovery_point(item, target) for item in snapshots]

    def _to_recovery_point(self, element, target):
        completed_time = findtext(element=element, xpath="CompleteTime", namespace=self.namespace)
        created_time = findtext(element=element, xpath="CreatedTime", namespace=self.namespace)
        point_time = self._to_datetime(completed_time or created_time)
        extra = {
            "snapshot_id": findtext(element=element, xpath="SnapshotId", namespace=self.namespace),
            "snapshot_hash": findtext(element=element, xpath="SnapshotHash", namespace=self.namespace),
            "vault_id": findtext(element=element, xpath="VaultId", namespace=self.namespace)
            or target.extra.get("vault_id"),
            "source_type": findtext(element=element, xpath="SourceType", namespace=self.namespace)
            or target.extra["source_type"],
            "instance_id": findtext(element=element, xpath="InstanceId", namespace=self.namespace)
            or target.extra.get("instance_id"),
            "client_id": findtext(element=element, xpath="ClientId", namespace=self.namespace)
            or target.extra.get("client_id"),
            "status": findtext(element=element, xpath="Status", namespace=self.namespace),
            "retention": self._to_int(
                findtext(element=element, xpath="Retention", namespace=self.namespace)
            ),
            "complete_time": self._to_int(completed_time),
            "created_time": self._to_int(created_time),
        }
        return BackupTargetRecoveryPoint(
            id=extra["snapshot_id"],
            date=point_time,
            target=target,
            driver=self,
            extra=extra,
        )

    def _get_source_type(self, type, extra):
        source_type = extra.get("source_type")
        if source_type:
            return source_type
        if type not in self.TARGET_TYPE_TO_SOURCE_TYPE:
            raise ValueError("Unsupported target type: %s" % (type))
        return self.TARGET_TYPE_TO_SOURCE_TYPE[type]

    def _get_target_address(self, source_type, extra):
        if source_type == "ECS_FILE":
            return extra.get("instance_id")
        if source_type == "NAS":
            return extra.get("file_system_id")
        if source_type == "OSS":
            bucket = extra.get("bucket")
            prefix = extra.get("prefix")
            if bucket and prefix:
                return "%s/%s" % (bucket, prefix)
            return bucket
        raise ValueError("Unsupported source_type: %s" % (source_type))

    def _get_required_extra(self, extra, key):
        value = extra.get(key)
        if value is None:
            raise ValueError("extra must include %s" % (key))
        return value

    def _normalize_rule(self, rule):
        normalized = {}
        mapping = {
            "rule_name": "RuleName",
            "schedule": "Schedule",
            "retention": "Retention",
            "disabled": "Disabled",
            "backup_type": "BackupType",
            "do_copy": "DoCopy",
            "destination_region_id": "DestinationRegionId",
            "destination_retention": "DestinationRetention",
        }
        for key, value in rule.items():
            mapped_key = mapping.get(key, key)
            if mapped_key == "rule_id" or mapped_key == "RuleId":
                continue
            normalized[mapped_key] = value
        return normalized

    def _add_common_request_params(self, params, extra):
        params["Edition"] = self._get_edition(extra)

    def _get_edition(self, extra):
        return extra.get("edition") or self.edition

    def _serialize_value(self, value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, datetime.datetime):
            return str(self._datetime_to_timestamp(value))
        return str(value)

    def _json_value(self, value):
        if isinstance(value, str):
            return value
        return json.dumps(value, separators=(",", ":"))

    def _safe_json(self, value):
        if value in (None, ""):
            return None
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value

    def _to_int(self, value):
        if value in (None, ""):
            return None
        return int(value)

    def _to_bool(self, value):
        if value in (None, ""):
            return None
        return str(value).lower() == "true"

    def _to_datetime(self, value):
        if value in (None, ""):
            return None
        return datetime.datetime.utcfromtimestamp(int(value))

    def _to_progress(self, value):
        if value in (None, ""):
            return 0
        progress = int(value)
        if progress > 100:
            progress = int(progress / 100)
        return max(0, min(progress, 100))

    def _map_job_status(self, status):
        if not status:
            return BackupTargetJobStatusType.PENDING
        return self.JOB_STATUS_MAP.get(status, BackupTargetJobStatusType.PENDING)

    def _datetime_to_timestamp(self, value):
        if value.tzinfo is not None:
            return calendar.timegm(value.utctimetuple())
        return int((value - datetime.datetime(1970, 1, 1)).total_seconds())
