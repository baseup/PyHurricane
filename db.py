from motorengine import Document, DateTimeField

class Model(Document):

    def to_son(self):
        data = dict()
        for name, field in list(self._fields.items()):
            value = self.get_field_value(name)
            if isinstance(value, Document):
                data[field.db_field] = value.to_son()
            else:
                data[field.db_field] = field.to_son(value)
                if data[field.db_field]:
                    if isinstance(field, DateTimeField):
                        data[field.db_field] = value.strftime('%Y-%m-%d %H:%M:%S')
        if hasattr(self, '_id'):
            data['_id'] = str(self._id)
        return data