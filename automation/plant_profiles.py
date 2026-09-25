"""
Botanical Species Knowledge Base & Agronomic Rule Presets
Defines optimal hydrological and thermal envelopes for various agricultural cultivars.
"""

from typing import Dict, Any, List

PLANT_PROFILES: Dict[str, Dict[str, Any]] = {
    "Succulents": {
        "species_name": "Succulents & Cacti (Xerophytic)",
        "moisture_threshold_min": 20.0,
        "moisture_threshold_max": 35.0,
        "pump_duration_seconds": 4.0,
        "cooldown_minutes": 120.0,
        "temperature_optimal_min": 18.0,
        "temperature_optimal_max": 32.0,
        "humidity_optimal_min": 20.0,
        "humidity_optimal_max": 45.0,
        "description": "Requires deep dry-downs to avert root rot. Irrigation is conservative and heavily throttled."
    },
    "Tropical Foliage": {
        "species_name": "Tropical Foliage (Monstera / Ficus)",
        "moisture_threshold_min": 50.0,
        "moisture_threshold_max": 75.0,
        "pump_duration_seconds": 6.0,
        "cooldown_minutes": 25.0,
        "temperature_optimal_min": 20.0,
        "temperature_optimal_max": 29.0,
        "humidity_optimal_min": 55.0,
        "humidity_optimal_max": 85.0,
        "description": "Consistent sub-surface moisture required. Low tolerance for persistent drought."
    },
    "Vegetables/Tomatoes": {
        "species_name": "Vegetables & Tomatoes (Solanaceae)",
        "moisture_threshold_min": 40.0,
        "moisture_threshold_max": 65.0,
        "pump_duration_seconds": 7.0,
        "cooldown_minutes": 35.0,
        "temperature_optimal_min": 18.0,
        "temperature_optimal_max": 30.0,
        "humidity_optimal_min": 40.0,
        "humidity_optimal_max": 70.0,
        "description": "Active transpiration demands moderate moisture replenishment with strict hysteresis."
    },
    "Culinary Herbs": {
        "species_name": "Culinary Herbs (Basil / Mint / Rosemary)",
        "moisture_threshold_min": 35.0,
        "moisture_threshold_max": 55.0,
        "pump_duration_seconds": 5.0,
        "cooldown_minutes": 30.0,
        "temperature_optimal_min": 17.0,
        "temperature_optimal_max": 27.0,
        "humidity_optimal_min": 40.0,
        "humidity_optimal_max": 65.0,
        "description": "Balanced soil moisture with responsive aeration cycles."
    }
}


def get_profile(name: str) -> Dict[str, Any]:
    """Retrieve profile by name with graceful fallback to Tropical Foliage."""
    return PLANT_PROFILES.get(name, PLANT_PROFILES["Tropical Foliage"])


def list_profiles() -> List[Dict[str, Any]]:
    """Return all catalogued plant profiles formatted for frontend display."""
    return [
        {"key": k, **v} for k, v in PLANT_PROFILES.items()
    ]
