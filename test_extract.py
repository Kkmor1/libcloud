import json
import time

def extract_driver_pricing(content, driver_type, driver_name):
    # Find the driver_type start
    type_idx = content.find(f'"{driver_type}"')
    if type_idx == -1:
        return None
    
    # Find the driver_name start after type_idx
    driver_idx = content.find(f'"{driver_name}"', type_idx)
    if driver_idx == -1:
        return None
    
    # Find the starting brace
    brace_idx = content.find('{', driver_idx)
    if brace_idx == -1:
        return None
    
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(content, brace_idx)
    return obj

if __name__ == '__main__':
    with open('/app/libcloud/libcloud/data/pricing.json', 'r') as f:
        content = f.read()
    
    start = time.time()
    pricing = extract_driver_pricing(content, "compute", "azure_linux")
    end = time.time()
    print(f"Extracted azure_linux in {end - start:.4f}s. Size: {len(pricing)}")
    
    start = time.time()
    full_pricing = json.loads(content)
    end = time.time()
    print(f"Full load in {end - start:.4f}s.")
