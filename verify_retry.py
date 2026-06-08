import asyncio
import logging
from libcloud.utils.retry import retry_on_exception

logging.basicConfig(level=logging.DEBUG)

def test_sync():
    print("\n--- Testing Sync ---")
    
    for max_r in [0, 1, 3]:
        print(f"\nTesting max_retries={max_r}")
        executed = 0
        
        @retry_on_exception(max_retries=max_r, retry_delay=0)
        def failing_func():
            nonlocal executed
            executed += 1
            raise ValueError("Intentional Failure")
            
        try:
            failing_func()
        except ValueError:
            pass
        print(f"max_retries={max_r} actually executed {executed} times.")

async def test_async():
    print("\n--- Testing Async ---")
    
    for max_r in [0, 1, 3]:
        print(f"\nTesting async max_retries={max_r}")
        executed = 0
        
        @retry_on_exception(max_retries=max_r, retry_delay=0)
        async def failing_func():
            nonlocal executed
            executed += 1
            raise ValueError("Intentional Failure")
            
        try:
            await failing_func()
        except ValueError:
            pass
        print(f"Async max_retries={max_r} actually executed {executed} times.")

if __name__ == "__main__":
    test_sync()
    asyncio.run(test_async())
