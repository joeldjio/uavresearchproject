.PHONY: help test test-unit test-integration test-ui test-system test-e2e test-all test-fast test-coverage clean lint format install install-dev install-ros install-test

# Default target
help:
	@echo "UAV Research Project - Test & Development Commands"
	@echo ""
	@echo "Installation:"
	@echo "  make install          Install core package"
	@echo "  make install-dev      Install with development dependencies"
	@echo "  make install-ros      Install with ROS2 support"
	@echo "  make install-test     Install with test dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests (fast only)"
	@echo "  make test-unit        Run unit tests only"
	@echo "  make test-integration Run integration tests only"
	@echo "  make test-ui          Run UI tests only"
	@echo "  make test-system      Run system tests (requires SITL)"
	@echo "  make test-e2e         Run E2E tests (requires Playwright)"
	@echo "  make test-all         Run ALL tests including slow ones"
	@echo "  make test-fast        Run fast tests only (default)"
	@echo "  make test-coverage    Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             Run all linters (ruff, mypy, black, isort)"
	@echo "  make format           Auto-format code with black and isort"
	@echo "  make clean            Clean build artifacts and cache"
	@echo ""
	@echo "CI/CD:"
	@echo "  make ci-test          Run CI test suite"
	@echo "  make ci-lint          Run CI linting"
	@echo "  make ci-build         Build package for CI"

# ============================================================================
# Installation
# ============================================================================
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

install-ros:
	pip install -e ".[ros]"

install-test:
	pip install -e ".[test]"
	pip install pytest-cov pytest-xdist pytest-timeout pytest-benchmark

# ============================================================================
# Testing
# ============================================================================
test: test-fast

test-unit:
	@echo "Running unit tests..."
	pytest tests/ -m unit -v

test-integration:
	@echo "Running integration tests..."
	pytest tests/ -m integration -v

test-ui:
	@echo "Running UI tests..."
	pytest tests/test_ui_*.py -v

test-system:
	@echo "Running system tests (requires SITL)..."
	pytest tests/ -m system -v --timeout=300

test-e2e:
	@echo "Running E2E tests (requires Playwright)..."
	pytest tests/e2e/ -m e2e -v

test-all:
	@echo "Running ALL tests (including slow)..."
	pytest tests/ -v

test-fast:
	@echo "Running fast tests only..."
	pytest tests/ -m "not slow and not sitl and not e2e" -v

test-coverage:
	@echo "Running tests with coverage..."
	pytest tests/ \
		-m "not slow and not sitl and not e2e" \
		--cov=skymeshx \
		--cov=tools.ui \
		--cov-report=html \
		--cov-report=term \
		--cov-report=xml \
		-v
	@echo ""
	@echo "Coverage report generated in htmlcov/index.html"

test-coverage-all:
	@echo "Running ALL tests with coverage..."
	pytest tests/ \
		--cov=skymeshx \
		--cov=tools.ui \
		--cov-report=html \
		--cov-report=term \
		--cov-report=xml \
		-v

# ============================================================================
# Code Quality
# ============================================================================
lint:
	@echo "Running ruff..."
	ruff check skymeshx/ tools/ tests/ || true
	@echo ""
	@echo "Running mypy..."
	mypy skymeshx/ --ignore-missing-imports || true
	@echo ""
	@echo "Running black (check only)..."
	black --check skymeshx/ tools/ tests/ || true
	@echo ""
	@echo "Running isort (check only)..."
	isort --check-only skymeshx/ tools/ tests/ || true

format:
	@echo "Formatting code with black..."
	black skymeshx/ tools/ tests/
	@echo ""
	@echo "Sorting imports with isort..."
	isort skymeshx/ tools/ tests/

# ============================================================================
# CI/CD
# ============================================================================
ci-test:
	pytest tests/ \
		-m "not slow and not sitl and not e2e" \
		--cov=skymeshx \
		--cov=tools.ui \
		--cov-report=xml \
		--cov-report=term \
		--junitxml=junit.xml \
		-v

ci-lint:
	ruff check skymeshx/ tools/ tests/
	black --check skymeshx/ tools/ tests/
	isort --check-only skymeshx/ tools/ tests/
	mypy skymeshx/ --ignore-missing-imports

ci-build:
	python -m build
	twine check dist/*

# ============================================================================
# Cleanup
# ============================================================================
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf junit.xml
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	@echo "Clean complete!"

# ============================================================================
# Development Helpers
# ============================================================================
watch-tests:
	@echo "Watching for changes and running tests..."
	pytest-watch tests/ -m "not slow and not sitl and not e2e" -v

benchmark:
	@echo "Running benchmarks..."
	pytest tests/ -m benchmark --benchmark-only -v

profile:
	@echo "Running tests with profiling..."
	pytest tests/ -m "not slow" --profile -v

# ============================================================================
# Documentation
# ============================================================================
docs:
	@echo "Building documentation..."
	@echo "TODO: Add sphinx or mkdocs setup"

# ============================================================================
# Docker
# ============================================================================
docker-build:
	docker-compose -f docker/docker-compose.yml build

docker-test:
	docker-compose -f docker/docker-compose.yml run --rm test

# ============================================================================
# Release
# ============================================================================
bump-version:
	python tools/installer/bump_version.py

build-installers:
	@echo "Building installers..."
	cd tools/installer && ./build.ps1
