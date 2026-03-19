"""
utils/aqi_calculator.py – US-EPA AQI computation from raw pollutant values
"""

from typing import Dict, Optional, Tuple
from config import AQI_BREAKPOINTS, AQI_CATEGORIES


def _linear(aqi_hi, aqi_lo, conc_hi, conc_lo, conc) -> int:
    """EPA linear interpolation formula."""
    return round(((aqi_hi - aqi_lo) / (conc_hi - conc_lo)) * (conc - conc_lo) + aqi_lo)


def pollutant_to_aqi(pollutant: str, concentration: float) -> Optional[int]:
    """
    Convert a single pollutant concentration to its sub-AQI value.

    Args:
        pollutant:     One of PM2.5, PM10, CO, NO2, O3, CO2
        concentration: Measured value in the pollutant's unit

    Returns:
        Integer sub-AQI, or None if out-of-range / unknown pollutant.
    """
    breakpoints = AQI_BREAKPOINTS.get(pollutant)
    if not breakpoints:
        return None

    for (conc_lo, conc_hi, aqi_lo, aqi_hi) in breakpoints:
        if conc_lo <= concentration <= conc_hi:
            return _linear(aqi_hi, aqi_lo, conc_hi, conc_lo, concentration)

    # If above highest range, cap at 500
    if concentration > breakpoints[-1][1]:
        return 500
    return None


def compute_aqi(readings: Dict[str, float]) -> Tuple[int, str, str, Dict[str, int]]:
    """
    Compute the overall AQI from a dict of pollutant readings.

    Args:
        readings: e.g. {"PM2.5": 35.2, "PM10": 65.0, "CO": 3.5, ...}

    Returns:
        (overall_aqi, category_label, hex_color, sub_aqis_dict)
    """
    sub_aqis: Dict[str, int] = {}
    for pollutant, concentration in readings.items():
        val = pollutant_to_aqi(pollutant, concentration)
        if val is not None:
            sub_aqis[pollutant] = val

    if not sub_aqis:
        return (0, "Unknown", "#AAAAAA", {})

    overall = max(sub_aqis.values())

    for (lo, hi, label, color, _) in AQI_CATEGORIES:
        if lo <= overall <= hi:
            return (overall, label, color, sub_aqis)

    return (overall, "Hazardous", "#7E0023", sub_aqis)


def get_aqi_category(aqi: int) -> Tuple[str, str, str]:
    """Return (label, hex_color, description) for a given AQI value."""
    for (lo, hi, label, color, desc) in AQI_CATEGORIES:
        if lo <= aqi <= hi:
            return label, color, desc
    return "Hazardous", "#7E0023", "Emergency conditions."


def health_recommendation(aqi: int) -> str:
    """Generate a human-readable health advisory for an AQI value."""
    if aqi <= 50:
        return "Air quality is good. Enjoy outdoor activities freely."
    elif aqi <= 100:
        return ("Air quality is acceptable. Unusually sensitive individuals should "
                "consider limiting prolonged outdoor exertion.")
    elif aqi <= 150:
        return ("Sensitive groups (elderly, children, asthma patients) should reduce "
                "prolonged outdoor exertion. Others can continue normally.")
    elif aqi <= 200:
        return ("Everyone should reduce prolonged or heavy outdoor exertion. "
                "Wear an N95 mask outdoors. Sensitive groups should stay inside.")
    elif aqi <= 300:
        return ("Health alert! Everyone should avoid prolonged outdoor exertion. "
                "Stay indoors with windows closed. Use air purifiers.")
    else:
        return ("HAZARDOUS – Emergency conditions. Stay indoors, seal windows/doors, "
                "avoid all outdoor activity. Seek medical attention if symptoms develop.")
