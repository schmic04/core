"""EMS tools for dynamic price list analysis."""

from __future__ import annotations


def minutes_to_time_index(minutes: int, resolution_minutes: int) -> int:
    """Convert minutes from midnight to time index based on resolution.

    Args:
        minutes: Minutes since midnight (0-1439)
        resolution_minutes: Time resolution in minutes (60 for hourly, 15 for quarter-hourly)

    Returns:
        Time index for the given resolution
    """
    if resolution_minutes == 60:
        # For hourly resolution: return the hour (0-23)
        # 10:30 (630 minutes) -> hour 10
        return minutes // 60
    if resolution_minutes == 15:
        # For 15-minute resolution: return the quarter-hour interval (0-95)
        # 10:30 (630 minutes) -> 630 // 15 = 42
        return minutes // 15
    # Fallback: generic calculation
    return minutes // resolution_minutes


def time_index_to_minutes(index: int, resolution_minutes: int) -> int:
    """Convert time index to minutes since midnight.

    Args:
        index: Time index
        resolution_minutes: Time resolution in minutes (60 for hourly, 15 for quarter-hourly)

    Returns:
        Minutes since midnight
    """
    return index * resolution_minutes


def get_resolution_minutes(time_resolution: str) -> int:
    """Get resolution in minutes based on time resolution setting.

    Args:
        time_resolution: "Stunde", "15-Minuten", or "Automatisch"

    Returns:
        Resolution in minutes (60 for hourly, 15 for quarter-hourly)
    """
    if time_resolution == "15-Minuten":
        return 15
    # Default to hourly for "Stunde" and "Automatisch"
    return 60


def get_max_time_index(time_resolution: str) -> int:
    """Get maximum time index for the given resolution.

    Args:
        time_resolution: "Stunde", "15-Minuten", or "Automatisch"

    Returns:
        Maximum time index (23 for hourly, 95 for quarter-hourly)
    """
    resolution_minutes = get_resolution_minutes(time_resolution)
    return (24 * 60) // resolution_minutes - 1


def convert_hours_to_minutes(hours: float) -> int:
    """Convert hours to minutes.

    Args:
        hours: Hours as float

    Returns:
        Minutes as integer
    """
    return int(hours * 60)


def convert_minutes_to_hours(minutes: int) -> float:
    """Convert minutes to hours.

    Args:
        minutes: Minutes as integer

    Returns:
        Hours as float
    """
    return minutes / 60


def is_local_maximum(price_list: list[float], index: int) -> bool:
    """Check if value at given index is a local maximum.

    Args:
        price_list: List of price values
        index: Index to check

    Returns:
        True if value at index is a local maximum
    """
    if index < 0 or index >= len(price_list):
        return False

    # For single element list
    if len(price_list) == 1:
        return True

    # First element: only check right neighbor
    if index == 0:
        return price_list[index] > price_list[index + 1]

    # Last element: only check left neighbor
    if index == len(price_list) - 1:
        return price_list[index] > price_list[index - 1]

    # Middle elements: check both neighbors
    return (
        price_list[index] > price_list[index - 1]
        and price_list[index] > price_list[index + 1]
    )


def sort_sublists_by_sum(
    sublists: list[list[float]], descending: bool = True
) -> list[list[float]]:
    """Sort sublists by their sum values.

    Args:
        sublists: List of price sublists
        descending: If True, sort in descending order (highest first)

    Returns:
        Sorted list of sublists
    """
    return sorted(sublists, key=sum, reverse=descending)


def dynamic_sublists_with_window(
    price_list: list[float], window: int = 10
) -> tuple[list[list[float]], list[list[int]]]:
    """Create dynamic sublists based on local maxima with window constraint.

    Args:
        price_list: List of price values
        window: Maximum length of each sublist

    Returns:
        Tuple of (sublists of prices, sublists of indices)
    """
    if not price_list:
        return [], []

    sublists: list[list[float]] = []
    index_lists: list[list[int]] = []
    used_indices: set[int] = set()
    overall_avg = sum(price_list) / len(price_list)

    # Find all local maxima
    local_maxima = [
        i for i in range(len(price_list)) if is_local_maximum(price_list, i)
    ]

    # If no local maxima found, use the global maximum
    if not local_maxima:
        max_index = price_list.index(max(price_list))
        local_maxima = [max_index]

    # Process each local maximum
    for peak_idx in local_maxima:
        if peak_idx in used_indices:
            continue

        # Start with the peak
        current_sublist = [price_list[peak_idx]]
        current_indices = [peak_idx]
        used_indices.add(peak_idx)

        # Calculate remaining slots after including the peak
        remaining_slots = window - 1

        # Expansion around the peak - always choose higher value
        left_idx = peak_idx - 1
        right_idx = peak_idx + 1

        while remaining_slots > 0 and (left_idx >= 0 or right_idx < len(price_list)):
            # Check if we can expand left
            can_expand_left = (
                left_idx >= 0
                and left_idx not in used_indices
                and price_list[left_idx] >= overall_avg
            )

            # Check if we can expand right
            can_expand_right = (
                right_idx < len(price_list)
                and right_idx not in used_indices
                and price_list[right_idx] >= overall_avg
            )

            # Determine which direction to expand based on higher value
            if can_expand_left and can_expand_right:
                # Both directions available - choose the higher value
                if price_list[left_idx] >= price_list[right_idx]:
                    # Expand left (higher or equal value)
                    current_sublist.insert(0, price_list[left_idx])
                    current_indices.insert(0, left_idx)
                    used_indices.add(left_idx)
                    left_idx -= 1
                    # Keep right_idx for next iteration
                else:
                    # Expand right (higher value)
                    current_sublist.append(price_list[right_idx])
                    current_indices.append(right_idx)
                    used_indices.add(right_idx)
                    right_idx += 1
                    # Keep left_idx for next iteration
                remaining_slots -= 1

            elif can_expand_left:
                # Only left expansion possible
                current_sublist.insert(0, price_list[left_idx])
                current_indices.insert(0, left_idx)
                used_indices.add(left_idx)
                left_idx -= 1
                remaining_slots -= 1

            elif can_expand_right:
                # Only right expansion possible
                current_sublist.append(price_list[right_idx])
                current_indices.append(right_idx)
                used_indices.add(right_idx)
                right_idx += 1
                remaining_slots -= 1

            else:
                # No more expansion possible
                break

        # Add sublist if it has at least one element
        if current_sublist:
            sublists.append(current_sublist)
            index_lists.append(current_indices)

    return sublists, index_lists
