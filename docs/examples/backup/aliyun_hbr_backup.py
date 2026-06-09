import os
from pprint import pprint

from libcloud.backup.types import Provider
from libcloud.backup.providers import get_driver

Driver = get_driver(Provider.ALIYUN_HBR)

driver = Driver(
    key=os.environ["ALIBABA_CLOUD_ACCESS_KEY_ID"],
    secret=os.environ["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
    edition=os.environ.get("ALIBABA_CLOUD_BACKUP_EDITION", "STANDARD"),
)

target = driver.create_target(
    name="example-ecs-file-backup",
    address=os.environ["ALIBABA_CLOUD_INSTANCE_ID"],
    extra={
        "vault_id": os.environ["ALIBABA_CLOUD_BACKUP_VAULT_ID"],
        "schedule": os.environ.get("ALIBABA_CLOUD_BACKUP_SCHEDULE", "I|1700000000|P1D"),
        "retention": int(os.environ.get("ALIBABA_CLOUD_BACKUP_RETENTION", "7")),
        "include": [os.environ.get("ALIBABA_CLOUD_BACKUP_INCLUDE", "/data")],
        "exclude": ["/proc", "/sys"],
    },
)

backup_job = driver.create_target_job(target)
recovery_points = driver.list_recovery_points(target)

if recovery_points:
    restore_job = driver.recover_target(target, recovery_points[0], path="/restore")
    print(restore_job)

pprint(target)
pprint(backup_job)
pprint(recovery_points)
