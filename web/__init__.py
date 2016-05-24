from hurricane.template import Loader, append_template_suffix
from motorengine.connection import connect
from hurricane.io import AsyncTaskPool
from hurricane.helpers import to_json
from motorengine import Document
from hurricane.db import Model
from types import ModuleType
from . import route

import tornado.options
import tornado.escape
import tornado.ioloop
import tornado.web
import tornado.websocket
import http.client
import traceback
import importlib
import signal
import sys
import re
import os

class RouteProvider:

    def __init__(self):
        self._routes = {}
        self._filters = {}
        self._stop_saving = False
        self._subdomain_routes = {}

    def when(self, action, filter=None):
        if isinstance(action, dict):
            for action_filter in action.items():
                self.when(action_filter[0], action_filter[1])
            return

        if isinstance(filter, str) or isinstance(filter, list):
            filter = { 'before': filter }

        if isinstance(filter, dict):
            for key in filter.keys():
                if isinstance(filter[key], str):
                    filter[key] = [filter[key]]
                if not len(filter[key]):
                    continue
                self._filters[action] = []
                for fn in filter[key]:
                    parts = fn.rsplit('.', 1)
                    module = importlib.import_module('app.filters.' + parts[0])
                    if hasattr(module, parts[1]):
                        tmp_fn = getattr(module, parts[1])
                        if not callable(tmp_fn):
                            raise ActionNotCallable('Filter is not callable')
                        self._filters[action].append(tmp_fn)

    def _save_route(self, created_route):
        if created_route.path not in self._routes:
            self._routes[created_route.path] = []

        if hasattr(created_route, 'handler_name') and created_route.handler_name in self._filters:
            created_route.set_filters(self._filters[created_route.handler_name])
        elif '*' in self._filters:
            created_route.set_filters(self._filters['*'])

        created_route.create_handler()
        self._routes[created_route.path].append(created_route)

    def _save_subdomain_route(self, subdomain, created_route):
        if hasattr(created_route, 'handler_name') and created_route.handler_name in self._filters:
            created_route.set_filters(self._filters[created_route.handler_name])
        elif '*' in self._filters:
            created_route.set_filters(self._filters['*'])

        created_route.create_handler()
        if subdomain not in self._subdomain_routes:
            self._subdomain_routes[subdomain] = {}
        if created_route.path not in self._subdomain_routes:
            self._subdomain_routes[subdomain][created_route.path] = []
        self._subdomain_routes[subdomain][created_route.path].append(created_route)

    def _attach_event_handlers(self, controller, receiver):
        if hasattr(receiver, 'method'):
            setattr(controller, receiver.method.lower(), receiver.handler)
        else:
            for attr in dir(receiver.handler):
                setattr(controller, attr, getattr(receiver.handler, attr))

    def path(self, method, url, action, options=None):
        created_route = route.Route(method, url, action, options)
        if not self._stop_saving:
            self._save_route(created_route)
        return created_route

    def get(self, url, action, options=None):
        return self.path('GET', url, action, options)

    def post(self, url, action, options=None):
        return self.path('POST', url, action, options)

    def put(self, url, action, options=None):
        return self.path('PUT', url, action, options)

    def delete(self, url, action, options=None):
        return self.path('DELETE', url, action, options)

    def resource(self, url, module, options=None):
        created_route = route.RouteResource(url, module, options)
        if not self._stop_saving:
            for resource in created_route:
                self._save_route(resource)
        return created_route

    def websocket(self, url, action, options=None):
        created_route = route.WebsocketRoute(url, action, options)
        if not self._stop_saving:
            self._save_route(created_route)
        return created_route

    def subdomain(self, subdomain, urls):
        self._stop_saving = True
        created_routes = []
        for for_subdomain in urls:
            created_routes.append(getattr(self, for_subdomain[0])(*for_subdomain[1:]))
        for subdomain_route in route.RouteSubdomain(subdomain, created_routes):
            self._save_subdomain_route(subdomain, subdomain_route)
        self._stop_saving = False
        return created_routes

    def prefix(self, prefix, routes):
        self._stop_saving = True
        created_routes = []
        for for_prefix in routes:
            created_routes.append(getattr(self, for_prefix[0])(*for_prefix[1:]))
        for prefixed_route in route.RoutePrefix(prefix, created_routes):
            self._save_route(prefixed_route)
        self._stop_saving = False
        return created_routes

    def get_routes(self):
        return self._routes

    def get_subdomain_routes(self, subdomain):
        if subdomain not in self._subdomain_routes:
            return None
        return self._subdomain_routes[subdomain]

    def set_hooks(self, events):
        self._hooks = events

    def get_urls(self):
        tmp_urls = {}
        for saved_route in self._routes.items():
            options = {}
            for receiver in saved_route[1]:
                if saved_route[0] not in tmp_urls:
                    route_controller = route.generate_controller(self._hooks, receiver)
                else:
                    route_controller = tmp_urls[saved_route[0]]

                self._attach_event_handlers(route_controller, receiver)
                tmp_urls[saved_route[0]] = route_controller

                if receiver.options:
                    options = options.update(receiver.options)
            tmp_urls[saved_route[0]] = (saved_route[0], tmp_urls[saved_route[0]], options)
        return tmp_urls.values()

    def get_subdomains(self):
        tmp_subdomain_routes = {}
        for saved_subdomain in self._subdomain_routes.items():
            tmp_urls = {}
            for saved_route in saved_subdomain[1].items():
                options = {}
                for receiver in saved_route[1]:
                    if saved_route[0] not in tmp_urls:
                        route_controller = route.generate_controller(self._hooks, receiver)
                    else:
                        route_controller = tmp_urls[saved_route[0]]

                    self._attach_event_handlers(route_controller, receiver)
                    tmp_urls[saved_route[0]] = route_controller

                    if receiver.options:
                        options = options.update(receiver.options)
                tmp_urls[saved_route[0]] = (saved_route[0], tmp_urls[saved_route[0]], options)
            tmp_subdomain_routes[saved_subdomain[0]] = tmp_urls.values()
        return tmp_subdomain_routes

class Config:

    _default_keys = [
        'port',
        'autoreload',
        'debug',
        'default_handler_class',
        'default_handler_args',
        'compress_response',
        'log_function',
        'serve_traceback',
        'ui_modules',
        'ui_methods',
        'cookie_secret',
        'login_url',
        'xsrf_cookies',
        'xsrf_cookie_version',
        'twitter_consumer_key',
        'twitter_consumer_secret',
        'friendfeed_consumer_key',
        'friendfeed_consumer_secret',
        'google_consumer_key',
        'google_consumer_secret',
        'facebook_api_key',
        'facebook_secret',
        'autoescape',
        'compiled_template_cache',
        'template_path',
        # 'template_loader',
        'static_hash_cache',
        'static_path',
        'static_url_prefix',
        'static_handler_class',
        'static_handler_args',
        'global_xss_filter',
        'template_suffix',
        'thread_max_workers',
        'database',
        'enable_logs',
        'log_path'
    ]

    _default_values = {
        'port': 8888,
        'template_path': 'app/views',
        'template_suffix': 'html',
        'autoescape': 'xhtml_escape',
        'static_path': 'assets',
        'static_url_prefix': 'assets/',
        'global_xss_filter': False,
        'log_path': 'logs/',
        'enable_logs': False
    }

    @staticmethod
    def parse(settings):
        parsed_config = {}
        if isinstance(settings, ModuleType):
            for key in Config._default_keys:
                ukey = key.upper()
                if hasattr(settings, ukey):
                    parsed_config[key] = getattr(settings, ukey)
                elif key in Config._default_values:
                    parsed_config[key] = Config._default_values[key]
        return parsed_config

class Bootstrap:

    def __init__(self, app):
        self._app = app

    def _setup_db(self):
        db = self._app.settings.get('database')
        if db is None or not len(db):
            return

        def create_host(config):
            port = ''
            host = 'mongodb://'
            credentials = ''
            if 'password' in config and config['password']:
                credentials = ':' + config['password']
            if 'username' in config and config['username']:
                credentials = config['username'] + credentials + '@'
            if 'port' in config and config['port']:
                port = ':' + str(config['port'])
            return host + credentials + config['host'] + port + '/' + config['db']

        io_loop = self._app.get_ioloop()
        default = db.pop('default')
        connect(default['db'], host=create_host(default), io_loop=io_loop)

        for conf in db.items():
            connect(conf[1]['db'], alias=conf[0], host=create_host(conf[1]), io_loop=io_loop)

    def run(self):
        print('info: Starting...')
        self._setup_db()
        if hasattr(self._app._hooks, 'bootstrap'):
            if not callable(self._app._hooks.bootstrap):
                raise route.ActionNotCallable('Bootstrap event is not callable')
            self._app._hooks.bootstrap(self._app)

        self._app.listen(self._app.settings.get('port'))
        io_loop = self._app.get_ioloop()
        if hasattr(self._app._hooks, 'shutdown'):
            if not callable(self._app._hooks.shutdown):
                raise route.ActionNotCallable('Shutdown event is not callable')
            def on_shutdown():
                self._app._hooks.shutdown(self._app)
                sys.exit(0)
            signal.signal(signal.SIGINT, lambda sig, frame: io_loop.add_callback_from_signal(on_shutdown))

        print('info: Server started in `' + self._app.root_dir + '`')
        print('info: To see your app, visit http://localhost:' + str(self._app.settings.get('port')))
        print('info: To shut down Tornado, press <CTRL> + C at any time.')
        io_loop.start()

class Application(tornado.web.Application):

    def __init__(self, routes, events, settings):
        settings = Config.parse(settings)
        self._hooks = events
        self._filters = {}
        self.subdomains = []

        for arg_value in sys.argv:
            if arg_value.find('--port=') == 0:
                settings['port'] = arg_value.replace('--port=', '', 1).strip()

        self.root_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        settings['template_path'] = self.root_dir + '/' + settings['template_path'].lstrip('/')
        settings['static_path'] = self.root_dir + '/' + settings['static_path'].lstrip('/')
        settings['static_url_prefix'] = '/' + settings['static_url_prefix'].lstrip('/')

        template_args = {
            'autoescape': settings['autoescape']
        }
        template_loader = Loader(settings['template_path'], **template_args)
        template_loader.set_template_suffix(settings['template_suffix'])
        settings['template_loader'] = template_loader

        cli_args = [sys.argv[0]]
        if 'enable_logs' in settings and settings['enable_logs'] and 'log_path' in settings and settings['log_path']:
            settings['log_path'] = self.root_dir + '/' + settings['log_path'].strip('/') + '/'
            if not os.path.exists(settings['log_path']):
                os.mkdir(settings['log_path'])
            cli_args.append('--log_file_prefix=' + settings['log_path'] + 'port-' + str(settings['port']) + '.log')

        if len(cli_args) > 1:
            tornado.options.parse_command_line(cli_args)

        if isinstance(routes, ModuleType):
            routes = routes.routes

        subdomains = None
        if isinstance(routes, RouteProvider):
            routes.set_hooks(self._hooks)
            subdomains = routes.get_subdomains()
            routes = routes.get_urls()

        self.io = AsyncTaskPool()
        super().__init__(routes, **settings)
        if subdomains:
            for subdomain in subdomains.items():
                self.add_handlers(subdomain[0], subdomain[1])
                self.subdomains.append(subdomain[0])

    def get_ioloop(self):
        return tornado.ioloop.IOLoop.instance()

    def run(self):
        Bootstrap(self).run()

class ViewData(object):

    def __init__(self):
        self.__dict__['data'] = {}

    def __getattr__(self, name):
        return self.__dict__['data'].get(name)

    def __setattr__(self, name, value):
        self.__dict__['data'][name] = value

    def merge(self, data):
        self.__dict__['data'].update(data)
        return self

    def all(self):
        return self.__dict__['data']

class URI:

    def __init__(self, request_path):
        if request_path[0] == '/':
            request_path = request_path[1:]
        self.path = request_path
        self.segments = self.path.split('/')

    def segment(self, index, default=None):
        if index < 1:
            return None
        index -= 1
        if index >= len(self.segments):
            return default
        return self.segments[index]

class RequestHandler(tornado.web.RequestHandler):

    def __init__(self, application, request, **kwargs):
        self._setup(application, request)
        super().__init__(application, request, **kwargs)
        self.disable_cache()

    @property
    def io(self):
        return self.application.io

    def _setup(self, application, request, with_session=True):
        self.view = ViewData()
        self.request = request
        self.application = application
        if not hasattr(self, 'uri'):
            self.uri = URI(self.request.path)

    def disable_cache(self):
        self.set_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.set_header('Pragma', 'no-cache')
        self.set_header('Expires', '0')

    def render_json(self, data):
        self.set_header('Content-Type', 'application/json')
        self.write(to_json(data))
        self.finish()

    def write_error(self, status_code, **kwargs):
        kwargs['code'] = status_code
        if 'exc_info' in kwargs:
            if self.settings.get('serve_traceback'):
                kwargs['message'] = "\n" + ''.join(traceback.format_exception(*kwargs['exc_info'])) + "\n"
            else:
                kwargs['message'] = kwargs['exc_info'][1]
        elif hasattr(self, '_reason'):
            kwargs['message'] = self._reason
        else:
            kwargs['message'] = http.client.responses[status_code]

        self.render('errors/' + str(status_code) + '.' + self.settings.get('template_suffix'), **kwargs)

    def get_argument(self, name, default=None, strip=True, xss_filter=None):
        return self._get_argument(name, default, self.request.arguments, strip, xss_filter)

    def get_query_argument(self, name, default=None, strip=True, xss_filter=None):
        return self._get_argument(name, default, self.request.query_arguments, strip, xss_filter)

    def get_body_argument(self, name, default=None, strip=True, xss_filter=None):
        return self._get_argument(name, default, self.request.body_arguments, strip, xss_filter)

    def _get_argument(self, name, default, source, strip=True, xss_filter=None):
        val = super()._get_argument(name, default, source, strip)
        if val and (xss_filter == True or (xss_filter is None and self.settings.get('global_xss_filter'))):
            return tornado.escape.xhtml_escape(val)
        return val

    def get_arguments(self, name, strip=True, xss_filter=None):
        return self._get_arguments(name, self.request.arguments, strip, xss_filter)

    def get_query_arguments(self, name, strip=True, xss_filter=None):
        return self._get_arguments(name, self.request.query_arguments, strip, xss_filter)

    def get_body_arguments(self, name, strip=True, xss_filter=None):
        return self._get_arguments(name, self.request.body_arguments, strip, xss_filter)

    def _get_arguments(self, name, source, strip=True, xss_filter=None):
        values = super()._get_arguments(name, source, strip)
        if values and (xss_filter == True or (xss_filter is None and self.settings.get('global_xss_filter'))):
            for k, v in enumerate(values):
                if v:
                    values[k] = tornado.escape.xhtml_escape(v)
        return values

    def view_exists(self, path):
        path = self.settings.get('template_path') + (('/' + path.lstrip('/')).rstrip('.') + '.')
        path = path + self.settings.get('template_suffix')
        return os.path.exists(path)

    def render_string(self, template_name, **kwargs):
        template_name = append_template_suffix(template_name, self.settings.get('template_suffix'))
        view_data = self.view.all()
        view_data.update(kwargs)
        return super().render_string(template_name, **view_data)

    def get_template_namespace(self):
        namespace = super().get_template_namespace()
        namespace.update({
            'settings': self.settings,
            'uri': self.uri
        })
        return namespace

    def flash_cookie(self, name):
        value = self.get_cookie(name)
        if value is not None:
            self.clear_cookie(name)
        return value

    def flash_secure_cookie(self, name):
        value = self.get_secure_cookie(name)
        if value is not None:
            self.clear_cookie(name)
        return value

    def finish(self, chunk=None):
        super().finish(chunk)

    def is_finished(self):
        return self._finished

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    pass

class ErrorHandler(RequestHandler):

    def __init__(self, application, request, status_code):
        super().__init__(application, request)
        self.set_status(status_code)

    def prepare(self):
        raise tornado.web.HTTPError(self._status_code)

tornado.web.ErrorHandler = ErrorHandler
