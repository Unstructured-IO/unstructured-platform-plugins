"""
setup.py

unstructured-platform-plugins - utility library for unstructured plugin development

Copyright 2022 Unstructured Technologies, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

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
    description="A utility library that provides tools around unstructured plugin development",
    long_description=open("README.md", encoding="utf-8").read(),  # noqa: SIM115
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.10,<3.13",
    url="https://github.com/Unstructured-IO/unstructured-platform-plugins",  # noqa: 501
    packages=find_packages(),
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "etl-uvicorn=unstructured_platform_plugins.etl_uvicorn.main:cmd",
            "etl-validate=unstructured_platform_plugins.validate_api:validate_api",
        ],
    },
    install_requires=load_requirements("requirements/cli.in")
    + load_requirements("requirements/validate.in"),
)
