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
Alibaba Cloud Hybrid Backup Recovery (HBR) Driver - Complete Usage Example

This example demonstrates the complete workflow of using the HBR backup
driver to manage backup plans, jobs, recovery points, and restores.

Prerequisites:
    - Alibaba Cloud Access Key ID and Access Key Secret
    - An ECS instance running in the target region
    - HBR service activated in the target region

Usage:
    export ALIYUN_ACCESS_KEY_ID="your-access-key-id"
    export ALIYUN_ACCESS_KEY_SECRET="your-access-key-secret"

    python examples/aliyun_hbr_example.py
"""

import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from libcloud.backup.types import Provider, BackupTargetType
from libcloud.backup.providers import get_driver


def print_section(title):
    print("\n" + "=" * 60)
    print("  %s" % title)
    print("=" * 60)


def main():
    access_key_id = os.environ.get("ALIYUN_ACCESS_KEY_ID")
    access_key_secret = os.environ.get("ALIYUN_ACCESS_KEY_SECRET")

    if not access_key_id or not access_key_secret:
        print("ERROR: Please set ALIYUN_ACCESS_KEY_ID and ALIYUN_ACCESS_KEY_SECRET")
        print("       environment variables before running this example.")
        sys.exit(1)

    region = os.environ.get("ALIYUN_REGION", "cn-hangzhou")

    DriverClass = get_driver(Provider.ALIYUN_HBR)
    driver = DriverClass(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        region=region,
    )

    print_section("Driver Information")
    print("  Name:    %s" % driver.name)
    print("  Website: %s" % driver.website)
    print("  Region:  %s" % driver.region)
    print(
        "  Supported Types: %s"
        % ", ".join(t.value for t in driver.get_supported_target_types())
    )

    # ── 1. List existing backup plans ─────────────────────────────────────
    print_section("1. Listing Existing Backup Plans")
    try:
        targets = driver.list_targets()
        if targets:
            for t in targets:
                print("  - [%s] %s (retention: %s days)" % (t.id, t.name, t.extra.get("retention")))
        else:
            print("  No backup plans found.")
    except Exception as e:
        print("  Error listing targets: %s" % e)
        targets = []

    # ── 2. Create a new backup plan ───────────────────────────────────────
    print_section("2. Creating a New Backup Plan")

    plan_name = "libcloud-example-backup-plan"
    extra = {
        "Schedule": "I|1602673158|P1D",
        "Retention": 7,
        "BackupType": "COMPLETE",
    }

    try:
        new_target = driver.create_target(
            name=plan_name,
            address="",
            type=BackupTargetType.VIRTUAL,
            extra=extra,
        )
        print("  Created backup plan:")
        print("    ID:         %s" % new_target.id)
        print("    Name:       %s" % new_target.name)
        print("    Schedule:   %s" % new_target.extra.get("schedule"))
        print("    Retention:  %s days" % new_target.extra.get("retention"))
        print("    Type:       %s" % new_target.extra.get("backup_type"))
    except Exception as e:
        print("  Error creating backup plan: %s" % e)
        new_target = None

    if new_target is None:
        print("\n  Using first existing target for subsequent operations.")
        if targets:
            new_target = targets[0]
        else:
            print("  No targets available. Exiting.")
            sys.exit(1)

    # ── 3. Update the backup plan ─────────────────────────────────────────
    print_section("3. Updating the Backup Plan")
    try:
        updated_extra = {
            "Schedule": "I|1602673158|PT12H",
            "Retention": 14,
        }
        updated = driver.update_target(
            target=new_target,
            name="libcloud-example-backup-plan-updated",
            extra=updated_extra,
        )
        print("  Updated backup plan:")
        print("    Name:      %s" % updated.name)
        print("    Schedule:  %s" % updated.extra.get("schedule"))
        print("    Retention: %s days" % updated.extra.get("retention"))
    except Exception as e:
        print("  Error updating backup plan: %s" % e)

    # ── 4. Create (execute) a backup job ──────────────────────────────────
    print_section("4. Executing a Backup Job")
    try:
        job = driver.create_target_job(target=new_target)
        print("  Backup job created:")
        print("    ID:       %s" % job.id)
        print("    Status:   %s" % job.status.value)
        print("    Progress: %s%%" % job.progress)
    except Exception as e:
        print("  Error creating backup job: %s" % e)

    # ── 5. List backup jobs ───────────────────────────────────────────────
    print_section("5. Listing Backup Jobs")
    try:
        jobs = driver.list_target_jobs(target=new_target)
        for j in jobs:
            print(
                "  - [%s] status=%s progress=%s%%"
                % (j.id, j.status.value, j.progress)
            )
    except Exception as e:
        print("  Error listing backup jobs: %s" % e)

    # ── 6. Get a specific job ─────────────────────────────────────────────
    print_section("6. Getting a Specific Backup Job")
    try:
        jobs = driver.list_target_jobs(target=new_target)
        if jobs:
            specific_job = driver.get_target_job(target=new_target, id=jobs[0].id)
            print("  Job details:")
            print("    ID:       %s" % specific_job.id)
            print("    Status:   %s" % specific_job.status.value)
            print("    Progress: %s%%" % specific_job.progress)
    except Exception as e:
        print("  Error getting backup job: %s" % e)

    # ── 7. Cancel a running backup job ────────────────────────────────────
    print_section("7. Cancelling a Backup Job")
    try:
        jobs = driver.list_target_jobs(target=new_target)
        running_jobs = [j for j in jobs if j.status.value == "Running"]
        if running_jobs:
            result = driver.cancel_target_job(job=running_jobs[0])
            print("  Cancel result: %s" % result)
        else:
            print("  No running jobs to cancel.")
    except Exception as e:
        print("  Error cancelling backup job: %s" % e)

    # ── 8. List recovery points ───────────────────────────────────────────
    print_section("8. Listing Recovery Points (Snapshots)")
    try:
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
        recovery_points = driver.list_recovery_points(
            target=new_target,
            start_date=start_date,
            end_date=end_date,
        )
        if recovery_points:
            for rp in recovery_points:
                print(
                    "  - [%s] date=%s status=%s"
                    % (rp.id, rp.date, rp.extra.get("status"))
                )
        else:
            print("  No recovery points found in the last 30 days.")
    except Exception as e:
        print("  Error listing recovery points: %s" % e)

    # ── 9. Recover from a recovery point ──────────────────────────────────
    print_section("9. Recovering from a Recovery Point")
    try:
        recovery_points = driver.list_recovery_points(target=new_target)
        if recovery_points:
            latest_rp = recovery_points[0]
            restore_job = driver.recover_target(
                target=new_target,
                recovery_point=latest_rp,
                path="/data",
            )
            print("  Restore job created:")
            print("    ID:     %s" % restore_job.id)
            print("    Status: %s" % restore_job.status.value)
        else:
            print("  No recovery points available for restore.")
    except Exception as e:
        print("  Error recovering: %s" % e)

    # ── 10. Recover out-of-place ──────────────────────────────────────────
    print_section("10. Recovering Out-of-Place")
    try:
        targets = driver.list_targets()
        recovery_points = driver.list_recovery_points(target=new_target)
        if len(targets) > 1 and recovery_points:
            recovery_target = targets[1] if targets[1].id != new_target.id else targets[0]
            latest_rp = recovery_points[0]
            restore_job = driver.recover_target_out_of_place(
                target=new_target,
                recovery_point=latest_rp,
                recovery_target=recovery_target,
                path="/data",
            )
            print("  Out-of-place restore job created:")
            print("    ID:              %s" % restore_job.id)
            print("    Source Target:   %s" % new_target.id)
            print("    Recovery Target: %s" % recovery_target.id)
        else:
            print("  Need at least 2 targets for out-of-place recovery demo.")
    except Exception as e:
        print("  Error recovering out-of-place: %s" % e)

    # ── 11. List restore jobs ─────────────────────────────────────────────
    print_section("11. Listing Restore Jobs")
    try:
        restore_jobs = driver.list_restore_jobs(target=new_target)
        for rj in restore_jobs:
            print(
                "  - [%s] status=%s progress=%s%%"
                % (rj.id, rj.status.value, rj.progress)
            )
    except Exception as e:
        print("  Error listing restore jobs: %s" % e)

    # ── 12. Delete a backup plan ──────────────────────────────────────────
    print_section("12. Deleting a Backup Plan")
    try:
        # Finds and deletes the example plan if it was created
        all_targets = driver.list_targets()
        example_targets = [t for t in all_targets if "libcloud-example" in t.name]
        if example_targets:
            for t in example_targets:
                driver.delete_target(target=t)
                print("  Deleted: [%s] %s" % (t.id, t.name))
        else:
            print("  No example backup plans to delete.")
    except Exception as e:
        print("  Error deleting backup plan: %s" % e)

    print_section("Done")
    print("  The Alibaba Cloud HBR driver usage example completed successfully.\n")


if __name__ == "__main__":
    main()