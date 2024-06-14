PACKAGE_NAME := platform
PROJECT_NAME := api
PROJECT_PATH := platform_api
ARCH=amd64
GIT_HASH := $(shell git rev-parse --short HEAD)
GIT_BRANCH := $(shell git rev-parse --abbrev-ref HEAD)
VERSION_SCRIPTS_PATH=scripts
IMAGE_REPOSITORY := "${PACKAGE_NAME}-${PROJECT_NAME}"
IMAGE_REGISTRY=uticplatform.azurecr.io

###########
# INSTALL #
###########

.PHONY: pip-compile
pip-compile:
	./scripts/pip-compile.sh

.PHONY: install
install: install-cli install-lint install-test

.PHONY: install-cli
install-cli:
	pip install -r requirements/cli.txt

.PHONY: install-lint
install-lint:
	pip install -r requirements/lint.txt

.PHONY: install-test
install-test:
	pip install -r requirements/test.txt

###########
#  TIDY   #
###########

.PHONY: tidy
tidy: tidy-black tidy-ruff tidy-autoflake tidy-shell

.PHONY: tidy_shell
tidy-shell:
	shfmt -l -w .

.PHONY: tidy-ruff
tidy-ruff:
	ruff check --fix-only --show-fixes .

.PHONY: tidy-black
tidy-black:
	black .

.PHONY: tidy-autoflake
tidy-autoflake:
	autoflake --in-place .

###########
#  CHECK  #
###########

.PHONY: check
check: check-python check-shell

.PHONY: check-python
check-python: check-black check-flake8 check-ruff check-autoflake

.PHONY: check-black
check-black:
	black . --check

.PHONY: check-flake8
check-flake8:
	flake8 .

.PHONY: check-ruff
check-ruff:
	ruff check .

.PHONY: check-autoflake
check-autoflake:
	autoflake --check-diff .

.PHONY: check-shell
check-shell:
	shfmt -d .

###########
#  TEST   #
###########

.PHONY: test
test:
	PYTHONPATH=. pytest
