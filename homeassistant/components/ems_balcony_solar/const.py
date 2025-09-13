"""Constants for the EMS Balcony Solar integration."""

DOMAIN = "ems_balcony_solar"

# Configuration
CONF_NORDPOOL_SENSOR = "nordpool_sensor"
CONF_HOURS_OF_OPERATING = "hours_of_operating"
CREATE_HOURS_NUMBER_ENTITY = "create_hours_number_entity"

# Defaults
DEFAULT_WINDOW = 5
DEFAULT_HOURS_OF_OPERATING = 10

# Time resolution options
TIME_RESOLUTION_HOURLY = "hourly"
TIME_RESOLUTION_15_MINUTES = "15_minutes"
TIME_RESOLUTION_OPTIONS = [TIME_RESOLUTION_HOURLY, TIME_RESOLUTION_15_MINUTES]
TIME_RESOLUTION_DEFAULT = TIME_RESOLUTION_HOURLY

# Time constants
MINUTES_PER_HOUR = 60
MINUTES_PER_QUARTER_HOUR = 15

# Entity unique ID suffixes (integration-only, no external sensor reference)
ENTITY_SUFFIX_WINDOW_SIZE = "window_size"
ENTITY_SUFFIX_HOURS_OF_OPERATING = "hours_of_operating"
ENTITY_SUFFIX_TIME_RESOLUTION = "time_resolution"
ENTITY_SUFFIX_PRICE_AVG = "price_avg"
ENTITY_SUFFIX_PRICE_LIST_LENGTH = "price_list_length"
ENTITY_SUFFIX_EPEX_PRICE_SUBLISTS = "epex_price_sublists"
ENTITY_SUFFIX_CURRENT_TIME_OPTIMAL = "current_time_optimal"

# Entity names (user-facing)
ENTITY_NAME_WINDOW_SIZE = "Window size"
ENTITY_NAME_HOURS_OF_OPERATING = "Hours of operating"
ENTITY_NAME_TIME_RESOLUTION = "Time resolution"
ENTITY_NAME_PRICE_AVG = "Price average"
ENTITY_NAME_PRICE_LIST_LENGTH = "Price list length"
ENTITY_NAME_EPEX_PRICE_SUBLISTS = "EPEX price sublists"
ENTITY_NAME_CURRENT_TIME_OPTIMAL = "Current time optimal"


def get_entity_unique_id(config_entry_id: str, suffix: str) -> str:
    """Generate consistent unique ID for entities.

    Args:
        config_entry_id: Config entry ID for uniqueness across multiple instances
        suffix: Entity suffix from ENTITY_SUFFIX_* constants

    Returns:
        Unique ID in format: {DOMAIN}_{config_entry_id}_{suffix}
    """
    return f"{DOMAIN}_{config_entry_id}_{suffix}"


def get_entity_id(platform: str, suffix: str) -> str:
    """Generate consistent entity ID for entities.

    Args:
        platform: Platform name (number, select, sensor, binary_sensor)
        suffix: Entity suffix from ENTITY_SUFFIX_* constants

    Returns:
        Entity ID in format: {platform}.{DOMAIN}_{suffix}
    """
    return f"{platform}.{DOMAIN}_{suffix}"
