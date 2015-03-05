from motorengine import Document, DateTimeField
from bson.objectid import ObjectId

class Model(Document):

    def serialize(self):
        data = dict()
        for name, field in list(self._fields.items()):
            value = self.get_field_value(name)
            if isinstance(value, Model):
                data[field.db_field] = value.serialize()
            else:
                data[field.db_field] = field.to_son(value)
                if data[field.db_field]:
                    if isinstance(field, DateTimeField):
                        data[field.db_field] = value.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(data[field.db_field], ObjectId):
                        data[field.db_field] = str(data[field.db_field])
        if hasattr(self, '_id'):
            data['_id'] = str(self._id)
        return data