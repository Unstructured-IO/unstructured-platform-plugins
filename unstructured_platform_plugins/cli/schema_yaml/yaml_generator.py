from typing import Optional

from uvicorn.importer import import_from_string
from yaml import Dumper, dump

from unstructured_platform_plugins.cli.utils import get_func, get_schema_dict


def generate_yaml(app: str, method_name: Optional[str] = None) -> str:
    instance = import_from_string(app)
    func = get_func(instance=instance, method_name=method_name)
    schemas = get_schema_dict(func)
    output = dump(schemas, Dumper=Dumper)
    return output
