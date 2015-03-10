from tornado.escape import json_encode
from hurricane.db import Model

def to_json_serializable(data):
    if isinstance(data, list):
        new_list = []
        for v in data:
            new_list.append(to_json_serializable(v))
        return new_list
    if isinstance(data, Model):
        data = data.serialize()
    if isinstance(data, dict):
        for k in data.keys():
            data[k] = to_json_serializable(data[k])
    return data

def to_json(data):
    return json_encode(to_json_serializable(data))
