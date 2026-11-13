import os
import math
import time
from datetime import datetime, timezone

import gradio as gr
import requests


# ============================================================
# MARS: THE LAST FRONTIER
# Full backend - Gradio (Render deployment)
# ============================================================

APP_NAME = "MARS: THE LAST FRONTIER"
NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")

REQUEST_TIMEOUT = 15
CACHE_TTL = 900
INSIGHT_CACHE_TTL = 6 * 3600  # InSight data is historical
CACHE = {}

NASA_INSIGHT_URL = "https://api.nasa.gov/insight_weather/"
NASA_PDS_SEARCH_URL = "https://pds.nasa.gov/api/search/1/products"

NASA_MARS_FACTSHEET_URL = (
    "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html"
)
PDS_SOURCE_URL = "https://pds.nasa.gov/"
CRISM_SOURCE_URL = (
    "https://pds-geosciences.wustl.edu/missions/mro/crism.htm"
)
RADIATION_SOURCE_URL = (
    "https://science.nasa.gov/resource/radiation-measurements-on-mars/"
)

BASE_LATITUDE_DEG = -4.5895
BASE_LONGITUDE_DEG = 137.4417

USER_AGENT = "MarsLastFrontier-StudentProject/2.0"


# ============================================================
# COMMON HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def cached_get_json(url, params=None, cache_key=None, ttl=None):
    key = cache_key or (url + repr(sorted((params or {}).items())))
    now = time.time()
    ttl = CACHE_TTL if ttl is None else ttl

    cached = CACHE.get(key)
    if cached and now - cached["time"] < ttl:
        return cached["data"], True

    try:
        response = requests.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        # Upstream failed: reuse the last good (stale) response if any
        if cached:
            return cached["data"], True
        raise

    CACHE[key] = {"time": now, "data": data}
    return data, False


def safe_float(value):
    try:
        if value is None:
            return None
        result = float(value)
        if not math.isfinite(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def clamp(value, minimum=0, maximum=100):
    value = safe_float(value)
    if value is None:
        return float(minimum)
    return max(minimum, min(maximum, value))


def json_error(source, exc):
    return {
        "status": "unavailable",
        "source": source,
        "error_type": type(exc).__name__,
        "generated_at_utc": utc_now(),
        "notice": "Source unavailable. No measurement was invented.",
    }


# ============================================================
# 1. ATMOSPHERE REFERENCE
# ============================================================

def get_atmosphere():
    return {
        "CO2": {"value": 95.1, "unit": "%"},
        "N2": {"value": 2.59, "unit": "%"},
        "Ar": {"value": 1.94, "unit": "%"},
        "O2": {"value": 0.16, "unit": "%"},
        "CO": {"value": 0.06, "unit": "%"},
        "source": "NASA Mars Fact Sheet",
        "source_url": NASA_MARS_FACTSHEET_URL,
        "data_type": "approximate_reference",
        "is_live": False,
        "notice": (
            "Approximate atmospheric composition reference; "
            "not a live local measurement."
        ),
    }


# ============================================================
# 2. HISTORICAL ENVIRONMENT
# ============================================================

def get_mars_environment():
    try:
        data, cache_used = cached_get_json(
            NASA_INSIGHT_URL,
            params={
                "api_key": NASA_API_KEY,
                "feedtype": "json",
                "ver": "1.0",
            },
            cache_key="nasa_insight_weather",
            ttl=INSIGHT_CACHE_TTL,
        )

        sols = data.get("sol_keys", [])
        if not sols:
            raise ValueError("No sol observations returned")

        sol = str(sols[-1])
        record = data.get(sol, {})

        at = record.get("AT", {})
        pre = record.get("PRE", {})
        hws = record.get("HWS", {})
        wd = record.get("WD", {})

        direction = (
            wd.get("most_common")
            or wd.get("most_common_direction")
        )
        if isinstance(direction, dict):
            direction_label = direction.get("compass_point")
            direction_degrees = safe_float(
                direction.get("compass_degrees")
            )
        else:
            direction_label = direction
            direction_degrees = None

        return {
            "status": "success",
            "source": "NASA InSight Mars Weather API",
            "data_type": "historical_observation",
            "is_live": False,
            "cache_used": cache_used,
            "sol": sol,
            "temperature": {
                "average_c": safe_float(at.get("av")),
                "minimum_c": safe_float(at.get("mn")),
                "maximum_c": safe_float(at.get("mx")),
            },
            "pressure": {
                "average_pa": safe_float(pre.get("av")),
                "unit": "Pa",
            },
            "wind": {
                "speed_m_s": safe_float(hws.get("av")),
                "direction": direction_label,
                "direction_degrees": direction_degrees,
            },
            "notice": (
                "Historical observation, not live Mars weather. "
                "Use the sol and original source metadata to interpret it."
            ),
        }

    except Exception as exc:
        return {
            "status": "reference_fallback",
            "source": "Published Mars mission observations",
            "data_type": "general_reference_not_local_live_data",
            "is_live": False,
            "temperature": {
                "average_c": None,
                "minimum_c": None,
                "maximum_c": None,
            },
            "pressure": {
                "average_pa": None,
                "unit": "Pa",
            },
            "wind": {
                "speed_m_s": None,
                "direction": None,
                "direction_degrees": None,
            },
            "fallback_reason": type(exc).__name__,
            "fallback_detail": str(exc)[:300],
            "notice": (
                "InSight weather retrieval failed. Weather values remain "
                "null rather than substituting unrelated measurements."
            ),
        }


# ============================================================
# 3. RADIATION
# ============================================================

def get_mars_radiation():
    dose_rate_ugy_day = 314.0
    dose_equivalent_usv_day = 720.0

    return {
        "status": "success",
        "source": "Curiosity Radiation Assessment Detector (RAD)",
        "source_url": RADIATION_SOURCE_URL,
        "archive_source": "NASA Planetary Data System",
        "archive_url": PDS_SOURCE_URL,
        "instrument": "Curiosity RAD",
        "mission_location": "Gale Crater, Mars",
        "data_type": "published_historical_measurement_reference",
        "is_live": False,
        "observation_period": {
            "start": "2019-11-28",
            "end": "2020-10-03",
        },
        "radiation": {
            "dose_rate_uGy_day": dose_rate_ugy_day,
            "dose_rate_unit": "microgray/day",
            "dose_rate_mGy_day": dose_rate_ugy_day / 1000.0,
            "dose_equivalent_rate_uSv_day": dose_equivalent_usv_day,
            "dose_equivalent_unit": "microsievert/day",
            "dose_equivalent_rate_mSv_day": (
                dose_equivalent_usv_day / 1000.0
            ),
            "radiation_level": "historical_reference",
            "particle_flux": None,
        },
        "uncertainty": {
            "dose_rate_mGy_day": None,
            "dose_equivalent_rate_mSv_day": None,
            "notice": (
                "The values above are rounded published averages. "
                "This API does not attach an uncertainty estimate to "
                "these rounded values."
            ),
        },
        "notice": (
            "Historical published averages from the specified observation "
            "period, not a current measurement at the game base. Radiation "
            "varies with solar conditions, atmosphere, location, shielding "
            "and observation period. Particle flux is not supplied here."
        ),
    }


# ============================================================
# 4. SOLAR GEOMETRY
# ============================================================

def julian_day(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    dt = dt.astimezone(timezone.utc)
    year = dt.year
    month = dt.month

    day_fraction = (
        dt.hour
        + dt.minute / 60.0
        + dt.second / 3600.0
        + dt.microsecond / 3.6e9
    ) / 24.0

    day = dt.day + day_fraction

    if month <= 2:
        year -= 1
        month += 12

    a = year // 100
    b = 2 - a + a // 4

    return (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + day + b - 1524.5
    )


def solar_position_mars(dt):
    """Approximate Mars solar position (Allison & McEwen 2000 / Mars24)."""
    jd = julian_day(dt)
    d = jd - 2451545.0

    mean_anomaly_deg = (19.3871 + 0.52402073 * d) % 360
    mean_anomaly = math.radians(mean_anomaly_deg)
    alpha_fms = 270.3863 + 0.52403840 * d

    # Planetary perturbations (small corrections)
    pbs_terms = (
        (0.0071, 2.2353, 49.409),
        (0.0057, 2.7543, 168.173),
        (0.0039, 1.1177, 191.837),
        (0.0037, 15.7866, 21.736),
        (0.0021, 2.1354, 15.704),
        (0.0020, 2.4694, 95.528),
        (0.0018, 32.8493, 49.095),
    )
    pbs = sum(
        amp * math.cos(math.radians(0.985626 * d / tau + phase))
        for amp, tau, phase in pbs_terms
    )

    # Equation of center (true anomaly minus mean anomaly), degrees
    equation_of_center = (
        (10.691 + 3.0e-7 * d) * math.sin(mean_anomaly)
        + 0.623 * math.sin(2 * mean_anomaly)
        + 0.050 * math.sin(3 * mean_anomaly)
        + 0.005 * math.sin(4 * mean_anomaly)
        + 0.0005 * math.sin(5 * mean_anomaly)
        + pbs
    )

    # Areocentric solar longitude Ls (0 = northern spring equinox)
    ls_deg = (alpha_fms + equation_of_center) % 360
    ls = math.radians(ls_deg)

    # Solar declination (degrees)
    declination_deg = (
        math.degrees(math.asin(0.42565 * math.sin(ls)))
        + 0.25 * math.sin(ls)
    )

    # Equation of time (Mars solar hours)
    eot_deg = (
        2.861 * math.sin(2 * ls)
        - 0.071 * math.sin(4 * ls)
        + 0.002 * math.sin(6 * ls)
        - equation_of_center
    )
    equation_of_time_hours = eot_deg / 15.0

    # Sun distance from Kepler's equation
    eccentricity = 0.0934
    semi_major_axis_au = 1.523679
    eccentric_anomaly = mean_anomaly
    for _ in range(8):
        eccentric_anomaly -= (
            eccentric_anomaly
            - eccentricity * math.sin(eccentric_anomaly)
            - mean_anomaly
        ) / (
            1 - eccentricity * math.cos(eccentric_anomaly)
        )
    radius_au = semi_major_axis_au * (
        1 - eccentricity * math.cos(eccentric_anomaly)
    )

    solar_constant_earth = 1361.0
    top_of_atmosphere_irradiance = (
        solar_constant_earth / (radius_au ** 2)
    )

    return {
        "julian_day": jd,
        "solar_longitude_ls_deg": ls_deg,
        "solar_declination_deg": declination_deg,
        "equation_of_time_hours": equation_of_time_hours,
        "mars_sun_distance_au": radius_au,
        "top_of_atmosphere_irradiance_w_m2": (
            top_of_atmosphere_irradiance
        ),
    }


def solar_time_string(hour_float):
    hour_float %= 24.0
    hour = int(hour_float)
    minute = int((hour_float - hour) * 60)
    return f"{hour:02d}:{minute:02d}"


def get_mars_solar(
    latitude_deg=BASE_LATITUDE_DEG,
    longitude_deg=BASE_LONGITUDE_DEG,
    date_utc=None,
):
    try:
        latitude_deg = float(latitude_deg)
        longitude_deg = float(longitude_deg)

        if not -90 <= latitude_deg <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        if not -180 <= longitude_deg <= 180:
            raise ValueError("Longitude must be between -180 and 180")

        if date_utc:
            dt = datetime.fromisoformat(
                str(date_utc).replace("Z", "+00:00")
            )
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        else:
            dt = datetime.now(timezone.utc)

        position = solar_position_mars(dt)

        latitude = math.radians(latitude_deg)
        declination = math.radians(
            position["solar_declination_deg"]
        )

        altitude_deg = -0.27
        altitude = math.radians(altitude_deg)

        denominator = math.cos(latitude) * math.cos(declination)

        if abs(denominator) < 1e-12:
            cos_hour_angle = 2.0
        else:
            cos_hour_angle = (
                math.sin(altitude)
                - math.sin(latitude) * math.sin(declination)
            ) / denominator

        daylight_mars_hours = None

        if cos_hour_angle >= 1:
            daylight_hours = 0.0
            daylight_mars_hours = 0.0
            sunrise = None
            sunset = None
            day_status = "polar_night_or_no_sunrise"
        elif cos_hour_angle <= -1:
            daylight_hours = 24.6597
            daylight_mars_hours = 24.0
            sunrise = None
            sunset = None
            day_status = "continuous_daylight"
        else:
            hour_angle_deg = math.degrees(
                math.acos(cos_hour_angle)
            )

            mars_solar_day_hours = 24.6597
            # Earth hours (kept for game rules / compatibility)
            daylight_hours = (
                mars_solar_day_hours * hour_angle_deg / 180.0
            )
            # Mars solar hours (24 per sol), local true solar time
            daylight_mars_hours = hour_angle_deg / 7.5

            sunrise = solar_time_string(12.0 - daylight_mars_hours / 2.0)
            sunset = solar_time_string(12.0 + daylight_mars_hours / 2.0)
            day_status = "calculated"

        return {
            "status": "success",
            "source": "Approximate Mars orbital solar calculation",
            "data_type": "calculated_astronomical_estimate",
            "is_live": False,
            "calculation_time_utc": dt.isoformat(),
            "location": {
                "latitude_deg": latitude_deg,
                "longitude_deg": longitude_deg,
                "reference_location": (
                    "Gale Crater reference location"
                    if (
                        latitude_deg == BASE_LATITUDE_DEG
                        and longitude_deg == BASE_LONGITUDE_DEG
                    )
                    else "User-supplied coordinates"
                ),
            },
            "sunrise": sunrise,
            "sunset": sunset,
            "day_length_hours": round(daylight_hours, 3),
            "day_length_mars_solar_hours": round(daylight_mars_hours, 3),
            "time_basis": (
                "sunrise/sunset are local true solar time in Mars solar "
                "hours (24 per sol); day_length_hours is in Earth hours"
            ),
            "solar_longitude_ls_deg": round(
                position["solar_longitude_ls_deg"], 2
            ),
            "equation_of_time_hours": round(
                position["equation_of_time_hours"], 4
            ),
            "solar_declination_deg": round(
                position["solar_declination_deg"], 3
            ),
            "mars_sun_distance_au": round(
                position["mars_sun_distance_au"], 6
            ),
            "solar_radiation": {
                "value": None,
                "unit": "W/m2",
                "reason": (
                    "Surface irradiance requires atmospheric opacity, "
                    "dust, terrain, solar elevation and/or validated "
                    "surface measurements."
                ),
            },
            "top_of_atmosphere_solar_irradiance": {
                "value": round(
                    position["top_of_atmosphere_irradiance_w_m2"], 2
                ),
                "unit": "W/m2",
                "data_type": "theoretical_atmosphere_top_estimate",
            },
            "day_status": day_status,
            "notice": (
                "Approximate astronomical calculations only. Sunrise, "
                "sunset and daylight are not mission-ephemeris products. "
                "Top-of-atmosphere irradiance is not surface irradiance."
            ),
        }

    except Exception as exc:
        return {
            "status": "error",
            "data_type": "unavailable",
            "error_type": type(exc).__name__,
            "solar_radiation": {"value": None, "unit": "W/m2"},
            "sunrise": None,
            "sunset": None,
            "day_length_hours": None,
            "notice": "Solar calculation failed; values remain unavailable.",
        }


# ============================================================
# 5. UNDERGROUND MINERAL API
# ============================================================

MINERAL_CATALOG = [
    {
        "mineral": "Hematite",
        "formula": "Fe2O3",
        "research_context": "Iron oxide mineral",
        "depth_m": None,
        "abundance": None,
        "resource_reserve": None,
        "game_resource_value": None,
        "data_type": "research_target",
    },
    {
        "mineral": "Gypsum",
        "formula": "CaSO4·2H2O",
        "research_context": "Hydrated calcium sulfate",
        "depth_m": None,
        "abundance": None,
        "resource_reserve": None,
        "game_resource_value": None,
        "data_type": "research_target",
    },
    {
        "mineral": "Olivine",
        "formula": "(Mg,Fe)2SiO4",
        "research_context": "Silicate mineral",
        "depth_m": None,
        "abundance": None,
        "resource_reserve": None,
        "game_resource_value": None,
        "data_type": "research_target",
    },
    {
        "mineral": "Clay minerals",
        "formula": None,
        "research_context": "Hydrated phyllosilicates",
        "depth_m": None,
        "abundance": None,
        "resource_reserve": None,
        "game_resource_value": None,
        "data_type": "research_target",
    },
    {
        "mineral": "Pyroxene",
        "formula": None,
        "research_context": "Silicate mineral group",
        "depth_m": None,
        "abundance": None,
        "resource_reserve": None,
        "game_resource_value": None,
        "data_type": "research_target",
    },
]


def extract_pds_products(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("data", "results", "items", "products"):
        if isinstance(payload.get(key), list):
            return payload[key]

    hits = payload.get("hits")
    if isinstance(hits, dict) and isinstance(hits.get("hits"), list):
        return [
            item.get("_source", item)
            if isinstance(item, dict) else item
            for item in hits["hits"]
        ]

    return []


def first_value(record, keys):
    if not isinstance(record, dict):
        return None

    for key in keys:
        value = record.get(key)
        if value is not None:
            if isinstance(value, list):
                return value[0] if value else None
            return value

    return None


def normalize_pds_product(product):
    if not isinstance(product, dict):
        return {
            "raw_result": str(product)[:500],
            "notice": "PDS returned an unrecognized product format.",
        }

    return {
        "title": first_value(
            product,
            [
                "title",
                "pds:Identification_Area.pds:title",
                "product_title",
            ],
        ),
        "identifier": first_value(
            product,
            [
                "lid",
                "logical_identifier",
                "pds:Identification_Area.pds:logical_identifier",
                "id",
            ],
        ),
        "description": first_value(
            product,
            [
                "description",
                "pds:Identification_Area.pds:description",
            ],
        ),
        "source": "NASA Planetary Data System",
        "source_url": PDS_SOURCE_URL,
        "data_type": "archived_product_metadata",
        "is_live": False,
        "mineral_presence_confirmed": False,
        "underground_depth_m": None,
        "mineral_abundance": None,
        "resource_reserve": None,
        "notice": (
            "Archive metadata is not proof of a mineral deposit, "
            "underground depth, abundance, or extractable reserve."
        ),
    }


def search_nasa_mineral_products(keywords="Mars CRISM mineral", limit=10):
    keywords = str(keywords or "Mars CRISM mineral").strip()[:120]

    try:
        limit = max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        limit = 10

    if not keywords:
        keywords = "Mars CRISM mineral"

    try:
        payload, cache_used = cached_get_json(
            NASA_PDS_SEARCH_URL,
            params={
                "keywords": keywords,
                "limit": limit,
            },
            cache_key=f"pds:{keywords}:{limit}",
        )

        products = extract_pds_products(payload)
        normalized = [
            normalize_pds_product(p)
            for p in products[:limit]
        ]

        return {
            "status": "success" if normalized else "no_results",
            "query": keywords,
            "result_count": len(normalized),
            "products": normalized,
            "cache_used": cache_used,
            "source": "NASA PDS Search API",
            "source_url": PDS_SOURCE_URL,
            "data_type": "archived_product_metadata",
            "is_live": False,
            "underground_deposit_confirmed": False,
            "generated_at_utc": utc_now(),
            "notice": (
                "Inspect each returned product and its spatial coverage. "
                "An empty result does not prove no data exists."
            ),
        }

    except Exception as exc:
        return {
            "status": "error",
            "query": keywords,
            "result_count": 0,
            "products": [],
            "source": "NASA PDS Search API",
            "source_url": PDS_SOURCE_URL,
            "error_type": type(exc).__name__,
            "data_type": "unavailable",
            "is_live": False,
            "notice": (
                "PDS search failed. Check the service logs and the archive "
                "service. No mineral location or reserve was fabricated."
            ),
        }


def get_underground_minerals():
    result = search_nasa_mineral_products(
        "Mars CRISM mineral",
        10,
    )
    result["module"] = "Underground Mineral API"
    result["catalog"] = MINERAL_CATALOG
    result["crism_source_url"] = CRISM_SOURCE_URL
    return result


def get_minerals_by_location(location):
    location = str(location or "").strip()[:100]

    if not location:
        return {
            "status": "invalid_input",
            "products": [],
            "notice": "Enter a Mars feature name.",
        }

    result = search_nasa_mineral_products(
        f"Mars {location} mineral CRISM",
        10,
    )
    result["location_query"] = location
    result["spatial_match_verified"] = False
    result["notice"] = (
        "This is a text metadata search. Check the product footprint "
        "before treating a result as covering the requested location."
    )
    return result


def get_mineral_catalog():
    return {
        "status": "success",
        "catalog": MINERAL_CATALOG,
        "count": len(MINERAL_CATALOG),
        "data_type": "research_target_catalog",
        "source_url": PDS_SOURCE_URL,
        "crism_source_url": CRISM_SOURCE_URL,
        "notice": (
            "Catalog entries are research targets, not verified deposits. "
            "Depth, abundance, reserve and game resource values remain null."
        ),
    }


# ============================================================
# 6. FARMING
# ============================================================

def get_farming(
    heating_on=False,
    grow_lights_on=False,
    latitude_deg=BASE_LATITUDE_DEG,
    longitude_deg=BASE_LONGITUDE_DEG,
):
    environment = get_mars_environment()
    solar = get_mars_solar(latitude_deg, longitude_deg)

    temp = environment.get("temperature", {}).get("average_c")
    daylight = solar.get("day_length_hours")

    heating_recommendation = (
        None if temp is None else temp < 18
    )

    grow_lights_recommendation = (
        None if daylight is None else daylight < 12
    )

    heating_units = 15 if bool(heating_on) else 0
    light_units = 10 if bool(grow_lights_on) else 0

    return {
        "temperature_c": temp,
        "day_length_hours": daylight,
        "sunrise": solar.get("sunrise"),
        "sunset": solar.get("sunset"),
        "solar_radiation_w_m2": None,
        "recommendations": {
            "heating": heating_recommendation,
            "grow_lights": grow_lights_recommendation,
        },
        "player_decisions": {
            "heating_on": bool(heating_on),
            "grow_lights_on": bool(grow_lights_on),
        },
        "power_consumption": {
            "heating_units": heating_units,
            "grow_lights_units": light_units,
            "total_units": heating_units + light_units,
        },
        "notice": (
            "Heating threshold, daylight threshold and power consumption "
            "are game mechanics. Surface solar irradiance is not connected."
        ),
    }


# ============================================================
# 6b. CROP LIGHT / PPFD TARGETS (educational + game)
# ============================================================

CROP_LIGHT_STAGES = {
    "seedling": {
        "stage": "seedling",
        "ppfd_min": 100,
        "ppfd_max": 150,
        "unit": "umol/m2/s",
        "note": "Low intensity for fragile shoots.",
    },
    "vegetative": {
        "stage": "vegetative",
        "ppfd_min": 250,
        "ppfd_max": 400,
        "unit": "umol/m2/s",
        "note": "Moderate-to-high intensity for stems and foliage.",
    },
    "flowering": {
        "stage": "flowering",
        "ppfd_min": 500,
        "ppfd_max": 800,
        "unit": "umol/m2/s",
        "note": "High intensity for fruiting crops (e.g. tomato).",
    },
}


def get_farm_light(
    stage="vegetative",
    lamp_ppfd=300,
    latitude_deg=None,
    longitude_deg=None,
):
    stage_key = str(stage or "vegetative").strip().lower()
    if stage_key not in CROP_LIGHT_STAGES:
        stage_key = "vegetative"

    target = CROP_LIGHT_STAGES[stage_key]
    lamp_ppfd = clamp(lamp_ppfd, 0, 1000)

    lat = BASE_LATITUDE_DEG if latitude_deg is None else latitude_deg
    lon = BASE_LONGITUDE_DEG if longitude_deg is None else longitude_deg
    solar = get_mars_solar(lat, lon)
    daylight = solar.get("day_length_hours")

    if lamp_ppfd < target["ppfd_min"]:
        light_fit = "too_low"
        growth_multiplier = 0.35
    elif lamp_ppfd > target["ppfd_max"]:
        light_fit = "too_high"
        growth_multiplier = 0.5
    else:
        light_fit = "optimal"
        growth_multiplier = 1.0

    if daylight is not None and daylight < 12:
        day_factor = 1.0
        lights_needed = True
    elif daylight is not None:
        day_factor = 0.85
        lights_needed = False
    else:
        day_factor = 1.0
        lights_needed = None

    return {
        "status": "success",
        "module": "FarmLight",
        "data_type": "educational_crop_target_plus_game_model",
        "is_live": False,
        "stage": target,
        "all_stages": CROP_LIGHT_STAGES,
        "player_lamp_ppfd": lamp_ppfd,
        "light_fit": light_fit,
        "growth_multiplier": round(growth_multiplier * day_factor, 3),
        "day_length_hours": daylight,
        "sunrise": solar.get("sunrise"),
        "sunset": solar.get("sunset"),
        "grow_lights_needed_game_rule": lights_needed,
        "source_note": (
            "PPFD bands are general controlled-environment teaching targets "
            "(seedling / vegetative / flowering). They are not measured "
            "Mars surface photosynthetic photon flux density."
        ),
        "notice": (
            "Use stage targets for the in-game light slider. "
            "Day length comes from calculated solar geometry when available. "
            "Not a live greenhouse sensor feed."
        ),
    }


# ============================================================
# 7. BUNKER
# ============================================================

def get_bunker(shielding=0, integrity=100):
    shielding = clamp(shielding)
    integrity = clamp(integrity)

    environment = get_mars_environment()
    wind = environment.get("wind", {}).get("speed_m_s")
    pressure = environment.get("pressure", {}).get("average_pa")

    wind_risk = None if wind is None else min(100, wind * 5)
    pressure_risk = (
        None if pressure is None else min(100, abs(pressure - 636) / 10)
    )

    risks = [
        value for value in (wind_risk, pressure_risk)
        if value is not None
    ]

    overall = None
    if risks:
        overall = max(
            0,
            sum(risks) - shielding * 0.3 - integrity * 0.2,
        )

    radiation = get_mars_radiation()

    return {
        "BunkerShielding": shielding,
        "HabitatIntegrity": integrity,
        "wind_risk_game_score": wind_risk,
        "pressure_risk_game_score": pressure_risk,
        "overall_risk_game_score": overall,
        "radiation": {
            "status": radiation["status"],
            "dose_rate_uGy_day": (
                radiation["radiation"]["dose_rate_uGy_day"]
            ),
            "dose_equivalent_rate_uSv_day": (
                radiation["radiation"]["dose_equivalent_rate_uSv_day"]
            ),
            "data_type": radiation["data_type"],
            "is_live": False,
            "notice": (
                "Historical Gale Crater reference, not a live measurement "
                "at this fictional bunker."
            ),
        },
        "notice": (
            "Wind, pressure and overall risk values are fictional game "
            "scores, not an engineering safety assessment. The radiation "
            "reference is not a measurement of bunker interior conditions."
        ),
    }


# ============================================================
# 8. COMBINED RESPONSE
# ============================================================

def get_all_mars_data(
    shielding=0,
    integrity=100,
    heating_on=False,
    grow_lights_on=False,
    farm_stage="vegetative",
    lamp_ppfd=300,
):
    return {
        "game": APP_NAME,
        "generated_at_utc": utc_now(),
        "atmosphere": get_atmosphere(),
        "environment": get_mars_environment(),
        "radiation": get_mars_radiation(),
        "solar": get_mars_solar(),
        "farming": get_farming(
            heating_on=heating_on,
            grow_lights_on=grow_lights_on,
        ),
        "farm_light": get_farm_light(
            stage=farm_stage,
            lamp_ppfd=lamp_ppfd,
        ),
        "bunker": get_bunker(shielding, integrity),
        "underground_minerals": get_underground_minerals(),
        "data_integrity": {
            "historical_data_labelled": True,
            "reference_data_labelled": True,
            "simulated_data_labelled": True,
            "missing_data_is_null": True,
            "live_data_claimed": False,
            "radiation_has_published_reference": True,
            "solar_is_calculated_not_measured": True,
            "mineral_metadata_is_not_a_deposit": True,
            "ppfd_targets_are_educational_not_mars_surface": True,
        },
    }


# ============================================================
# 9. API FUNCTIONS
# ============================================================

def api_health():
    return {
        "status": "ok",
        "game": APP_NAME,
        "generated_at_utc": utc_now(),
        "modules": [
            "atmosphere",
            "environment",
            "radiation",
            "solar",
            "farming",
            "farm_light",
            "bunker",
            "minerals",
        ],
    }


def api_atmosphere():
    return get_atmosphere()


def api_environment():
    return get_mars_environment()


def api_radiation():
    return get_mars_radiation()


def api_solar(latitude_deg, longitude_deg, date_utc):
    return get_mars_solar(latitude_deg, longitude_deg, date_utc)


def api_farming(heating_on, grow_lights_on):
    return get_farming(heating_on, grow_lights_on)


def api_farm_light(stage, lamp_ppfd):
    return get_farm_light(stage=stage, lamp_ppfd=lamp_ppfd)


def api_bunker(shielding, integrity):
    return get_bunker(shielding, integrity)


def api_all(
    shielding,
    integrity,
    heating_on,
    grow_lights_on,
    farm_stage,
    lamp_ppfd,
):
    return get_all_mars_data(
        shielding,
        integrity,
        heating_on,
        grow_lights_on,
        farm_stage,
        lamp_ppfd,
    )


def api_minerals():
    return get_underground_minerals()


def api_mineral_catalog():
    return get_mineral_catalog()


def api_minerals_location(location):
    return get_minerals_by_location(location)


def api_minerals_search(keywords, limit):
    return search_nasa_mineral_products(keywords, limit)


# ============================================================
# 10. GRADIO UI
# ============================================================

with gr.Blocks(title=APP_NAME) as demo:
    gr.Markdown(
        f"""
# 🚀 {APP_NAME}

NASA science-data backend with Radiation, Solar, Farming, Farm Light (PPFD),
Bunker and Underground Minerals.

**Data rules:** historical is not live; calculated is not measured;
PPFD stage bands are educational targets, not Mars surface measurements;
fictional game scores are not real engineering assessments.
"""
    )

    with gr.Tab("Dashboard"):
        health_button = gr.Button("Check Backend")
        health_output = gr.JSON(label="Health")
        health_button.click(
            api_health, inputs=[], outputs=health_output,
            api_name="health",
        )

        with gr.Row():
            all_shielding = gr.Slider(
                0, 100, value=0, step=1, label="BunkerShielding"
            )
            all_integrity = gr.Slider(
                0, 100, value=100, step=1, label="HabitatIntegrity"
            )

        all_heating = gr.Checkbox(value=False, label="Heating On")
        all_lights = gr.Checkbox(value=False, label="Grow Lights On")
        all_stage = gr.Dropdown(
            choices=["seedling", "vegetative", "flowering"],
            value="vegetative",
            label="Farm Stage",
        )
        all_ppfd = gr.Slider(
            0, 1000, value=300, step=10, label="Lamp PPFD"
        )
        all_button = gr.Button("Load All Mars Data")
        all_output = gr.JSON(label="Combined Data")

        all_button.click(
            api_all,
            inputs=[
                all_shielding,
                all_integrity,
                all_heating,
                all_lights,
                all_stage,
                all_ppfd,
            ],
            outputs=all_output,
            api_name="mars_data",
        )

    with gr.Tab("Radiation"):
        gr.Markdown(
            """
## Curiosity RAD historical reference

This module returns published historical radiation measurements.
It is not a live radiation sensor or a measurement inside your bunker.
"""
        )
        rad_button = gr.Button("Get Radiation Reference")
        rad_output = gr.JSON(label="Radiation Data")
        rad_button.click(
            api_radiation, inputs=[], outputs=rad_output,
            api_name="radiation",
        )

    with gr.Tab("Environment"):
        env_button = gr.Button("Get Environment")
        env_output = gr.JSON(label="Environment")
        env_button.click(
            api_environment, inputs=[], outputs=env_output,
            api_name="environment",
        )

        atmosphere_button = gr.Button("Get Atmosphere")
        atmosphere_output = gr.JSON(label="Atmosphere")
        atmosphere_button.click(
            api_atmosphere, inputs=[], outputs=atmosphere_output,
            api_name="atmosphere",
        )

    with gr.Tab("Solar"):
        solar_lat = gr.Number(
            value=BASE_LATITUDE_DEG,
            label="Latitude (degrees)",
        )
        solar_lon = gr.Number(
            value=BASE_LONGITUDE_DEG,
            label="Longitude (degrees)",
        )
        solar_date = gr.Textbox(
            value="",
            label="UTC date/time (optional)",
            placeholder="2026-11-06T00:00:00Z; leave blank for now",
        )
        solar_button = gr.Button("Calculate Mars Solar Geometry")
        solar_output = gr.JSON(label="Solar Geometry")

        solar_button.click(
            api_solar,
            inputs=[solar_lat, solar_lon, solar_date],
            outputs=solar_output,
            api_name="solar",
        )

    with gr.Tab("Farming"):
        farm_heating = gr.Checkbox(value=False, label="Heating On")
        farm_lights = gr.Checkbox(value=False, label="Grow Lights On")
        farm_button = gr.Button("Calculate Farming State")
        farm_output = gr.JSON(label="Farming")
        farm_button.click(
            api_farming,
            inputs=[farm_heating, farm_lights],
            outputs=farm_output,
            api_name="farming",
        )

        gr.Markdown(
            """
## Farm light / PPFD targets

Educational controlled-environment PPFD bands for seedling, vegetative
and flowering stages. Not measured Mars surface PPFD.
"""
        )
        farm_stage = gr.Dropdown(
            choices=["seedling", "vegetative", "flowering"],
            value="vegetative",
            label="Growth Stage",
        )
        farm_ppfd = gr.Slider(
            0, 1000, value=300, step=10, label="Lamp PPFD (umol/m2/s)"
        )
        farm_light_btn = gr.Button("Get Farm Light Targets")
        farm_light_out = gr.JSON(label="Farm Light")
        farm_light_btn.click(
            api_farm_light,
            inputs=[farm_stage, farm_ppfd],
            outputs=farm_light_out,
            api_name="farm_light",
        )

    with gr.Tab("Bunker"):
        bunker_shielding = gr.Slider(
            0, 100, value=0, step=1, label="BunkerShielding"
        )
        bunker_integrity = gr.Slider(
            0, 100, value=100, step=1, label="HabitatIntegrity"
        )
        bunker_button = gr.Button("Calculate Bunker State")
        bunker_output = gr.JSON(label="Bunker")
        bunker_button.click(
            api_bunker,
            inputs=[bunker_shielding, bunker_integrity],
            outputs=bunker_output,
            api_name="bunker",
        )

    with gr.Tab("Underground Minerals"):
        gr.Markdown(
            """
## NASA PDS mineral archive search

Returned records are archive product metadata, not verified
underground mineral deposits or extractable reserves.
"""
        )

        minerals_button = gr.Button("Search Default Mineral Products")
        minerals_output = gr.JSON(label="Mineral Products")
        minerals_button.click(
            api_minerals, inputs=[], outputs=minerals_output,
            api_name="minerals",
        )

        mineral_keywords = gr.Textbox(
            value="Mars CRISM mineral",
            label="Search Keywords",
        )
        mineral_limit = gr.Slider(
            1, 25, value=10, step=1, label="Maximum Results"
        )
        mineral_search_button = gr.Button("Search NASA PDS")
        mineral_search_output = gr.JSON(label="PDS Search Results")
        mineral_search_button.click(
            api_minerals_search,
            inputs=[mineral_keywords, mineral_limit],
            outputs=mineral_search_output,
            api_name="minerals_search",
        )

        mineral_location = gr.Textbox(
            label="Mars Feature Name",
            placeholder="e.g. Gale Crater",
        )
        mineral_location_button = gr.Button("Search Location Metadata")
        mineral_location_output = gr.JSON(label="Location Results")
        mineral_location_button.click(
            api_minerals_location,
            inputs=[mineral_location],
            outputs=mineral_location_output,
            api_name="minerals_location",
        )

        catalog_button = gr.Button("Show Mineral Catalog")
        catalog_output = gr.JSON(label="Research Target Catalog")
        catalog_button.click(
            api_mineral_catalog, inputs=[], outputs=catalog_output,
            api_name="minerals_catalog",
        )


demo.queue()
demo.launch(
    server_name="0.0.0.0",
    server_port=int(os.getenv("PORT", 7860)),
)
