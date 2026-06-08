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
Example script to demonstrate the usage of the Aliyun Backup driver.
"""

from libcloud.backup.types import Provider, BackupTargetType
from libcloud.backup.providers import get_driver

# 1. 初始化驱动
AliyunBackupDriver = get_driver(Provider.ALIYUN)
access_key_id = "your_access_key_id"
access_key_secret = "your_access_key_secret"
region = "cn-hangzhou"  # 可替换为您需要的区域
driver = AliyunBackupDriver(access_key_id, access_key_secret, region=region)

print(f"使用区域: {region}")

# 2. 列出所有备份目标 (Vaults)
print("\n--- 列出所有备份目标 ---")
targets = driver.list_targets()
for target in targets:
    print(f"  目标: {target.name} ({target.id})")
    print(f"  类型: {target.type}")

# 3. 创建一个新的备份目标 (Vault)
print("\n--- 创建新的备份目标 ---")
new_target = driver.create_target(
    name="test-vault",
    address="",
    type=BackupTargetType.VOLUME,
    extra={"description": "Test backup vault"}
)
print(f"  创建的目标: {new_target.name} ({new_target.id})")

# 4. 创建一个备份任务
print("\n--- 创建备份任务 ---")
backup_job = driver.create_target_job(
    target=new_target,
    extra={"source": "your-source-id", "backup_type": "FULL"}
)
print(f"  任务ID: {backup_job.id}")
print(f"  状态: {backup_job.status}")
print(f"  进度: {backup_job.progress}%")

# 5. 列出该目标的所有备份任务
print("\n--- 列出备份目标的任务 ---")
jobs = driver.list_target_jobs(target=new_target)
for job in jobs:
    print(f"  任务: {job.id}")
    print(f"  状态: {job.status}")

# 6. 列出该目标的所有恢复点
print("\n--- 列出恢复点 ---")
recovery_points = driver.list_recovery_points(target=new_target)
for rp in recovery_points:
    print(f"  恢复点: {rp.id}")
    print(f"  创建时间: {rp.date}")

# 7. 恢复数据
if recovery_points:
    print("\n--- 从最近的恢复点恢复 ---")
    recovery_job = driver.recover_target(
        target=new_target,
        recovery_point=recovery_points[0],
        path="/"
    )
    print(f"  恢复任务: {recovery_job.id}")

# 8. 更新备份目标
print("\n--- 更新备份目标 ---")
updated_target = driver.update_target(
    target=new_target,
    name="test-vault-updated",
    address=new_target.address,
    extra={"description": "Updated test vault"}
)
print(f"  更新后的目标: {updated_target.name}")

# 9. 删除备份目标 (注意：这是一个演示，实际操作时请小心)
# 取消下一行的注释以测试删除功能
# driver.delete_target(target=updated_target)
# print("\n--- 备份目标已删除 ---")

print("\n示例完成！")
