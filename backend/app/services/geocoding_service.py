import requests
from typing import Optional, Tuple
from app.utils.logger import logger

class GeocodingService:
    def __init__(self):
        self.base_url = "https://nominatim.openstreetmap.org/search"

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

geocoding_service = GeocodingService()