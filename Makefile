PROJECT_NAME := unstructured_platform_plugins
PROJECT_SRC_DIR := $(subst -,_,${PROJECT_NAME})
SHELL_FILES := $(shell find . -name '*.sh' -type f | grep -v venv)
###########
# INSTALL #
###########

.PHONY: install-dependencies
install-dependencies:
	@uv sync --all-groups

.PHONY: upgrade-dependencies
upgrade-dependencies:
	@uv sync --all-groups --upgrade

###########
#  TIDY   #
###########

.PHONY: tidy
tidy: tidy-ruff

.PHONY: tidy-ruff
tidy-ruff:
	uv run ruff format .
	uv run ruff check --fix-only --show-fixes .

.PHONY: tidy-shell
tidy-shell:
	shfmt -l -w ${SHELL_FILES}

###########
#  CHECK  #
###########

.PHONY: check
check: check-ruff check-shell

.PHONY: check-ruff
check-ruff:
	uv run ruff check .

.PHONY: check-shell
check-shell:
	shfmt -d ${SHELL_FILES}

.PHONY: check-version
check-version:
    # Fail if syncing version would produce changes
	scripts/version-sync.sh -c \
		-f "${PROJECT_SRC_DIR}/__version__.py" semver

###########
#  TEST   #
###########

.PHONY: test
test:
	PYTHONPATH=. pytest --cov-config=pyproject.toml --cov-report=json --cov-report=term --cov=${PROJECT_SRC_DIR} -sv
