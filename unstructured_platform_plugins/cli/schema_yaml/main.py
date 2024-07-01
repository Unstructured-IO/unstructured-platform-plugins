from typing import Optional

import click

from unstructured_platform_plugins.cli.schema_yaml.yaml_generator import generate_yaml


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
def yaml(app: str, method_name: Optional[str] = None) -> None:
    output = generate_yaml(app=app, method_name=method_name)
    print(output)
