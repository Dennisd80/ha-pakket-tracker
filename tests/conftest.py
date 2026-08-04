"""Gedeelde pytest-configuratie."""

import pytest
from pytest_homeassistant_custom_component.plugins import hass  # noqa: F401


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Maak custom_components.pakket_tracker beschikbaar in tests."""
    yield
