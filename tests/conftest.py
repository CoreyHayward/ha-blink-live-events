"""Shared fixtures for the Home Assistant custom integration tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def enable_custom_component(enable_custom_integrations):
    """Allow Home Assistant to load the integration from this checkout."""
    yield
