"""EMS Balcony Solar sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_NORDPOOL_SENSOR,
    DEFAULT_WINDOW,
    DOMAIN,
    ENTITY_NAME_EPEX_PRICE_SUBLISTS,
    ENTITY_NAME_PRICE_AVG,
    ENTITY_NAME_PRICE_LIST_LENGTH,
    ENTITY_SUFFIX_EPEX_PRICE_SUBLISTS,
    ENTITY_SUFFIX_PRICE_AVG,
    ENTITY_SUFFIX_PRICE_LIST_LENGTH,
    ENTITY_SUFFIX_TIME_RESOLUTION,
    ENTITY_SUFFIX_WINDOW_SIZE,
    MINUTES_PER_HOUR,
    MINUTES_PER_QUARTER_HOUR,
    TIME_RESOLUTION_DEFAULT,
    get_entity_id,
    get_entity_unique_id,
)
from .ems_tools import (
    convert_hours_to_minutes,
    dynamic_sublists_with_window,
    get_resolution_minutes,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up EMS Balcony Solar sensors from a config entry."""
    nordpool_sensor = entry.data[CONF_NORDPOOL_SENSOR]

    sensors = [
        EmsBalconySolarSensor(
            entry.entry_id,
            nordpool_sensor,
            ENTITY_SUFFIX_PRICE_AVG,
            ENTITY_NAME_PRICE_AVG,
        ),
        EmsBalconySolarSensor(
            entry.entry_id,
            nordpool_sensor,
            ENTITY_SUFFIX_PRICE_LIST_LENGTH,
            ENTITY_NAME_PRICE_LIST_LENGTH,
        ),
        EmsBalconySolarSensor(
            entry.entry_id,
            nordpool_sensor,
            ENTITY_SUFFIX_EPEX_PRICE_SUBLISTS,
            ENTITY_NAME_EPEX_PRICE_SUBLISTS,
        ),
    ]

    async_add_entities(sensors)


class EmsBalconySolarSensor(SensorEntity):
    """Representation of an EMS Balcony Solar sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        config_entry_id: str,
        nordpool_sensor: str,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize the sensor."""
        self._nordpool_sensor = nordpool_sensor
        self._sensor_type = sensor_type
        self._attr_name = name
        self._attr_unique_id = get_entity_unique_id(config_entry_id, sensor_type)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry_id)},
            name="EMS Balcony Solar",
            manufacturer="EMS",
            model="Balcony Solar",
        )
        self._unsubscribe_callback: Callable[[], None] | None = None

        # Generate entity IDs using consistent schema
        self._window_number = get_entity_id("number", ENTITY_SUFFIX_WINDOW_SIZE)
        self._time_resolution_select = get_entity_id(
            "select", ENTITY_SUFFIX_TIME_RESOLUTION
        )

    def _get_time_resolution_setting(self) -> str:
        """Get the current time resolution setting from select entity."""
        select_state = self.hass.states.get(self._time_resolution_select)

        if not select_state or select_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return TIME_RESOLUTION_DEFAULT

        return select_state.state

    def _expand_price_data_for_resolution(
        self, nordpool_prices: list[float]
    ) -> list[float]:
        """Expand price data based on time resolution setting.

        Args:
            nordpool_prices: Hourly price data from Nordpool

        Returns:
            Price data expanded according to time resolution
        """
        time_resolution = self._get_time_resolution_setting()
        resolution_minutes = get_resolution_minutes(time_resolution)

        if resolution_minutes == MINUTES_PER_QUARTER_HOUR:
            # Expand hourly data to 15-minute intervals by repeating each price 4 times
            expanded_prices = []
            for price in nordpool_prices:
                expanded_prices.extend([price] * 4)  # 4 × 15min = 60min
            return expanded_prices

        # For hourly resolution, use data as-is
        return nordpool_prices

    def _get_resolution_info(self) -> tuple[int, int, str]:
        """Get resolution information for current time setting.

        Returns:
            Tuple of (resolution_minutes, entries_per_hour, unit_name)
        """
        time_resolution = self._get_time_resolution_setting()
        resolution_minutes = get_resolution_minutes(time_resolution)

        if resolution_minutes == MINUTES_PER_QUARTER_HOUR:
            return MINUTES_PER_QUARTER_HOUR, 4, "15-minute intervals"

        return MINUTES_PER_HOUR, 1, "hourly intervals"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Track nordpool, window, and time resolution sensor changes
        # Note: hours_of_operating is not tracked as it's only used by binary_sensor
        self._unsubscribe_callback = async_track_state_change_event(
            self.hass,
            [
                self._nordpool_sensor,
                self._window_number,  # ✅ Jetzt überwacht
                self._time_resolution_select,
            ],
            self._handle_sensor_state_change,
        )

        await self._update_from_sensors()

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._unsubscribe_callback:
            self._unsubscribe_callback()

    @callback
    def _handle_sensor_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle state changes of the input sensors."""
        self.hass.async_create_task(self._update_from_sensors())

    def _get_window_value(self) -> int:
        """Get the window value from number entity or default."""
        window_state = self.hass.states.get(self._window_number)

        if not window_state or window_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return DEFAULT_WINDOW

        try:
            window_value = int(float(window_state.state))
            return max(1, window_value)
        except (ValueError, TypeError):
            _LOGGER.debug("Invalid window number value: %s", window_state.state)
            return DEFAULT_WINDOW

    async def _update_from_sensors(self) -> None:
        """Update sensor value based on input sensor data."""
        nordpool_state = self.hass.states.get(self._nordpool_sensor)

        if not nordpool_state or nordpool_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            self.async_write_ha_state()
            return

        try:
            today_prices = nordpool_state.attributes.get("today", [])
            tomorrow_prices = nordpool_state.attributes.get("tomorrow", [])
            tomorrow_valid = nordpool_state.attributes.get("tomorrow_valid", False)

            if tomorrow_valid and tomorrow_prices:
                nordpool_prices = today_prices + tomorrow_prices
            else:
                nordpool_prices = today_prices

            if not nordpool_prices:
                self._attr_native_value = None
                self._attr_extra_state_attributes = {}
                self.async_write_ha_state()
                return

            window_value_hours = self._get_window_value()
            time_resolution = self._get_time_resolution_setting()
            resolution_minutes, entries_per_hour, unit_name = (
                self._get_resolution_info()
            )

            # Convert hours to minutes for internal calculations
            window_value_minutes = convert_hours_to_minutes(window_value_hours)

            match self._sensor_type:
                case "price_avg":
                    self._attr_native_value = sum(nordpool_prices) / len(
                        nordpool_prices
                    )
                    self._attr_unit_of_measurement = nordpool_state.attributes.get(
                        "unit", "€/kWh"
                    )
                    self._attr_extra_state_attributes = {
                        "today_count": len(today_prices),
                        "tomorrow_count": len(tomorrow_prices) if tomorrow_valid else 0,
                        "tomorrow_valid": tomorrow_valid,
                        "window_value_hours": window_value_hours,
                        "window_value_minutes": window_value_minutes,
                        "time_resolution_setting": time_resolution,
                        "resolution_minutes": resolution_minutes,
                        "resolution_unit": unit_name,
                        "window_number": self._window_number,
                        "time_resolution_sensor": self._time_resolution_select,
                    }

                case "price_list_length":
                    # Expand price data based on resolution
                    expanded_prices = self._expand_price_data_for_resolution(
                        nordpool_prices
                    )

                    self._attr_native_value = len(expanded_prices)
                    self._attr_unit_of_measurement = None
                    self._attr_extra_state_attributes = {
                        "price_list": expanded_prices,
                        "count": len(expanded_prices),
                        "original_hourly_prices": nordpool_prices,
                        "today_prices": today_prices,
                        "tomorrow_prices": tomorrow_prices if tomorrow_valid else [],
                        "today_count": len(today_prices),
                        "tomorrow_count": len(tomorrow_prices) if tomorrow_valid else 0,
                        "tomorrow_valid": tomorrow_valid,
                        "window_value_hours": window_value_hours,
                        "window_value_minutes": window_value_minutes,
                        "time_resolution_setting": time_resolution,
                        "resolution_minutes": resolution_minutes,
                        "resolution_unit": unit_name,
                        "entries_per_hour": entries_per_hour,
                        "window_number": self._window_number,
                        "time_resolution_sensor": self._time_resolution_select,
                    }

                case "epex_price_sublists":
                    # Expand price data based on resolution for sublist processing
                    expanded_prices = self._expand_price_data_for_resolution(
                        nordpool_prices
                    )

                    # Calculate window in time entries based on resolution
                    window_entries = window_value_minutes // resolution_minutes
                    window_entries = max(1, window_entries)  # Ensure at least 1 entry

                    sublists, index_lists = dynamic_sublists_with_window(
                        expanded_prices, window=window_entries
                    )
                    sublist_sums = [sum(sublist) for sublist in sublists]
                    sublist_avgs = [
                        (sum(sublist) / len(sublist)) for sublist in sublists
                    ]
                    sublist_lengths = [len(sublist) for sublist in sublists]

                    # Convert sublist durations to minutes for user-friendly display
                    sublist_durations_minutes = [
                        length * resolution_minutes for length in sublist_lengths
                    ]

                    self._attr_native_value = len(sublists)
                    self._attr_unit_of_measurement = None
                    self._attr_extra_state_attributes = {
                        "sublists": sublists,
                        "sublist_sums": sublist_sums,
                        "sublist_avgs": sublist_avgs,
                        "sublist_lengths": sublist_lengths,
                        "sublist_durations_minutes": sublist_durations_minutes,
                        "index_lists": index_lists,
                        "sublist_count": len(sublists),
                        "expanded_prices": expanded_prices,
                        "expanded_prices_length": len(expanded_prices),
                        "original_hourly_prices": nordpool_prices,
                        "nordpool_prices_length": len(nordpool_prices),
                        "window_value_hours": window_value_hours,
                        "window_value_minutes": window_value_minutes,
                        "window_entries": window_entries,
                        "time_resolution_setting": time_resolution,
                        "resolution_minutes": resolution_minutes,
                        "resolution_unit": unit_name,
                        "entries_per_hour": entries_per_hour,
                        "window_number": self._window_number,
                        "time_resolution_sensor": self._time_resolution_select,
                    }

        except (ValueError, TypeError, KeyError) as exc:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            _LOGGER.debug("Error processing sensor data: %s", exc)

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        nordpool_state = self.hass.states.get(self._nordpool_sensor)

        return nordpool_state is not None and nordpool_state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )

    @property
    def native_value(self) -> str | int | float | date | Decimal | None:
        """Return the state of the sensor."""
        return self._attr_native_value
