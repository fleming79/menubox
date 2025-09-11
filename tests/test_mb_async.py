from typing import Never

import anyio
import pytest
from async_kernel.caller import FutureCancelledError

import menubox as mb
from menubox.hasparent import HasParent
from menubox.mb_async import run_async
from menubox.trait_factory import TF


class MBRunAsync(HasParent):
    my_set = TF.Set()
    my_task = TF.Future()


async def async_function(result, delay=0.0):
    await anyio.sleep(delay)
    return result


class TestRunAsync:
    async def test_run_async_basic(self):
        result = await run_async({}, async_function, 1)
        assert result == 1

    async def test_run_async_singular(self):
        fut = run_async({"key": "my key"}, async_function, 2)
        assert mb.mb_async.singular_tasks.get("my key") is fut
        await fut
        assert mb.mb_async.singular_tasks.get("my key") is None

    async def test_run_async_restart(self):
        fut1 = run_async({"key": async_function}, async_function, 3, 0.1)
        fut2 = run_async({"key": async_function}, async_function, 4)
        assert fut1.cancelled()
        assert fut1 is not fut2
        assert await fut2 == 4
        assert fut1.done()
        with pytest.raises(FutureCancelledError):
            fut1.exception()

    async def test_run_async_no_restart(self):
        task1 = run_async({"key": async_function, "restart": False}, async_function, 5, 0.1)
        task2 = run_async({"key": async_function, "restart": False}, async_function, 6)
        assert task1 is task2
        assert (await task1) == 5

    async def test_run_async_timeout(self):
        with pytest.raises(TimeoutError):
            await run_async({}, async_function, 7, 100).wait(timeout=0.1)

    async def test_run_async_handle_set(self):
        obj = MBRunAsync()
        fut = run_async({"obj": obj, "handle": "my_set"}, async_function, result=8)
        assert fut in obj.my_set
        assert await fut == 8
        assert fut not in obj.my_set

    async def test_run_async_handle_task(self):
        obj = MBRunAsync()
        fut = run_async({"obj": obj, "handle": "my_task"}, async_function, 9)
        assert obj.my_task is fut
        assert await fut == 9
        assert obj.my_task is None

    async def test_run_async_tasktype(self):
        fut = run_async({"tasktype": mb.mb_async.TaskType.update}, async_function, 10)
        assert fut.metadata.get("tasktype") == mb.mb_async.TaskType.update
        await fut

    async def test_run_async_exception(self):
        async def raising_function() -> Never:
            msg = "Test Exception"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Test Exception"):
            await run_async({}, raising_function)


class MBRunAsyncSingular(HasParent):
    my_task_trait = TF.Future()

    @mb.mb_async.singular_task(handle="my_task_trait")
    async def async_singular_function(self, *args, **kwgs):
        await anyio.sleep(0.01)
        return args, kwgs

    @mb.mb_async.singular_task(handle="my_task_trait", restart=False)
    async def async_singular_function_restart_false(self, *args, **kwgs):
        await anyio.sleep(0.01)
        return args, kwgs

    @mb.mb_async.singular_task()
    def singular_function(self, num):
        return num


class TestSingularTaskDecorator:
    async def test_singular_task_decorator(self):
        obj = MBRunAsyncSingular()
        fut1 = obj.async_singular_function(1)
        fut2 = obj.async_singular_function(2)
        assert fut1 is not fut2
        assert not fut1.done()
        assert not fut2.done()
        assert (await fut2) == ((2,), {}), "Task restarts by default"
        assert fut1.cancelled()
        task4 = obj.async_singular_function(a=3)
        assert (await task4) == ((), {"a": 3}), "Pass keyword argument"
        obj.close()
        await obj.wait_tasks()

    async def test_singular_task_decorator_restart_false_default(self):
        obj = MBRunAsyncSingular()
        fut1 = obj.async_singular_function_restart_false(1)
        fut2 = obj.async_singular_function_restart_false(2)
        assert fut1 is fut2
        assert (await fut1) == ((1,), {})
        obj.close()
        await obj.wait_tasks()

    async def test_singular_task_decorator_kwargs(self):
        obj = MBRunAsyncSingular()
        fut = obj.async_singular_function(1)
        assert obj.my_task_trait is fut
        await fut
        assert obj.my_task_trait is None
        obj.close()
        await obj.wait_tasks()


class TestToThread:
    async def test_to_thread_success(self):
        def sync_function(x, y=2):
            return x + y

        result = await mb.mb_async.to_thread(sync_function, 1, y=3)
        assert result == 4

    async def test_to_thread_exception(self):
        def sync_raising_function():
            msg = "Sync Test Exception"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Sync Test Exception"):
            await mb.mb_async.to_thread(sync_raising_function)
