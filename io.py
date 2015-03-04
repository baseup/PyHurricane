from concurrent.futures import ThreadPoolExecutor
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
        self._pool = ThreadPoolExecutor(max_workers=None)

    @gen.coroutine
    def async_task(self, blocking_func, args=None):
        return (yield self._pool.submit(blocking_func, args))