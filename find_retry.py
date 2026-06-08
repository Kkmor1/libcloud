import os

with open('/app/libcloud/find.txt', 'w') as f:
    for root, dirs, files in os.walk('/app/'):
        if 'retry.py' in files:
            f.write(os.path.join(root, 'retry.py') + '\n')
