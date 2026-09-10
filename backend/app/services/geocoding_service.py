import requests
from typing import Optional, Tuple
from app.utils.logger import logger

class GeocodingService:
    def __init__(self):
        self.base_url = "https://nominatim.openstreetmap.org/search"
        self.reverse_url = "https://nominatim.openstreetmap.org/reverse"

    def geocode(self, place_name: str) -> Optional[Tuple[float, float]]:
        """Convert a place name into (latitude, longitude). Returns None if not found."""
        try:
            params = {"q": place_name, "format": "json", "limit": 1}
            headers = {"User-Agent": "Call-Astro/1.0"}
            response = requests.get(self.base_url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                results = response.json()
                if results:
                    lat = float(results[0]["lat"])
                    lon = float(results[0]["lon"])
                    logger.info(f"Geocoded '{place_name}' -> ({lat}, {lon})")
                    return lat, lon
            logger.warning(f"Geocoding failed for '{place_name}': no results")
            return None
        except Exception as e:
            logger.error(f"Geocoding error for '{place_name}': {e}")
            return None

    def reverse_geocode(self, latitude: float, longitude: float) -> Optional[str]:
        """Convert (lat, lon) into a short, human-readable place label, e.g.
        'Guntakal, Andhra Pradesh'. Used to replace raw coordinates in the
        calendar's location display. Returns None if the lookup fails —
        callers should fall back to a generic label, never raw numbers
        pretending to be a place name."""
        try:
            params = {
                "lat": latitude,
                "lon": longitude,
                "format": "json",
                "zoom": 10,
                "addressdetails": 1,
            }
            headers = {"User-Agent": "Call-Astro/1.0"}
            response = requests.get(self.reverse_url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                result = response.json()
                address = result.get("address", {}) or {}
                city = (
                    address.get("city") or address.get("town") or address.get("village")
                    or address.get("municipality") or address.get("county")
                )
                state = address.get("state")
                parts = [p for p in [city, state] if p]
                if parts:
                    label = ", ".join(parts)
                    logger.info(f"Reverse geocoded ({latitude},{longitude}) -> {label}")
                    return label
                display_name = result.get("display_name")
                if display_name:
                    return display_name.split(",")[0].strip()
            logger.warning(f"Reverse geocoding failed for ({latitude},{longitude}): no results")
            return None
        except Exception as e:
            logger.error(f"Reverse geocoding error for ({latitude},{longitude}): {e}")
            return None

geocoding_service = GeocodingService()