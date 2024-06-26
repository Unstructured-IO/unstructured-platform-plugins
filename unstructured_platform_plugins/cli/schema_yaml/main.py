from typing import Optional

import click
from uvicorn.importer import import_from_string
from yaml import Dumper, dump

from unstructured_platform_plugins.cli.utils import get_func, get_schema_dict


@click.command()
@click.argument("app", envvar="UVICORN_APP")
@click.option(
    "--method-name",
    required=False,
    type=str,
    default=None,
    help="If passed in instance is a class, what method to wrap. "
    "Will fall back to __call__ if none is provided.",
)
def generate_yaml(app: str, method_name: Optional[str] = None) -> None:
    instance = import_from_string(app)
    func = get_func(instance=instance, method_name=method_name)
    schemas = get_schema_dict(func)
    output = dump(schemas, Dumper=Dumper)
    print(output)
