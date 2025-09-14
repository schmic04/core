"""EMS Balcony Solar binary sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_HOURS_OF_OPERATING,
    CONF_NORDPOOL_SENSOR,
    CREATE_HOURS_NUMBER_ENTITY,
    DEFAULT_HOURS_OF_OPERATING,
    DOMAIN,
    ENTITY_NAME_CURRENT_TIME_OPTIMAL,
    ENTITY_SUFFIX_CURRENT_TIME_OPTIMAL,
    ENTITY_SUFFIX_EPEX_PRICE_SUBLISTS,
    ENTITY_SUFFIX_HOURS_OF_OPERATING,
    ENTITY_SUFFIX_TIME_RESOLUTION,
    MINUTES_PER_QUARTER_HOUR,
    TIME_RESOLUTION_DEFAULT,
    get_entity_id,
    get_entity_unique_id,
)
from .ems_tools import (
    convert_hours_to_minutes,
    convert_minutes_to_hours,
    get_resolution_minutes,
    minutes_to_time_index,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up EMS Balcony Solar binary sensors from a config entry."""
    nordpool_sensor = entry.data[CONF_NORDPOOL_SENSOR]

    sensors = [
        EmsBalconySolarBinarySensor(entry.entry_id, nordpool_sensor),
    ]

    async_add_entities(sensors)


class EmsBalconySolarBinarySensor(BinarySensorEntity):
    """Binary sensor that indicates if current time is in optimal sublists."""

    _attr_has_entity_name = True

    def __init__(self, config_entry_id: str, nordpool_sensor: str) -> None:
        """Initialize the binary sensor."""
        self._nordpool_sensor = nordpool_sensor
        self._attr_name = ENTITY_NAME_CURRENT_TIME_OPTIMAL
        self._attr_unique_id = get_entity_unique_id(
            config_entry_id, ENTITY_SUFFIX_CURRENT_TIME_OPTIMAL
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry_id)},
            name="EMS Balcony Solar",
            manufacturer="EMS",
            model="Balcony Solar",
        )
        self._unsubscribe_callbacks: list[Callable[[], None]] = []

        # Generate entity IDs using consistent schema
        self._hours_of_operating_number = get_entity_id(
            "number", ENTITY_SUFFIX_HOURS_OF_OPERATING
        )
        self._time_resolution_select = get_entity_id(
            "select", ENTITY_SUFFIX_TIME_RESOLUTION
        )

    def _get_hours_of_operating_value(self) -> int:
        """Get the hours of operating value from number entity or external sensor or default."""
        # Get config entry to check hours configuration
        config_entry = None
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_NORDPOOL_SENSOR) == self._nordpool_sensor:
                config_entry = entry
                break

        if not config_entry:
            return DEFAULT_HOURS_OF_OPERATING

        hours_config = config_entry.data.get(CONF_HOURS_OF_OPERATING)

        # Determine which entity to check based on config
        if not hours_config or hours_config == CREATE_HOURS_NUMBER_ENTITY:
            # Use integration number entity
            hours_entity_id = self._hours_of_operating_number
        else:
            # Use external entity specified in config
            hours_entity_id = hours_config

        hours_state = self.hass.states.get(hours_entity_id)

        if not hours_state or hours_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return DEFAULT_HOURS_OF_OPERATING

        try:
            hours_value = int(float(hours_state.state))
            return max(1, hours_value)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "Invalid hours of operating number value: %s", hours_state.state
            )
            return DEFAULT_HOURS_OF_OPERATING

    def _get_time_resolution_setting(self) -> str:
        """Get the current time resolution setting from select entity."""
        select_state = self.hass.states.get(self._time_resolution_select)

        if not select_state or select_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return TIME_RESOLUTION_DEFAULT

        return select_state.state

    def _get_num_price_sublists_sensor(self) -> str:
        """Get the entity ID for the num_price_sublists sensor created by this integration."""
        return get_entity_id("sensor", ENTITY_SUFFIX_EPEX_PRICE_SUBLISTS)

    def _get_current_time_index(self) -> int:
        """Get the current time index based on resolution setting."""
        now = dt_util.now()
        current_minutes = now.hour * 60 + now.minute

        time_resolution = self._get_time_resolution_setting()
        resolution_minutes = get_resolution_minutes(time_resolution)

        return minutes_to_time_index(current_minutes, resolution_minutes)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Get the num_price_sublists sensor ID
        num_sublists_sensor_id = self._get_num_price_sublists_sensor()

        # Build list of entities to track
        entities_to_track = [
            num_sublists_sensor_id,
            self._time_resolution_select,
        ]

        # Add the appropriate hours_of_operating entity based on config
        config_entry = None
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_NORDPOOL_SENSOR) == self._nordpool_sensor:
                config_entry = entry
                break

        if config_entry:
            hours_config = config_entry.data.get(CONF_HOURS_OF_OPERATING)
            if not hours_config or hours_config == CREATE_HOURS_NUMBER_ENTITY:
                # Use integration number entity
                entities_to_track.append(self._hours_of_operating_number)
            else:
                # Use external entity specified in config
                entities_to_track.append(hours_config)
        else:
            # Fallback to integration number entity
            entities_to_track.append(self._hours_of_operating_number)

        # Track state changes of all relevant sensors
        self._unsubscribe_callbacks.append(
            async_track_state_change_event(
                self.hass,
                entities_to_track,
                self._handle_sensor_state_change,
            )
        )

        # Track time changes based on resolution
        await self._setup_time_tracking()
        await self._update_state()

    async def _setup_time_tracking(self) -> None:
        """Set up time tracking based on current resolution."""
        time_resolution = self._get_time_resolution_setting()
        resolution_minutes = get_resolution_minutes(time_resolution)

        if resolution_minutes == MINUTES_PER_QUARTER_HOUR:
            # Update every 15 minutes
            self._unsubscribe_callbacks.append(
                async_track_time_change(
                    self.hass,
                    self._handle_time_change,
                    minute=[0, 15, 30, 45],
                    second=0,
                )
            )
        else:
            # Update every hour
            self._unsubscribe_callbacks.append(
                async_track_time_change(
                    self.hass,
                    self._handle_time_change,
                    minute=0,
                    second=0,
                )
            )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        for unsubscribe in self._unsubscribe_callbacks:
            unsubscribe()

    @callback
    def _handle_sensor_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle state changes of the input sensors."""
        # If time resolution changed, we need to re-setup time tracking
        if event.data["entity_id"] == self._time_resolution_select:
            _LOGGER.debug("Time resolution changed, re-initializing time tracking")
            # Remove existing callbacks and re-add with new resolution
            for unsubscribe in self._unsubscribe_callbacks:
                unsubscribe()
            self._unsubscribe_callbacks.clear()

            # Re-setup tracking with new resolution
            self.hass.async_create_task(self.async_added_to_hass())
            return

        self.hass.async_create_task(self._update_state())

    @callback
    def _handle_time_change(self, now: datetime) -> None:
        """Handle time changes."""
        self.hass.async_create_task(self._update_state())

    async def _update_state(self) -> None:
        """Update the binary sensor state."""
        # Get the num_price_sublists sensor state
        num_sublists_sensor_id = self._get_num_price_sublists_sensor()
        num_sublists_state = self.hass.states.get(num_sublists_sensor_id)

        if not num_sublists_state or num_sublists_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            self._attr_is_on = False
            self._attr_extra_state_attributes = {
                "current_time_index": self._get_current_time_index(),
                "current_time_minutes": dt_util.now().hour * 60 + dt_util.now().minute,
                "optimal_indices": [],
                "hours_of_operating_setting": self._get_hours_of_operating_value(),
                "time_resolution_setting": self._get_time_resolution_setting(),
                "error": "num_price_sublists sensor unavailable",
                "num_sublists_sensor": num_sublists_sensor_id,
            }
            self.async_write_ha_state()
            return

        try:
            # Get attributes from the num_price_sublists sensor
            sublist_sums = num_sublists_state.attributes.get("sublist_sums", [])
            index_lists = num_sublists_state.attributes.get("index_lists", [])

            if not sublist_sums or not index_lists:
                self._attr_is_on = False
                self._attr_extra_state_attributes = {
                    "current_time_index": self._get_current_time_index(),
                    "current_time_minutes": dt_util.now().hour * 60
                    + dt_util.now().minute,
                    "optimal_indices": [],
                    "hours_of_operating_setting": self._get_hours_of_operating_value(),
                    "time_resolution_setting": self._get_time_resolution_setting(),
                    "error": "no sublist data available",
                    "num_sublists_sensor": num_sublists_sensor_id,
                }
                self.async_write_ha_state()
                return

            # Use index lists directly - they already match the current time resolution
            # No conversion needed as the sensor provides the correct resolution

            # Create list of (sum, index_list) pairs and sort by sum (descending for highest prices)
            sum_index_pairs = list(zip(sublist_sums, index_lists, strict=False))
            sum_index_pairs.sort(key=lambda x: x[0], reverse=True)

            # Get hours of operating and convert to minutes for calculations
            hours_of_operating = self._get_hours_of_operating_value()
            hours_of_operating_minutes = convert_hours_to_minutes(hours_of_operating)

            time_resolution = self._get_time_resolution_setting()
            resolution_minutes = get_resolution_minutes(time_resolution)

            # Convert target duration from minutes to number of time entries
            target_entries = hours_of_operating_minutes // resolution_minutes
            target_entries = max(1, target_entries)  # Ensure at least 1 entry

            best_sublists: list[tuple[float, list[int]]] = []
            total_entries = 0

            for sum_value, index_list in sum_index_pairs:
                sublist_entries = len(index_list)

                # If adding this sublist would exceed the limit, check if we should still add it
                if total_entries + sublist_entries > target_entries:
                    # If we haven't selected any sublists yet, or if this would be the first to exceed,
                    # add it anyway as specified in requirements
                    if not best_sublists or total_entries < target_entries:
                        best_sublists.append((sum_value, index_list))
                        total_entries += sublist_entries
                    break
                # Safe to add without exceeding limit
                best_sublists.append((sum_value, index_list))
                total_entries += sublist_entries

                # If we've reached the exact target, stop
                if total_entries >= target_entries:
                    break

            # Get all indices from the selected sublists
            optimal_indices = []
            for _, index_list in best_sublists:
                optimal_indices.extend(index_list)

            # Remove duplicates and sort
            optimal_indices = sorted(set(optimal_indices))

            # Check if current time index is in optimal indices
            current_time_index = self._get_current_time_index()
            current_time_minutes = dt_util.now().hour * 60 + dt_util.now().minute
            self._attr_is_on = current_time_index in optimal_indices

            # Convert total entries back to minutes and hours for display
            total_duration_minutes = total_entries * resolution_minutes
            total_duration_hours = convert_minutes_to_hours(total_duration_minutes)

            self._attr_extra_state_attributes = {
                "current_time_index": current_time_index,
                "current_time_minutes": current_time_minutes,
                "optimal_indices": optimal_indices,
                "hours_of_operating_setting": hours_of_operating,
                "hours_of_operating_minutes": hours_of_operating_minutes,
                "time_resolution_setting": time_resolution,
                "resolution_minutes": resolution_minutes,
                "target_entries": target_entries,
                "total_entries": total_entries,
                "total_duration_minutes": total_duration_minutes,
                "total_duration_hours": total_duration_hours,
                "best_sublist_sums": [pair[0] for pair in best_sublists],
                "best_sublist_indices": [pair[1] for pair in best_sublists],
                "best_sublist_durations_entries": [
                    len(pair[1]) for pair in best_sublists
                ],
                "best_sublist_durations_minutes": [
                    len(pair[1]) * resolution_minutes for pair in best_sublists
                ],
                "selected_sublists_count": len(best_sublists),
                "total_sublists_available": len(sublist_sums),
                "index_lists_sample": index_lists[:3] if index_lists else [],
                "num_sublists_sensor": num_sublists_sensor_id,
                "hours_of_operating_number": self._hours_of_operating_number,
                "time_resolution_sensor": self._time_resolution_select,
            }

        except (ValueError, TypeError, KeyError) as exc:
            self._attr_is_on = False
            self._attr_extra_state_attributes = {
                "current_time_index": self._get_current_time_index(),
                "current_time_minutes": dt_util.now().hour * 60 + dt_util.now().minute,
                "optimal_indices": [],
                "hours_of_operating_setting": self._get_hours_of_operating_value(),
                "time_resolution_setting": self._get_time_resolution_setting(),
                "error": f"Error processing data: {exc!s}",
                "num_sublists_sensor": num_sublists_sensor_id,
            }
            _LOGGER.debug("Error processing binary sensor data: %s", exc)

        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        num_sublists_sensor_id = self._get_num_price_sublists_sensor()
        num_sublists_state = self.hass.states.get(num_sublists_sensor_id)

        return num_sublists_state is not None and num_sublists_state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if current time is in optimal time windows."""
        return self._attr_is_on
