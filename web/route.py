import importlib
import tornado.gen
import tornado.web
import hurricane.web
import hurricane.io

def generate_controller(events, receiver):
    if hasattr(receiver, 'method'):
        controller = type('RouteHandler', (hurricane.web.RequestHandler,), {})
    else:
        controller = type('RouteHandler', (hurricane.web.WebSocketHandler,), {})

    if hasattr(events, 'prepare'):
        if not callable(events.prepare):
            raise ActionNotCallableError('Event or Action is not callable')
        setattr(controller, 'prepare', hurricane.io.make_coroutine(events.prepare))

    if hasattr(events, 'on_finish'):
        if not callable(events.on_finish):
            raise ActionNotCallableError('Event or Action is not callable')
        setattr(controller, 'on_finish', events.on_finish)

    return controller



class ActionNotCallableError(Exception):

    def __init__(self, message='Given action is not callable'):
        super().__init__(message)

class Route:

    def __init__(self, method, path, action, options=None):
        module = action.rsplit('.', 1)
        self.controller = module[0]
        self.action = 'index'
        if len(module) > 1:
            self.action = module[1]

        self.method = method
        self.options = options
        self.path = '/' + path.lstrip('/')
        self.handler_name = self.controller + '.' + self.action

    def set_filters(self, filters):
        if not isinstance(filters, dict):
            self.set_filters({ 'before': filters })
            return

        for key in filters.keys():
            for fn_key, fn_val in enumerate(filters[key]):
                filters[key][fn_key] = hurricane.io.make_non_blocking(fn_val)
        self._filters = filters

    def create_handler(self):
        module = importlib.import_module('app.controllers.' + self.controller)
        if hasattr(module, self.action):

            action = getattr(module, self.action)
            if not callable(action):
                raise ActionNotCallableError()

            filters = None
            if hasattr(self, '_filters'):
                filters = self._filters

            def before_func(request_handler):
                if not filters or 'before' not in filters:
                    return
                for before_fn_val in filters['before']:
                    before_return = yield before_fn_val(request_handler)
                    if before_return or before_return is None:
                        if request_handler.is_finished():
                            return False
                        continue
                    return False
                return True

            def after_func(request_handler):
                if not filters or 'after' not in filters:
                    return
                for after_fn_val in filters['after']:
                    after_return = yield after_fn_val(request_handler)
                    if after_return or after_return is None:
                        if request_handler.is_finished():
                            return False
                        continue
                    return False
                return True

            before_func = hurricane.io.make_non_blocking(before_func)
            action = hurricane.io.make_non_blocking(action)
            after_func = hurricane.io.make_non_blocking(after_func)

            def route_handler(self, **kwargs):
                if not filters:
                    yield action(self, **kwargs)
                    return

                if (yield before_func(self)):
                    yield action(self, **kwargs)
                    yield after_func(self)

            self.handler = hurricane.io.make_non_blocking(route_handler)
        else:
            def route_handler(self, **kwargs):
                pass
            self.handler = route_handler

class WebSocketRoute:

    def __init__(self, path, action, options=None):
        self.controller = action
        self.options = options
        self.path = '/' + path.lstrip('/')

    def create_handler(self):
        module = importlib.import_module('app.controllers.' + self.controller)
        self.handler = module

class RouteGroup:

    def __init__(self, routes=[]):
        self.set_routes(routes)

    def set_routes(self, routes):
        self._routes = routes

    def add_route(self, route):
        self._routes.append(route)

    def clear_routes(self):
        self._routes = []

    def __getitem__(self, key):
        return self._routes[key]

class RouteResource(RouteGroup):

    def __init__(self, path, action, options=None):
        param_id  = '/(?P<id>[A-Za-z0-9-_]+)'
        super().__init__([
            Route('GET', path, action + '.find', options),
            Route('POST', path, action + '.create', options),
            Route('PUT', path + param_id, action + '.update', options),
            Route('GET', path + param_id, action + '.find_one', options),
            Route('DELETE', path + param_id, action + '.destroy', options)
        ])

class RoutePrefix(RouteGroup):

    def __init__(self, prefix, routes=[]):
        prefixed_routes = []
        prefix = '/' + prefix.lstrip('/')
        for route in routes:
            if isinstance(route, RouteGroup):
                for sub in route:
                    sub.path = prefix + sub.path
                    prefixed_routes.append(sub)
                continue
            route.path = prefix + route.path
            prefixed_routes.append(route)
        super().__init__(prefixed_routes)

class RouteSubdomain(RouteGroup):

    def __init__(self, subdomain, routes):
        subdomain_routes = []
        for route in routes:
            if isinstance(route, RouteGroup):
                for sub in route:
                    subdomain_routes.append(sub)
                continue
            subdomain_routes.append(route)
        super().__init__(subdomain_routes)
