"""Regressietests voor de options-flow."""

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pakket_tracker.const import (
    CONF_CARRIERS,
    CONF_CONFIRMATION_ENABLED,
    CONF_CONFIRMATION_TIME,
    CONF_IMAP_TIMEOUT,
    CONF_NOTIFY_SERVICE,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_WINDOW_DAYS,
    DOMAIN,
    PRESET_CARRIERS,
)


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            CONF_CARRIERS: PRESET_CARRIERS,
            CONF_SCAN_INTERVAL: 300,
            CONF_IMAP_TIMEOUT: 30,
            CONF_SCAN_WINDOW_DAYS: 2,
            CONF_CONFIRMATION_ENABLED: True,
            CONF_CONFIRMATION_TIME: "22:00:00",
            CONF_NOTIFY_SERVICE: "",
        },
    )


async def _open_menu_step(hass, entry, step_id):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step_id}
    )


async def test_scan_settings_form_opens_and_saves(hass):
    entry = _entry()
    entry.add_to_hass(hass)

    result = await _open_menu_step(hass, entry, "scan_interval")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "scan_interval"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SCAN_INTERVAL: 600,
            CONF_IMAP_TIMEOUT: 45,
            CONF_SCAN_WINDOW_DAYS: 3,
            CONF_CONFIRMATION_ENABLED: True,
            CONF_CONFIRMATION_TIME: "07:30",
            CONF_NOTIFY_SERVICE: "",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONFIRMATION_TIME] == "07:30"


async def test_simple_carrier_form_opens_and_saves(hass):
    entry = _entry()
    entry.add_to_hass(hass)

    result = await _open_menu_step(hass, entry, "add_simple_carrier")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "add_simple_carrier"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "name": "Trunkrs",
            "email_address": "updates@example.com",
            "delivering_title": "vandaag bezorgd",
            "delivered_title": "pakket bezorgd",
            "missed_title": "bezorging gemist",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "trunkrs" in result["data"][CONF_CARRIERS]
