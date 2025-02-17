import asyncio

import pytest
import traitlets

from menubox import mb_async as mba
from menubox import trait_factory as tf
from menubox.hasparent import HasParent


class MBRunAsync(HasParent):
    my_set = traitlets.Set()
    my_task = tf.Task()


async def async_function(result, delay=0.0):
    await asyncio.sleep(delay)
    return result


class TestRunAsync:
    async def test_run_async_basic(self):
        result = await mba.run_async(async_function(1))
        assert result == 1

    async def test_run_async_name(self):
        task = mba.run_async(async_function(2), name="test_task")
        assert task.get_name() == "test_task"
        await task

    async def test_run_async_restart(self):
        task1 = mba.run_async(lambda: async_function(3, 0.1), name="test_task_restart")
        task2 = mba.run_async(lambda: async_function(4), name="test_task_restart")
        assert task1 is not task2
        assert await task2 == 4
        assert task1.done()
        with pytest.raises(asyncio.CancelledError):
            task1.exception()

    async def test_run_async_no_restart(self):
        task1 = mba.run_async(lambda: async_function(5, 0.1), name="test_task_no_restart", restart=False)
        task2 = mba.run_async(lambda: async_function(6), name="test_task_no_restart", restart=False)
        assert task1 is task2
        assert (await task1) is None

    async def test_run_async_timeout(self):
        with pytest.raises(asyncio.TimeoutError):
            await mba.run_async(async_function(7, 0.2), timeout=0.1)

    async def test_run_async_handle_set(self):
        obj = MBRunAsync()
        task = mba.run_async(async_function(8), obj=obj, handle="my_set")
        assert task in obj.my_set
        await task
        assert task not in obj.my_set

    async def test_run_async_handle_task(self):
        obj = MBRunAsync()
        task = mba.run_async(async_function(9), obj=obj, handle="my_task")
        assert obj.my_task is task
        await task
        assert obj.my_task is None

    async def test_run_async_tasktype(self):
        task = mba.run_async(async_function(10), tasktype=mba.TaskType.update)
        assert task in mba.background_tasks
        assert mba.background_tasks[task] == mba.TaskType.update
        await task

    async def test_run_async_partial(self):
        result = await mba.run_async(lambda: async_function(11))
        assert result == 11

    async def test_run_async_exception(self):
        async def raising_function():
            msg = "Test Exception"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Test Exception"):
            await mba.run_async(raising_function())

    async def test_run_async_no_name_no_restart(self):
        with pytest.raises(TypeError, match="A name must be provided if `restart=False`!"):
            mba.run_async(lambda: async_function(12), restart=False)


class MBRunAsyncSingular(HasParent):
    my_task_trait = tf.Task()

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
        task3 = obj.async_singular_function(1, restart=False)
        assert (await task3) is None
        task4 = obj.async_singular_function(a=3)
        assert (await task4) == ((), {"a": 3}), "Pass keyword argument"
        obj.close()
        await obj.wait_tasks()

    async def test_singular_task_decorator_restart_false_default(self):
        obj = MBRunAsyncSingular()
        task1 = obj.async_singular_function_restart_false(1)
        task2 = obj.async_singular_function_restart_false(2)
        assert task1 is task2
        assert (await task1) is None
        obj.close()
        await obj.wait_tasks()

    async def test_singular_task_decorator_kwargs(self):
        obj = MBRunAsyncSingular()
        task1 = obj.async_singular_function(1)
        assert obj.my_task_trait is task1
        await task1
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
