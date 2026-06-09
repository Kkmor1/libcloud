#!/usr/bin/env python
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

"""
Alibaba Cloud Backup Driver - Complete Usage Example

This example demonstrates how to use the AlibabaBackupDriver to manage
backup targets, create backup jobs, list recovery points, and perform
recovery operations on Alibaba Cloud (Aliyun) ECS resources.

Prerequisites:
    - libcloud installed
    - Alibaba Cloud AccessKey ID and AccessKey Secret
    - Set environment variables: ALIBABA_ACCESS_KEY_ID and ALIBABA_ACCESS_KEY_SECRET
"""

import os

from libcloud.backup.types import Provider
from libcloud.backup.providers import get_driver

ACCESS_KEY_ID = os.environ.get("ALIBABA_ACCESS_KEY_ID", "your_access_key_id")
ACCESS_KEY_SECRET = os.environ.get("ALIBABA_ACCESS_KEY_SECRET", "your_access_key_secret")
REGION = "cn-hangzhou"


def main():
    cls = get_driver(Provider.ALIBABA)
    driver = cls(key=ACCESS_KEY_ID, secret=ACCESS_KEY_SECRET, region=REGION)

    print("=" * 60)
    print("Alibaba Cloud Backup Driver Example")
    print("=" * 60)

    # 1. List supported target types
    print("\n1. Supported target types:")
    for t in driver.get_supported_target_types():
        print("   - {}".format(t))

    # 2. List existing backup targets (ECS instances)
    print("\n2. Listing backup targets (ECS instances):")
    targets = driver.list_targets()
    for target in targets:
        print("   - ID: {}, Name: {}, Status: {}".format(
            target.id, target.name, target.extra.get("status", "N/A")
        ))

    # 3. Create a backup target for a specific ECS instance
    print("\n3. Creating a backup target for ECS instance:")
    instance_id = "i-instance001"
    target = driver.create_target(
        name="my-web-server",
        address=instance_id,
        type="Virtual",
        extra={"instance-id": instance_id, "region": REGION},
    )
    print("   - Created target: ID={}, Name={}".format(target.id, target.name))

    # 4. Create a backup target for a specific disk (Volume type)
    print("\n4. Creating a backup target for a disk volume:")
    disk_id = "d-disk001"
    volume_target = driver.create_target(
        name="my-data-disk",
        address=disk_id,
        type="Volume",
        extra={"volume-id": disk_id, "region": REGION},
    )
    print("   - Created volume target: ID={}, Name={}".format(volume_target.id, volume_target.name))

    # 5. Create a backup job (snapshot)
    print("\n5. Creating a backup job:")
    job = driver.create_target_job(
        target,
        extra={"snapshot_name": "daily-backup-20250115"},
    )
    print("   - Job created: ID={}, Status={}".format(job.id, job.status))

    # 6. List running backup jobs
    print("\n6. Listing running backup jobs:")
    jobs = driver.list_target_jobs(target)
    for j in jobs:
        print("   - Job ID: {}, Status: {}, Progress: {}%".format(j.id, j.status, j.progress))

    # 7. List recovery points (snapshots)
    print("\n7. Listing recovery points:")
    recovery_points = driver.list_recovery_points(target)
    for rp in recovery_points:
        print("   - Recovery Point ID: {}, Date: {}, Name: {}".format(
            rp.id, rp.date, rp.extra.get("snapshot-name", "N/A")
        ))

    # 8. Recover from a recovery point
    if recovery_points:
        print("\n8. Recovering from recovery point:")
        latest_rp = recovery_points[0]
        recovery_job = driver.recover_target(target, latest_rp)
        print("   - Recovery job: ID={}, Status={}".format(recovery_job.id, recovery_job.status))
        print("   - New disk ID: {}".format(recovery_job.extra.get("disk-id", "N/A")))

    # 9. Recover to a different target (out-of-place recovery)
    if recovery_points:
        print("\n9. Out-of-place recovery:")
        recovery_target = driver.create_target(
            name="recovery-destination",
            address="i-instance002",
            type="Virtual",
        )
        oop_job = driver.recover_target_out_of_place(
            target, recovery_points[0], recovery_target
        )
        print("   - OOP Recovery job: ID={}, Target={}".format(oop_job.id, oop_job.target.id))

    # 10. Cancel a running backup job
    print("\n10. Canceling a backup job:")
    result = driver.cancel_target_job(job)
    print("   - Cancel result: {}".format(result))

    # 11. Delete a recovery point (extended method)
    if recovery_points:
        print("\n11. Deleting a recovery point:")
        result = driver.ex_delete_recovery_point(recovery_points[0])
        print("   - Delete result: {}".format(result))

    # 12. Get a specific recovery point
    print("\n12. Getting a specific recovery point:")
    if recovery_points:
        rp = driver.ex_get_recovery_point(recovery_points[0].id, target)
        if rp:
            print("   - Found: ID={}, Name={}".format(rp.id, rp.extra.get("snapshot-name", "N/A")))
        else:
            print("   - Recovery point not found")

    # 13. Update a target
    print("\n13. Updating a target:")
    updated_target = driver.update_target(
        target, name="updated-server", extra={"description": "Updated description"}
    )
    print("   - Updated: Name={}, Extra={}".format(updated_target.name, updated_target.extra))

    # 14. Delete a target
    print("\n14. Deleting a target:")
    result = driver.delete_target(target)
    print("   - Delete result: {}".format(result))

    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
