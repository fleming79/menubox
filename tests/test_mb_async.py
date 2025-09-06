import asyncio

import pytest
from async_kernel.caller import FutureCancelledError

from menubox import mb_async as mba
from menubox.hasparent import HasParent
from menubox.trait_factory import TF


class MBRunAsync(HasParent):
    my_set = TF.Set()
    my_task = TF.Future()


async def async_function(result, delay=0.0):
    await asyncio.sleep(delay)
    return result


class TestRunAsync:
    async def test_run_async_basic(self):
        result = await mba.run_async({}, async_function, 1)
        assert result == 1

    async def test_run_async_name(self):
        fut = mba.run_async({"handle": "test_task"}, async_function, 2)
        assert mba.get_pending_future(handle="test_task") is fut
        await fut

    async def test_run_async_restart(self):
        task1 = mba.run_async({"handle": "test_task_restart"}, async_function, 3, 0.1)
        task2 = mba.run_async({"handle": "test_task_restart"}, async_function, 4)
        assert task1.cancelled()
        assert task1 is not task2
        assert await task2 == 4
        assert task1.done()
        with pytest.raises(FutureCancelledError):
            task1.exception()

    async def test_run_async_no_restart(self):
        task1 = mba.run_async({"handle": "test_task_restart", "restart": False}, async_function, 5, 0.1)
        task2 = mba.run_async({"handle": "test_task_restart", "restart": False}, async_function, 6)
        assert task1 is task2
        assert (await task1) == 5

    async def test_run_async_timeout(self):
        with pytest.raises(asyncio.TimeoutError):
            await mba.run_async({}, async_function, 7, 100).wait(timeout=0.1)

    async def test_run_async_handle_set(self):
        obj = MBRunAsync()
        task = mba.run_async({"obj": obj, "handle": "my_set"}, async_function, result=8)
        assert task in obj.my_set
        assert await task == 8
        assert task not in obj.my_set

    async def test_run_async_handle_task(self):
        obj = MBRunAsync()
        task = mba.run_async({"obj": obj, "handle": "my_task"}, async_function, 9)
        assert obj.my_task is task
        assert await task == 9
        assert obj.my_task is None

    async def test_run_async_tasktype(self):
        task = mba.run_async({"tasktype": mba.TaskType.update}, async_function, 10)
        assert task in mba.background_tasks
        assert mba.background_tasks[task] == mba.TaskType.update
        await task

    async def test_run_async_exception(self):
        async def raising_function():
            msg = "Test Exception"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Test Exception"):
            await mba.run_async({}, raising_function)


class MBRunAsyncSingular(HasParent):
    my_task_trait = TF.Future()

    @mba.singular_task(handle="my_task_trait")
    async def async_singular_function(self, *args, **kwgs):
        await asyncio.sleep(0.01)
        return args, kwgs

    @mba.singular_task(handle="my_task_trait", restart=False)
    async def async_singular_function_restart_false(self, *args, **kwgs):
        await asyncio.sleep(0.01)
        return args, kwgs

    @mba.singular_task()
    def singular_function(self, num):
        return num


class TestSingularTaskDecorator:
    async def test_singular_task_decorator(self):
        obj = MBRunAsyncSingular()
        task1 = obj.async_singular_function(1)
        task2 = obj.async_singular_function(2)
        assert task1 is not task2
        assert not task1.done()
        assert not task2.done()
        assert (await task2) == ((2,), {}), "Task restarts by default"
        assert task1.cancelled()
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

        result = await mba.to_thread(sync_function, 1, y=3)
        assert result == 4

    async def test_to_thread_exception(self):
        def sync_raising_function():
            msg = "Sync Test Exception"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Sync Test Exception"):
            await mba.to_thread(sync_raising_function)
