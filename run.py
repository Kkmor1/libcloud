import os
import subprocess
print(subprocess.check_output(["git", "status"]).decode("utf-8"))
