"""EMS Balcony Solar select platform."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_NORDPOOL_SENSOR,
    DOMAIN,
    ENTITY_NAME_TIME_RESOLUTION,
    ENTITY_SUFFIX_TIME_RESOLUTION,
    TIME_RESOLUTION_DEFAULT,
    TIME_RESOLUTION_OPTIONS,
    get_entity_unique_id,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up EMS Balcony Solar select entities from a config entry."""
    nordpool_sensor = entry.data[CONF_NORDPOOL_SENSOR]

    selects = [
        EmsBalconySolarSelect(entry.entry_id, nordpool_sensor),
    ]

    async_add_entities(selects)


class EmsBalconySolarSelect(SelectEntity):
    """Select entity for time resolution setting."""

    _attr_has_entity_name = True

    def __init__(self, config_entry_id: str, nordpool_sensor: str) -> None:
        """Initialize the select entity."""
        self._nordpool_sensor = nordpool_sensor
        self._attr_name = ENTITY_NAME_TIME_RESOLUTION
        self._attr_unique_id = get_entity_unique_id(
            config_entry_id, ENTITY_SUFFIX_TIME_RESOLUTION
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry_id)},
            name="EMS Balcony Solar",
            manufacturer="EMS",
            model="Balcony Solar",
        )
        self._attr_options = TIME_RESOLUTION_OPTIONS
        self._attr_current_option = TIME_RESOLUTION_DEFAULT
        self._attr_icon = "mdi:clock-outline"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option in self._attr_options:
            self._attr_current_option = option
            self.async_write_ha_state()
            _LOGGER.debug("Time resolution changed to: %s", option)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        nordpool_state = self.hass.states.get(self._nordpool_sensor)
        return nordpool_state is not None
