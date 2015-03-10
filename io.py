from concurrent.futures import ThreadPoolExecutor
from tornado.process import cpu_count
from tornado import gen, web

def make_async(action):
    return web.asynchronous(action)

def make_coroutine(action):
    return gen.coroutine(action)

def make_non_blocking(action):
    action = make_async(action)
    action = make_coroutine(action)
    return action

class AsyncTaskPool:

    def __init__(self):
        self._pool = ThreadPoolExecutor(cpu_count() * 5)

    @make_coroutine
    def async_task(self, blocking_func, *args, **kwargs):
        return (yield self._pool.submit(blocking_func, *args, **kwargs))