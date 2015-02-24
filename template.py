import tornado.template
import os

def append_template_suffix(template_name, suffix):
    if os.path.splitext(template_name)[-1].lstrip('.') != suffix:
        template_name += '.' + suffix
    return template_name

class Loader(tornado.template.Loader):
    
    def set_template_suffix(self, suffix):
        self._suffix = suffix

    def load(self, name, parent_path=None):
        return super().load(append_template_suffix(name, self._suffix), parent_path)