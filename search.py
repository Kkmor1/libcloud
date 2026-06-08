import os

for root, dirs, files in os.walk('/app/libcloud/libcloud/'):
    for f in files:
        if f.endswith('.py'):
            with open(os.path.join(root, f), 'r', encoding='utf-8') as file:
                content = file.read()
                if 'retry_on_exception' in content or 'max_retries' in content:
                    print(f"Found in {os.path.join(root, f)}")
