#!/usr/bin/env python
import logging
import asyncio
from libcloud.utils.retry import retry_on_exception

# 配置日志级别为 DEBUG
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 用于跟踪执行次数
call_count = 0


def test_sync_function(max_retries_val):
    global call_count
    call_count = 0

    @retry_on_exception(max_retries=max_retries_val, retry_exceptions=(Exception,), retry_delay=0.001)
    def failing_function():
        global call_count
        call_count += 1
        logger.debug(f"failing_function 被调用，当前调用次数: {call_count}")
        raise Exception("测试异常")

    try:
        failing_function()
    except Exception as e:
        logger.debug(f"最终异常: {e}")

    return call_count


async def test_async_function(max_retries_val):
    global call_count
    call_count = 0

    @retry_on_exception(max_retries=max_retries_val, retry_exceptions=(Exception,), retry_delay=0.001)
    async def async_failing_function():
        global call_count
        call_count += 1
        logger.debug(f"async_failing_function 被调用，当前调用次数: {call_count}")
        raise Exception("测试异步异常")

    try:
        await async_failing_function()
    except Exception as e:
        logger.debug(f"最终异常: {e}")

    return call_count


def run_tests():
    print("\n=== 测试同步函数 ===")
    for max_retries in [0, 1, 3]:
        expected_calls = max_retries + 1
        actual_calls = test_sync_function(max_retries)
        print(f"max_retries={max_retries}: 预期 {expected_calls} 次调用，实际 {actual_calls} 次调用")
        assert actual_calls == expected_calls, f"测试失败！期望 {expected_calls}，得到 {actual_calls}"

    print("\n=== 测试异步函数 ===")
    for max_retries in [0, 1, 3]:
        expected_calls = max_retries + 1
        actual_calls = asyncio.run(test_async_function(max_retries))
        print(f"max_retries={max_retries}: 预期 {expected_calls} 次调用，实际 {actual_calls} 次调用")
        assert actual_calls == expected_calls, f"测试失败！期望 {expected_calls}，得到 {actual_calls}"

    print("\n🎉 所有测试通过！")


if __name__ == "__main__":
    run_tests()
