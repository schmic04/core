"""EMS Balcony Solar number platform."""

from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_HOURS_OF_OPERATING,
    CONF_NORDPOOL_SENSOR,
    CREATE_HOURS_NUMBER_ENTITY,
    DEFAULT_HOURS_OF_OPERATING,
    DEFAULT_WINDOW,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

NUMBER_DESCRIPTIONS: tuple[NumberEntityDescription, ...] = (
    NumberEntityDescription(
        key="window_size",
        name="Window Size",
        icon="mdi:window-open-variant",
        native_min_value=1,
        native_max_value=24,
        native_step=1,
        native_unit_of_measurement="hours",
        mode=NumberMode.BOX,
    ),
    NumberEntityDescription(
        key="hours_of_operating",
        name="Hours of Operating",
        icon="mdi:clock-time-eight-outline",
        native_min_value=1,
        native_max_value=24,
        native_step=1,
        native_unit_of_measurement="hours",
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up EMS Balcony Solar number entities from a config entry."""
    nordpool_sensor = entry.data[CONF_NORDPOOL_SENSOR]
    hours_config = entry.data.get(CONF_HOURS_OF_OPERATING)

    numbers = []

    # Always create window size number entity
    numbers.append(
        EmsBalconySolarNumber(
            entry.entry_id,
            nordpool_sensor,
            NUMBER_DESCRIPTIONS[0],  # window_size
            DEFAULT_WINDOW,
        )
    )

    # Only create hours_of_operating number entity if configured to do so
    if not hours_config or hours_config == CREATE_HOURS_NUMBER_ENTITY:
        numbers.append(
            EmsBalconySolarNumber(
                entry.entry_id,
                nordpool_sensor,
                NUMBER_DESCRIPTIONS[1],  # hours_of_operating
                DEFAULT_HOURS_OF_OPERATING,
            )
        )

    async_add_entities(numbers)


class EmsBalconySolarNumber(NumberEntity):
    """Number entity for EMS Balcony Solar settings."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        nordpool_sensor: str,
        description: NumberEntityDescription,
        default_value: float,
    ) -> None:
        """Initialize the number entity."""
        self.entity_description = description
        self._nordpool_sensor = nordpool_sensor
        self._attr_unique_id = f"{nordpool_sensor}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, nordpool_sensor)},
            name="EMS Balcony Solar",
            manufacturer="EMS",
            model="Balcony Solar",
        )
        self._attr_native_value = default_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self._attr_native_value = int(value)
        self.async_write_ha_state()
        _LOGGER.debug("%s changed to: %s", self.entity_description.name, value)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        nordpool_state = self.hass.states.get(self._nordpool_sensor)
        return nordpool_state is not None
