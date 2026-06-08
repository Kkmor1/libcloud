import os

with open('/app/libcloud/result.txt', 'w', encoding='utf-8') as out:
    for root, dirs, files in os.walk('/app/libcloud/libcloud/'):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    if 'retry_on_exception' in content or 'max_retries' in content:
                        out.write(f"Found in {path}\n")
