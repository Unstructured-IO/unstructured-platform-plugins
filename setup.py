from pathlib import Path
from typing import List, Union

from setuptools import find_packages, setup

from unstructured_platform_plugins.__version__ import __version__


def load_requirements(file: Union[str, Path]) -> List[str]:
    path = file if isinstance(file, Path) else Path(file)
    requirements: List[str] = []
    if not path.is_file():
        raise FileNotFoundError(f"path does not point to a valid file: {path}")
    if not path.suffix == ".in":
        raise ValueError(f"file should have .in extension: {path}")
    file_dir = path.parent.resolve()
    with open(file, encoding="utf-8") as f:
        raw = f.read().splitlines()
        requirements.extend([r for r in raw if not r.startswith("#") and not r.startswith("-")])
        recursive_reqs = [r for r in raw if r.startswith("-r")]
    for recursive_req in recursive_reqs:
        file_spec = recursive_req.split()[-1]
        file_path = Path(file_dir) / file_spec
        requirements.extend(load_requirements(file=file_path.resolve()))
    # Remove duplicates and any blank entries
    return list({r for r in requirements if r})


setup(
    name="unstructured-platform-plugins",
    version=__version__,
    python_requires=">=3.10,<3.13",
    url="https://github.com/Unstructured-IO/unstructured-platform-plugins",  # noqa: 501
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "etl-uvicorn=unstructured_platform_plugins.etl_uvicorn.main:cmd",
            "etl-validate=unstructured_platform_plugins.validate_api:validate_api",
        ],
    },
    install_requires=load_requirements("requirements/cli.in")
    + load_requirements("requirements/validate.in"),
)
