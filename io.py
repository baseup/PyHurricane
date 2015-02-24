from concurrent.futures import ThreadPoolExecutor

class AsyncTaskPool:

    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=None)

    def async_task(self):
        return self._pool.submit()