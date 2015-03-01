from concurrent.futures import ThreadPoolExecutor
from tornado import gen

class AsyncTaskPool:

    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=None)

    @gen.coroutine
    def async_task(self, blocking_func, args=None):
        return yield self._pool.submit(blocking_func, args)