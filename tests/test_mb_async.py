from typing import Never

import anyio
import pytest
from async_kernel.pending import PendingCancelled

import menubox as mb
from menubox.hasparent import HasParent
from menubox.mb_async import run_async
from menubox.trait_factory import TF


class MBRunAsync(HasParent):
    my_set = TF.Set()
    my_pen = TF.Pending()


async def async_function(result, delay=0.0):
    await anyio.sleep(delay)
    return result


class TestRunAsync:
    async def test_run_async_basic(self):
        result = await run_async({}, async_function, 1)
        assert result == 1

    async def test_run_async_singular(self):
        pen = run_async({"key": "my key"}, async_function, 2)
        assert mb.mb_async.singular_pending.get("my key") is pen
        await pen
        assert mb.mb_async.singular_pending.get("my key") is None

    async def test_run_async_restart(self):
        pen_1 = run_async({"key": async_function}, async_function, 3, 0.1)
        pen_2 = run_async({"key": async_function}, async_function, 4)
        assert pen_1.cancelled()
        assert pen_1 is not pen_2
        assert await pen_2 == 4
        assert pen_1.done()
        with pytest.raises(PendingCancelled):
            pen_1.exception()

    async def test_run_async_no_restart(self):
        pen_1 = run_async({"key": async_function, "restart": False}, async_function, 5, 0.1)
        pen_2 = run_async({"key": async_function, "restart": False}, async_function, 6)
        assert pen_1 is pen_2
        assert (await pen_1) == 5

    async def test_run_async_timeout(self):
        with pytest.raises(TimeoutError):
            await run_async({}, async_function, 7, 100).wait(timeout=0.1)

    async def test_run_async_handle_set(self):
        obj = MBRunAsync()
        pen = run_async({"obj": obj, "handle": "my_set"}, async_function, result=8)
        assert pen in obj.my_set
        assert await pen == 8
        assert pen not in obj.my_set

    async def test_run_async_handle_pen(self):
        obj = MBRunAsync()
        pen = run_async({"obj": obj, "handle": "my_pen"}, async_function, 9)
        assert obj.my_pen is pen
        assert await pen == 9
        assert obj.my_pen is None

    async def test_run_async_pentype(self):
        pen = run_async({"pentype": mb.mb_async.PenType.update}, async_function, 10)
        assert pen.metadata.get("pentype") == mb.mb_async.PenType.update
        await pen

    async def test_run_async_exception(self):
        async def raising_function() -> Never:
            msg = "Test Exception"
            raise ValueError(msg)

        with pytest.raises(ValueError, match="Test Exception"):
            await run_async({}, raising_function)


class MBRunAsyncSingular(HasParent):
    my_pen_trait = TF.Pending()

    @mb.mb_async.singular(handle="my_pen_trait")
    async def async_singular_function(self, *args, **kwgs):
        await anyio.sleep(0.01)
        return args, kwgs

    @mb.mb_async.singular(handle="my_pen_trait", restart=False)
    async def async_singular_function_restart_false(self, *args, **kwgs):
        await anyio.sleep(0.01)
        return args, kwgs

    @mb.mb_async.singular()
    def singular_function(self, num):
        return num


class TestSingularTaskDecorator:
    async def test_singular_decorator(self):
        obj = MBRunAsyncSingular()
        pen_1 = obj.async_singular_function(1)
        pen_2 = obj.async_singular_function(2)
        assert pen_1 is not pen_2
        assert not pen_2.done()
        assert (await pen_2) == ((2,), {}), "Pending restarts by default"
        assert pen_1.cancelled()
        task4 = obj.async_singular_function(a=3)
        assert (await task4) == ((), {"a": 3}), "Pass keyword argument"
        obj.close()
        await obj.wait_pending()

    async def test_singular_decorator_restart_false_default(self):
        obj = MBRunAsyncSingular()
        pen_1 = obj.async_singular_function_restart_false(1)
        pen_2 = obj.async_singular_function_restart_false(2)
        assert pen_1 is pen_2
        assert (await pen_1) == ((1,), {})
        obj.close()
        await obj.wait_pending()

    async def test_singular_decorator_kwargs(self):
        obj = MBRunAsyncSingular()
        pen = obj.async_singular_function(1)
        assert obj.my_pen_trait is pen
        await pen
        assert obj.my_pen_trait is None
        obj.close()
        await obj.wait_pending()


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
