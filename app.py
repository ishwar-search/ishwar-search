import os
import re
import json
import html
import time
import hmac
import logging
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_from_directory
)

# ============================================================
# ISHWAR SEARCH - PROFESSIONAL BACKEND
# ============================================================

APP_NAME = "Ishwar Search"
OWNER_NAME = "Ishwar Ghanchi"
APP_VERSION = "7.0.0"

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

SERVICES_FILE = BASE_DIR / "service.json"

DATA_DIR = Path(
    os.environ.get("DATA_DIR", str(BASE_DIR))
)

DATA_DIR.mkdir(parents=True, exist_ok=True)

STATS_FILE = DATA_DIR / "search_stats.json"
PUSH_DATA_FILE = DATA_DIR / "push_subscriptions.json"

HTTP_TIMEOUT = 10
MAX_QUERY_LENGTH = 250
MAX_REQUEST_SIZE = 1024 * 1024

NEWS_CACHE_SECONDS = 300
IMAGE_CACHE_SECONDS = 600
PLACE_CACHE_SECONDS = 600

MAX_NEWS_ITEMS = 30

USER_AGENT = (
    "IshwarSearch/7.0 "
    "(https://ishwar-search.onrender.com)"
)

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_SIZE
app.config["JSON_AS_ASCII"] = False

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("ishwar-search")


# ============================================================
# BASIC HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]*>", " ", value)

    return re.sub(r"\s+", " ", value).strip()


def normalize_text(value):
    value = clean_text(value).casefold()
    value = value.replace("&", " and ")

    value = re.sub(
        r"[^\w\s]",
        " ",
        value,
        flags=re.UNICODE
    )

    return re.sub(r"\s+", " ", value).strip()


def safe_url(value):
    if not value:
        return ""

    try:
        parsed = urllib.parse.urlparse(
            str(value).strip()
        )

        if parsed.scheme not in ("http", "https"):
            return ""

        if not parsed.hostname:
            return ""

        if parsed.username or parsed.password:
            return ""

        return str(value).strip()

    except (ValueError, TypeError):
        return ""


def json_error(message, status=400):
    return jsonify({
        "success": False,
        "error": message,
        "time": utc_now()
    }), status


def bounded_limit(value, default=20, maximum=50):
    try:
        value = int(value)
    except (ValueError, TypeError):
        value = default

    return max(1, min(value, maximum))


def fetch_url(url, timeout=HTTP_TIMEOUT):
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid URL scheme")

    if not parsed.hostname:
        raise ValueError("Invalid hostname")

    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/json, application/xml, "
                "text/xml, text/plain, */*"
            )
        }
    )

    with urllib.request.urlopen(
        req,
        timeout=timeout
    ) as response:

        raw = response.read(
            5 * 1024 * 1024 + 1
        )

        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Response too large")

        charset = (
            response.headers.get_content_charset()
            or "utf-8"
        )

        return raw.decode(
            charset,
            errors="replace"
        )


def get_request_query():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}

        if not isinstance(payload, dict):
            return "", 20

        query = clean_text(
            payload.get("q")
            or payload.get("query")
            or ""
        )

        limit = payload.get("limit", 20)

    else:
        query = clean_text(
            request.args.get("q", "")
        )

        limit = request.args.get("limit", 20)

    return query, bounded_limit(limit, 20, 100)


# ============================================================
# SIMPLE CACHE
# ============================================================

_cache = {}
_cache_lock = threading.RLock()


def cache_get(key, max_age=300):
    with _cache_lock:
        item = _cache.get(key)

        if item is None:
            return None

        created, value = item

        if time.time() - created > max_age:
            _cache.pop(key, None)
            return None

        return value


def cache_set(key, value):
    with _cache_lock:
        _cache[key] = (
            time.time(),
            value
        )

        if len(_cache) > 400:
            oldest = sorted(
                _cache,
                key=lambda key: _cache[key][0]
            )[:100]

            for key in oldest:
                _cache.pop(key, None)


# ============================================================
# SERVICE DIRECTORY
# service.json is the main website catalogue.
# ============================================================

def load_services():
    if not SERVICES_FILE.is_file():
        logger.warning("service.json not found")
        return []

    try:
        with SERVICES_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if isinstance(data, dict):
            data = data.get("services", [])

        if not isinstance(data, list):
            logger.error("service.json must contain a list")
            return []

        results = []
        seen = set()

        for item in data:
            if not isinstance(item, dict):
                continue

            name = clean_text(
                item.get("name")
                or item.get("title")
                or item.get("label")
            )

            url = safe_url(
                item.get("url")
                or item.get("link")
            )

            if not name or not url:
                continue

            key = url.rstrip("/").casefold()

            if key in seen:
                continue

            seen.add(key)

            keywords = item.get("keywords", [])

            if isinstance(keywords, list):
                keywords = " ".join(
                    str(word) for word in keywords
                )

            category = clean_text(
                item.get("category") or "General"
            )

            results.append({
                "name": name,
                "title": name,
                "url": url,
                "link": url,
                "category": category,
                "description": clean_text(
                    item.get("description", "")
                ),
                "keywords": clean_text(keywords),
                "type": clean_text(
                    item.get("type", "External")
                )
            })

        return results

    except (OSError, json.JSONDecodeError):
        logger.exception("service.json could not be loaded")
        return []


# ============================================================
# SEARCH SYNONYMS - HINDI + ENGLISH
# ============================================================

SEARCH_SYNONYMS = {
    "railway": [
        "rrb", "rail", "रेलवे", "रेल", "ट्रेन"
    ],

    "rrb": [
        "railway", "रेलवे", "रेल भर्ती"
    ],

    "job": [
        "jobs", "recruitment", "vacancy",
        "नौकरी", "भर्ती", "रोजगार"
    ],

    "jobs": [
        "job", "recruitment", "vacancy",
        "नौकरी", "भर्ती", "रोजगार"
    ],

    "result": [
        "results", "रिजल्ट", "परिणाम", "नतीजा"
    ],

    "results": [
        "result", "रिजल्ट", "परिणाम"
    ],

    "scholarship": [
        "छात्रवृत्ति", "स्कॉलरशिप", "छात्र"
    ],

    "aadhaar": [
        "aadhar", "आधार", "uidai"
    ],

    "aadhar": [
        "aadhaar", "आधार", "uidai"
    ],

    "weather": [
        "मौसम", "तापमान", "बारिश"
    ],

    "gold": [
        "सोना", "gold rate"
    ],

    "silver": [
        "चांदी", "चाँदी", "silver rate"
    ],

    "news": [
        "खबर", "समाचार", "ताजा खबर"
    ],

    "cyber": [
        "cybercrime", "साइबर", "फ्रॉड", "fraud"
    ],

    "hospital": [
        "अस्पताल", "clinic", "चिकित्सालय"
    ],

    "police": [
        "पुलिस", "थाना", "constable"
    ],

    "education": [
        "शिक्षा", "पढ़ाई", "study"
    ],

    "exam": [
        "परीक्षा", "test", "एग्जाम"
    ],

    "iti": [
        "industrial training institute",
        "आईटीआई",
        "ncvt",
        "scvt"
    ],

    "bank": [
        "banking", "बैंक", "ibps", "sbi", "rbi"
    ],

    "army": [
        "सेना", "defence", "agniveer"
    ],

    "rajasthan": [
        "राजस्थान", "raj"
    ],

    "photo": [
        "image", "images", "फोटो", "तस्वीर"
    ],

    "video": [
        "वीडियो", "clips"
    ],

    "document": [
        "दस्तावेज", "कागजात", "certificate"
    ],

    "scheme": [
        "योजना", "सरकारी योजना", "yojana"
    ]
}


def expand_search_words(query):
    words = normalize_text(query).split()

    expanded = list(words)

    for word in words:
        for synonym in SEARCH_SYNONYMS.get(word, []):
            normalized = normalize_text(synonym)

            if normalized and normalized not in expanded:
                expanded.append(normalized)

    return expanded


# ============================================================
# SEARCH ENGINE
# ============================================================

def search_services(query, limit=30):
    query = clean_text(query)

    normalized_query = normalize_text(query)

    if not normalized_query:
        return []

    query_words = normalized_query.split()

    expanded_words = expand_search_words(
        normalized_query
    )

    matches = []

    for service in load_services():

        name = normalize_text(service["name"])
        description = normalize_text(
            service["description"]
        )

        category = normalize_text(
            service["category"]
        )

        keywords = normalize_text(
            service["keywords"]
        )

        searchable = " ".join([
            name,
            description,
            category,
            keywords
        ])

        score = 0

        if normalized_query == name:
            score += 150

        elif normalized_query in name:
            score += 90

        if normalized_query in keywords:
            score += 65

        if normalized_query in category:
            score += 35

        if normalized_query in description:
            score += 25

        matched = sum(
            1 for word in query_words
            if word in searchable
        )

        if query_words and matched == len(query_words):
            score += 45

        elif matched:
            score += matched * 7

        for word in query_words:
            if word in name:
                score += 18

            elif word in keywords:
                score += 9

            elif word in category:
                score += 5

            elif word in description:
                score += 3

        for word in expanded_words:
            if word in query_words or len(word) < 3:
                continue

            if word in name:
                score += 7

            elif word in keywords:
                score += 5

            elif word in category:
                score += 2

        if score > 0:
            result = dict(service)

            result["score"] = score

            matches.append(result)

    matches.sort(
        key=lambda item: (
            -item["score"],
            item["name"].casefold()
        )
    )

    return matches[
        :bounded_limit(limit, 30, 100)
    ]


# ============================================================
# SEARCH SUGGESTIONS
# ============================================================

def get_search_suggestions(query, limit=8):
    query = normalize_text(query)

    if len(query) < 2:
        return []

    results = []

    for service in load_services():

        name = normalize_text(service["name"])
        keywords = normalize_text(
            service["keywords"]
        )

        if (
            query in name
            or query in keywords
        ):
            results.append({
                "text": service["name"],
                "name": service["name"],
                "category": service["category"],
                "url": service["url"]
            })

    results.sort(
        key=lambda item: item["name"].casefold()
    )

    return results[
        :bounded_limit(limit, 8, 20)
    ]


# ============================================================
# SEARCH ANALYTICS
# ============================================================

_trending_searches = Counter()
_trending_lock = threading.RLock()


def load_search_stats():
    try:
        if STATS_FILE.exists():
            with STATS_FILE.open(
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            if isinstance(data, dict):
                for query, count in data.items():
                    if isinstance(query, str):
                        if isinstance(count, int):
                            _trending_searches[query] = max(
                                0,
                                count
                            )

    except (OSError, json.JSONDecodeError):
        logger.exception("Search stats load failed")


def save_search_stats():
    try:
        DATA_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        temp_file = STATS_FILE.with_suffix(".tmp")

        with temp_file.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                dict(
                    _trending_searches.most_common(500)
                ),
                file,
                ensure_ascii=False,
                indent=2
            )

            file.flush()
            os.fsync(file.fileno())

        os.replace(
            temp_file,
            STATS_FILE
        )

    except OSError:
        logger.exception("Search stats save failed")


def record_search(query):
    normalized = normalize_text(query)

    if not normalized:
        return

    with _trending_lock:

        _trending_searches[normalized] += 1

        if len(_trending_searches) > 500:
            keep = _trending_searches.most_common(300)

            _trending_searches.clear()
            _trending_searches.update(dict(keep))

        save_search_stats()


def get_trending_searches(limit=10):
    with _trending_lock:
        results = _trending_searches.most_common(
            bounded_limit(limit, 10, 30)
        )

    return [
        {
            "query": query,
            "search_count": count
        }
        for query, count in results
    ]


load_search_stats()
# ============================================================
# NEWS RSS SYSTEM
# ============================================================

NEWS_FEEDS = [
    {
        "name": "Google News Hindi",
        "url": "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"
    },
    {
        "name": "Google News India",
        "url": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
    },
    {
        "name": "BBC Hindi",
        "url": "https://feeds.bbci.co.uk/hindi/rss.xml"
    }
]

_news_cache = []
_news_cache_time = 0
_news_lock = threading.RLock()


def get_xml_text(element, names):
    for child in list(element):
        tag = child.tag.split("}")[-1].lower()

        if tag in names:
            return "".join(
                child.itertext()
            ).strip()

    return ""


def extract_news_items(xml_text, source_name):
    root = ET.fromstring(xml_text)

    results = []

    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()

        if tag not in ("item", "entry"):
            continue

        title = clean_text(
            get_xml_text(node, {"title"})
        )

        description = clean_text(
            get_xml_text(
                node,
                {"description", "summary", "content", "encoded"}
            )
        )

        published = clean_text(
            get_xml_text(
                node,
                {"pubdate", "published", "updated", "date"}
            )
        )

        link = safe_url(
            get_xml_text(node, {"link"})
        )

        if not link:
            for child in list(node):
                if child.tag.split("}")[-1].lower() == "link":
                    link = safe_url(
                        child.attrib.get("href", "")
                    )

                    if link:
                        break

        if title and link:
            results.append({
                "title": title,
                "name": title,
                "description": description[:1000],
                "url": link,
                "link": link,
                "source": source_name,
                "published": published
            })

    return results


def fetch_news(query="", force_refresh=False):
    global _news_cache, _news_cache_time

    now = time.time()

    with _news_lock:

        cache_valid = (
            bool(_news_cache)
            and now - _news_cache_time < NEWS_CACHE_SECONDS
        )

        if cache_valid and not force_refresh:
            all_news = list(_news_cache)

        else:
            all_news = []

            for feed in NEWS_FEEDS:
                try:
                    xml_text = fetch_url(
                        feed["url"],
                        timeout=8
                    )

                    all_news.extend(
                        extract_news_items(
                            xml_text,
                            feed["name"]
                        )
                    )

                except Exception as error:
                    logger.warning(
                        "News feed failed %s: %s",
                        feed["name"],
                        error
                    )

            unique = []
            seen = set()

            for item in all_news:
                key = item["url"].rstrip("/").casefold()

                if key not in seen:
                    seen.add(key)
                    unique.append(item)

            all_news = unique

            _news_cache = list(unique)
            _news_cache_time = now

    words = normalize_text(query).split()

    if words:
        filtered = []

        for item in all_news:
            searchable = normalize_text(
                item["title"] + " " +
                item["description"] + " " +
                item["source"]
            )

            if all(
                word in searchable
                for word in words
            ):
                filtered.append(item)

        return filtered[:MAX_NEWS_ITEMS]

    return all_news[:MAX_NEWS_ITEMS]


# ============================================================
# WEATHER - OPEN METEO
# ============================================================

def get_location_details(place):
    place = clean_text(place)

    if not place:
        return None

    key = "geocode:" + normalize_text(place)

    cached = cache_get(key, 3600)

    if cached is not None:
        return cached

    params = urllib.parse.urlencode({
        "name": place,
        "count": 5,
        "language": "en",
        "format": "json",
        "countryCode": "IN"
    })

    url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        + params
    )

    try:
        data = json.loads(
            fetch_url(url, timeout=8)
        )

        results = data.get("results", [])

        if not results:
            cache_set(key, None)
            return None

        candidates = [
            item for item in results
            if item.get("country_code") == "IN"
        ] or results

        location = candidates[0]

        cache_set(key, location)

        return location

    except Exception as error:
        logger.warning(
            "Geocoding error: %s",
            error
        )

        return None


def weather_description(code):
    descriptions = {
        0: "साफ आसमान",
        1: "मुख्यतः साफ",
        2: "कुछ बादल",
        3: "बादल छाए हुए",
        45: "कोहरा",
        48: "घना कोहरा",
        51: "हल्की बूंदाबांदी",
        53: "बूंदाबांदी",
        55: "तेज बूंदाबांदी",
        61: "हल्की बारिश",
        63: "बारिश",
        65: "तेज बारिश",
        71: "हल्की बर्फबारी",
        73: "बर्फबारी",
        75: "तेज बर्फबारी",
        80: "बारिश की बौछारें",
        81: "तेज बारिश की बौछारें",
        82: "बहुत तेज बौछारें",
        95: "आंधी-तूफान",
        96: "ओलों के साथ तूफान",
        99: "तेज तूफान और ओले"
    }

    try:
        return descriptions.get(
            int(code),
            "मौसम की जानकारी उपलब्ध"
        )

    except (TypeError, ValueError):
        return "मौसम की जानकारी उपलब्ध"


def get_weather(place):
    location = get_location_details(place)

    if not location:
        return {
            "success": False,
            "error": "इस जगह का मौसम नहीं मिला।"
        }

    params = urllib.parse.urlencode({
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "is_day,"
            "precipitation,"
            "weather_code,"
            "wind_speed_10m"
        ),
        "daily": (
            "temperature_2m_max,"
            "temperature_2m_min,"
            "precipitation_probability_max,"
            "sunrise,"
            "sunset"
        ),
        "timezone": "auto",
        "forecast_days": 3
    })

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + params
    )

    try:
        data = json.loads(
            fetch_url(url, timeout=8)
        )

        current = data.get("current", {})

        if "temperature_2m" not in current:
            raise ValueError("Weather data missing")

        code = current.get("weather_code")

        return {
            "success": True,
            "place": location.get("name", place),
            "city": location.get("name", place),
            "region": (
                location.get("admin2")
                or location.get("admin1")
                or ""
            ),
            "country": location.get("country", ""),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "temperature": current.get("temperature_2m"),
            "temp": current.get("temperature_2m"),
            "description": weather_description(code),
            "condition": weather_description(code),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "feels_like": current.get("apparent_temperature"),
            "precipitation": current.get("precipitation"),
            "weather_code": code,
            "is_day": current.get("is_day"),
            "current": current,
            "daily": data.get("daily", {}),
            "units": data.get("current_units", {}),
            "time": current.get("time"),
            "timezone": data.get("timezone", ""),
            "source": "Open-Meteo"
        }

    except Exception as error:
        logger.warning(
            "Weather request failed: %s",
            error
        )

        return {
            "success": False,
            "error": "मौसम सर्वर अभी उपलब्ध नहीं है।"
        }


# ============================================================
# IMAGE SEARCH - WIKIMEDIA COMMONS
# ============================================================

def search_images(query, limit=12):
    query = clean_text(query)

    if not query:
        return []

    limit = bounded_limit(limit, 12, 30)

    key = (
        "images:"
        + normalize_text(query)
        + ":"
        + str(limit)
    )

    cached = cache_get(
        key,
        IMAGE_CACHE_SECONDS
    )

    if cached is not None:
        return cached

    params = urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        "gsrsearch": "filetype:bitmap " + query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 500,
        "format": "json"
    })

    endpoint = (
        "https://commons.wikimedia.org/w/api.php?"
        + params
    )

    try:
        data = json.loads(
            fetch_url(endpoint, timeout=8)
        )

        pages = data.get(
            "query", {}
        ).get("pages", {})

        results = []

        for page in pages.values():
            info_list = page.get("imageinfo", [])

            if not info_list:
                continue

            info = info_list[0]
            metadata = info.get("extmetadata", {})

            image_url = safe_url(
                info.get("thumburl")
                or info.get("url")
            )

            page_url = safe_url(
                info.get("descriptionurl")
            )

            if not image_url or not page_url:
                continue

            def meta_value(name):
                value = metadata.get(name, {})

                if isinstance(value, dict):
                    return clean_text(
                        value.get("value", "")
                    )

                return ""

            title = clean_text(
                page.get("title", "").replace("File:", "")
            )

            results.append({
                "title": title,
                "alt": title,
                "image": image_url,
                "src": image_url,
                "image_url": image_url,
                "url": page_url,
                "page_url": page_url,
                "source": "Wikimedia Commons",
                "license": (
                    meta_value("LicenseShortName")
                    or "लाइसेंस स्रोत पेज पर देखें"
                ),
                "artist": meta_value("Artist"),
                "credit": meta_value("Credit"),
                "attribution_required": True
            })

        cache_set(key, results)

        return results

    except Exception as error:
        logger.warning(
            "Image search failed: %s",
            error
        )

        return []


# ============================================================
# VIDEO SEARCH LINKS
# ============================================================

def search_videos(query, limit=10):
    query = clean_text(query)

    if not query:
        return []

    encoded = urllib.parse.quote_plus(query)

    results = [
        {
            "title": "YouTube पर " + query + " खोजें",
            "url": (
                "https://www.youtube.com/results?search_query="
                + encoded
            ),
            "source": "YouTube",
            "type": "search_link"
        },
        {
            "title": "Bing Videos पर " + query + " खोजें",
            "url": (
                "https://www.bing.com/videos/search?q="
                + encoded
            ),
            "source": "Bing Videos",
            "type": "search_link"
        }
    ]

    return results[:bounded_limit(limit, 10, 10)]


# ============================================================
# PLACES - OPENSTREETMAP NOMINATIM
# ============================================================

_place_lock = threading.Lock()
_last_place_request = 0


def search_places(query, limit=10):
    global _last_place_request

    query = clean_text(query)

    if not query:
        return []

    limit = bounded_limit(limit, 10, 10)

    key = (
        "places:"
        + normalize_text(query)
        + ":"
        + str(limit)
    )

    cached = cache_get(
        key,
        PLACE_CACHE_SECONDS
    )

    if cached is not None:
        return cached

    with _place_lock:

        wait = 1.1 - (
            time.time() - _last_place_request
        )

        if wait > 0:
            time.sleep(wait)

        params = urllib.parse.urlencode({
            "q": query,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 1,
            "countrycodes": "in"
        })

        endpoint = (
            "https://nominatim.openstreetmap.org/search?"
            + params
        )

        _last_place_request = time.time()

        try:
            data = json.loads(
                fetch_url(endpoint, timeout=8)
            )

            results = []

            for item in data if isinstance(data, list) else []:

                lat = item.get("lat")
                lon = item.get("lon")

                if not lat or not lon:
                    continue

                osm_type = str(
                    item.get("osm_type", "")
                )

                osm_id = str(
                    item.get("osm_id", "")
                )

                results.append({
                    "name": clean_text(
                        item.get("name")
                        or item.get("display_name", "")
                    ),
                    "address": clean_text(
                        item.get("display_name", "")
                    ),
                    "category": clean_text(
                        item.get("category", "")
                    ),
                    "type": clean_text(
                        item.get("type", "")
                    ),
                    "latitude": lat,
                    "longitude": lon,
                    "map_url": (
                        "https://www.openstreetmap.org/"
                        + urllib.parse.quote(osm_type)
                        + "/"
                        + urllib.parse.quote(osm_id)
                    ),
                    "directions_url": (
                        "https://www.openstreetmap.org/directions?to="
                        + urllib.parse.quote(
                            str(lat) + "," + str(lon)
                        )
                    ),
                    "source": "© OpenStreetMap contributors"
                })

            cache_set(key, results)

            return results

        except Exception as error:
            logger.warning(
                "Place search failed: %s",
                error
            )

            return []


# ============================================================
# RATE SOURCES
# These are source links, not live financial prices.
# ============================================================

RATE_SOURCES = {
    "gold": {
        "title": "सोना",
        "description": "सोने का भाव स्रोत वेबसाइट पर देखें।",
        "url": "https://www.goodreturns.in/gold-rates/"
    },

    "silver": {
        "title": "चाँदी",
        "description": "चाँदी का भाव स्रोत वेबसाइट पर देखें।",
        "url": "https://www.goodreturns.in/silver-rates/"
    },

    "stock_market": {
        "title": "शेयर बाजार",
        "description": "शेयर बाजार के लिए NSE वेबसाइट देखें।",
        "url": "https://www.nseindia.com/"
    },

    "mandi": {
        "title": "मंडी भाव",
        "description": "कृषि मंडी के भाव के लिए Agmarknet देखें।",
        "url": "https://agmarknet.gov.in/"
    }
}


def get_rates(place="Rajasthan"):
    place = clean_text(place) or "Rajasthan"

    rates = {}

    for key, source in RATE_SOURCES.items():
        rates[key] = {
            "title": source["title"],
            "value": "स्रोत पर देखें",
            "unit": "",
            "description": source["description"],
            "source": source["url"],
            "updated_at": None,
            "is_live_value": False
        }

    return {
        "success": True,
        "place": place,
        "updated_at": utc_now(),
        "live_prices_available": False,
        "rates": rates,
        "message": (
            "यहाँ वास्तविक कीमतें सीधे उपलब्ध नहीं हैं। "
            "स्रोत वेबसाइट पर नवीनतम भाव जाँचें।"
        )
    }


# ============================================================
# GOVERNMENT INFORMATION CENTRES
# ============================================================

GOVERNMENT_CENTRES = [
    {
        "id": "schemes",
        "name": "सरकारी योजनाएँ",
        "description": "केंद्र और राज्य सरकार की योजनाएँ।",
        "items": [
            {
                "name": "myScheme",
                "description": "सरकारी योजनाएँ और पात्रता जानकारी।",
                "url": "https://www.myscheme.gov.in/",
                "source": "Government of India"
            },
            {
                "name": "UMANG",
                "description": "विभिन्न सरकारी ऑनलाइन सेवाएँ।",
                "url": "https://web.umang.gov.in/",
                "source": "Government of India"
            },
            {
                "name": "National Portal of India",
                "description": "भारत सरकार की सेवाओं की जानकारी।",
                "url": "https://www.india.gov.in/",
                "source": "Government of India"
            }
        ]
    },

    {
        "id": "documents",
        "name": "दस्तावेज़ सेवाएँ",
        "description": "आधार, डिजिटल दस्तावेज़ और पहचान सेवाएँ।",
        "items": [
            {
                "name": "UIDAI Aadhaar",
                "description": "आधार की आधिकारिक वेबसाइट।",
                "url": "https://uidai.gov.in/",
                "source": "UIDAI"
            },
            {
                "name": "DigiLocker",
                "description": "डिजिटल दस्तावेज़ सेवाएँ।",
                "url": "https://www.digilocker.gov.in/",
                "source": "Government of India"
            },
            {
                "name": "PAN Services",
                "description": "PAN कार्ड से जुड़ी सेवाएँ।",
                "url": "https://www.protean-tinpan.com/",
                "source": "Protean"
            }
        ]
    },

    {
        "id": "scholarships",
        "name": "छात्रवृत्ति",
        "description": "छात्रों के लिए छात्रवृत्ति पोर्टल।",
        "items": [
            {
                "name": "National Scholarship Portal",
                "description": "राष्ट्रीय छात्रवृत्ति सेवाएँ।",
                "url": "https://scholarships.gov.in/",
                "source": "Government of India"
            },
            {
                "name": "AICTE",
                "description": "तकनीकी शिक्षा और छात्र योजनाएँ।",
                "url": "https://www.aicte-india.org/",
                "source": "AICTE"
            }
        ]
    },

    {
        "id": "exams",
        "name": "परीक्षा और भर्ती",
        "description": "सरकारी परीक्षाएँ और भर्ती पोर्टल।",
        "items": [
            {
                "name": "Staff Selection Commission",
                "description": "SSC भर्ती और परीक्षा जानकारी।",
                "url": "https://ssc.gov.in/",
                "source": "Government of India"
            },
            {
                "name": "Railway Recruitment Board",
                "description": "रेलवे भर्ती की जानकारी।",
                "url": "https://www.rrbcdg.gov.in/",
                "source": "Indian Railways"
            },
            {
                "name": "RPSC",
                "description": "राजस्थान लोक सेवा आयोग।",
                "url": "https://rpsc.rajasthan.gov.in/",
                "source": "Government of Rajasthan"
            },
            {
                "name": "RSSB",
                "description": "राजस्थान कर्मचारी चयन बोर्ड।",
                "url": "https://rssb.rajasthan.gov.in/",
                "source": "Government of Rajasthan"
            },
            {
                "name": "National Career Service",
                "description": "रोजगार और करियर सेवाएँ।",
                "url": "https://www.ncs.gov.in/",
                "source": "Government of India"
            }
        ]
    },

    {
        "id": "skills",
        "name": "कौशल और शिक्षा",
        "description": "कौशल विकास और ऑनलाइन शिक्षा।",
        "items": [
            {
                "name": "Skill India",
                "description": "कौशल विकास से जुड़ी जानकारी।",
                "url": "https://www.skillindiadigital.gov.in/",
                "source": "Government of India"
            },
            {
                "name": "NCVT MIS",
                "description": "ITI और कौशल प्रशिक्षण जानकारी।",
                "url": "https://www.ncvtmis.gov.in/",
                "source": "Government of India"
            },
            {
                "name": "SWAYAM",
                "description": "ऑनलाइन शिक्षा और पाठ्यक्रम।",
                "url": "https://swayam.gov.in/",
                "source": "Government of India"
            }
        ]
    }
]


def get_government_centres():
    total = sum(
        len(category["items"])
        for category in GOVERNMENT_CENTRES
    )

    return {
        "success": True,
        "categories": GOVERNMENT_CENTRES,
        "total_categories": len(GOVERNMENT_CENTRES),
        "total_links": total,
        "updated_at": utc_now()
    }
    # ============================================================
# PUSH NOTIFICATIONS CONFIGURATION
# ============================================================

def get_vapid_settings():
    return {
        "public_key": os.environ.get(
            "VAPID_PUBLIC_KEY", ""
        ).strip(),

        "private_key": os.environ.get(
            "VAPID_PRIVATE_KEY", ""
        ).strip(),

        "subject": os.environ.get(
            "VAPID_SUBJECT",
            "mailto:admin@example.com"
        ).strip()
    }


def push_configuration():
    settings = get_vapid_settings()

    try:
        import pywebpush
        package_available = True

    except ImportError:
        package_available = False

    configured = bool(
        settings["public_key"]
        and settings["private_key"]
        and package_available
    )

    return {
        "public_key_configured": bool(
            settings["public_key"]
        ),
        "private_key_configured": bool(
            settings["private_key"]
        ),
        "pywebpush_available": package_available,
        "configured": configured
    }


# ============================================================
# SUBSCRIPTION STORAGE
# ============================================================

_subscription_lock = threading.RLock()


def load_subscriptions():
    if not PUSH_DATA_FILE.exists():
        return []

    try:
        with PUSH_DATA_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        return data if isinstance(data, list) else []

    except (OSError, json.JSONDecodeError):
        logger.exception(
            "Subscription data load failed"
        )

        return []


def save_subscriptions(subscriptions):
    temp_file = PUSH_DATA_FILE.with_suffix(".tmp")

    try:
        DATA_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        with temp_file.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                subscriptions,
                file,
                ensure_ascii=False,
                indent=2
            )

            file.flush()
            os.fsync(file.fileno())

        os.replace(
            temp_file,
            PUSH_DATA_FILE
        )

        return True

    except OSError:
        logger.exception(
            "Subscription data save failed"
        )

        try:
            if temp_file.exists():
                temp_file.unlink()
        except OSError:
            pass

        return False


def notification_admin_authorized():
    expected = os.environ.get(
        "NOTIFICATION_ADMIN_TOKEN",
        ""
    ).strip()

    if not expected:
        return False

    supplied = request.headers.get(
        "X-Admin-Token",
        ""
    ).strip()

    return bool(supplied) and hmac.compare_digest(
        supplied,
        expected
    )


# ============================================================
# BASIC API RATE LIMIT
# ============================================================

_rate_lock = threading.Lock()
_rate_data = {}


def request_allowed(max_requests=120, window=60):
    now = time.time()

    ip = (
        request.headers.get("X-Forwarded-For", "")
        .split(",")[0]
        .strip()
        or request.remote_addr
        or "unknown"
    )

    key = (
        ip,
        request.path
    )

    with _rate_lock:
        timestamps = _rate_data.get(key, [])

        timestamps = [
            stamp for stamp in timestamps
            if now - stamp < window
        ]

        if len(timestamps) >= max_requests:
            _rate_data[key] = timestamps
            return False

        timestamps.append(now)
        _rate_data[key] = timestamps

        if len(_rate_data) > 5000:
            expired_keys = [
                item for item, values in _rate_data.items()
                if not values or now - values[-1] > window
            ]

            for item in expired_keys:
                _rate_data.pop(item, None)

        return True


@app.before_request
def api_rate_limit():
    if request.path.startswith("/api/"):
        if not request_allowed():
            return json_error(
                "बहुत अधिक अनुरोध किए गए हैं। थोड़ी देर बाद प्रयास करें।",
                429
            )


# ============================================================
# MAIN WEBSITE ROUTES
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/sw.js", methods=["GET"])
def service_worker():
    response = app.make_response(
        send_from_directory(
            STATIC_DIR,
            "sw.js",
            mimetype="application/javascript"
        )
    )

    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"

    return response


# ============================================================
# HEALTH AND ABOUT
# ============================================================

@app.route("/health", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "success": True,
        "app": APP_NAME,
        "owner": OWNER_NAME,
        "version": APP_VERSION,
        "status": "running",
        "services_count": len(load_services()),
        "time": utc_now()
    })


@app.route("/api/about", methods=["GET"])
def about():
    return jsonify({
        "success": True,
        "name": APP_NAME,
        "owner": OWNER_NAME,
        "version": APP_VERSION,
        "description": (
            "Hindi and English search and information platform."
        ),
        "features": [
            "Hindi and English website search",
            "Website directory",
            "Search suggestions",
            "Trending searches",
            "RSS news",
            "Open-Meteo weather",
            "Wikimedia image search",
            "Video search links",
            "OpenStreetMap places",
            "Government Information Centre",
            "Rate source directory",
            "Push notifications",
            "Search analytics",
            "Service Worker support"
        ],
        "services_count": len(load_services()),
        "time": utc_now()
    })


# ============================================================
# MAIN SEARCH API
# ============================================================

@app.route(
    "/api/search",
    methods=["GET", "POST"]
)
def api_search():
    query, limit = get_request_query()

    if len(query) > MAX_QUERY_LENGTH:
        return json_error(
            "खोज का शब्द 250 अक्षरों से छोटा रखें।"
        )

    if not query:
        return jsonify({
            "success": True,
            "query": "",
            "count": 0,
            "results": [],
            "message": "खोजने के लिए कुछ लिखें।"
        })

    record_search(query)

    results = search_services(
        query,
        limit
    )

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "message": (
            ""
            if results
            else "इस खोज से संबंधित लिंक नहीं मिला।"
        )
    })


@app.route("/api/search-services", methods=["GET"])
def api_search_services():
    return api_search()


# ============================================================
# WEBSITE DIRECTORY API
# Empty query now returns the website directory.
# This fixes the old index.html connection.
# ============================================================

@app.route("/api/services", methods=["GET"])
def api_services():
    query = clean_text(
        request.args.get("q", "")
    )

    category = normalize_text(
        request.args.get("category", "")
    )

    if len(query) > MAX_QUERY_LENGTH:
        return json_error(
            "खोज का शब्द बहुत लंबा है।"
        )

    if query:
        results = search_services(
            query,
            request.args.get("limit", 100)
        )

    else:
        results = load_services()

    if category and category != "all":
        results = [
            item for item in results
            if normalize_text(
                item.get("category", "")
            ) == category
        ]

    results = results[:100]

    return jsonify({
        "success": True,
        "count": len(results),
        "results": results,
        "services": results
    })


# ============================================================
# SEARCH SUGGESTIONS
# ============================================================

@app.route("/api/suggestions", methods=["GET"])
def api_suggestions():
    query = clean_text(
        request.args.get("q", "")
    )

    if len(query) > MAX_QUERY_LENGTH:
        return json_error(
            "खोज का शब्द बहुत लंबा है।"
        )

    results = get_search_suggestions(
        query,
        request.args.get("limit", 8)
    )

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results
    })


# ============================================================
# TRENDING SEARCHES
# ============================================================

@app.route("/api/trending", methods=["GET"])
def api_trending():
    results = get_trending_searches(
        request.args.get("limit", 10)
    )

    return jsonify({
        "success": True,
        "count": len(results),
        "results": results
    })


# ============================================================
# GOVERNMENT INFORMATION CENTRE
# Fixes /api/future/centres missing route.
# ============================================================

@app.route("/api/future/centres", methods=["GET"])
@app.route("/api/government/centres", methods=["GET"])
def api_government_centres():
    return jsonify(
        get_government_centres()
    )


# ============================================================
# IMAGE SEARCH API
# Both old and new endpoint paths work.
# ============================================================

@app.route("/api/images", methods=["GET"])
@app.route("/api/images/search", methods=["GET"])
def api_images():
    query = clean_text(
        request.args.get("q", "")
    )

    if len(query) > MAX_QUERY_LENGTH:
        return json_error(
            "फोटो खोज का शब्द बहुत लंबा है।"
        )

    if not query:
        return jsonify({
            "success": True,
            "query": "",
            "count": 0,
            "results": []
        })

    results = search_images(
        query,
        request.args.get("limit", 12)
    )

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "source": "Wikimedia Commons"
    })


# ============================================================
# VIDEO SEARCH API
# ============================================================

@app.route("/api/videos", methods=["GET"])
def api_videos():
    query = clean_text(
        request.args.get("q", "")
    )

    if len(query) > MAX_QUERY_LENGTH:
        return json_error(
            "वीडियो खोज का शब्द बहुत लंबा है।"
        )

    results = search_videos(
        query,
        request.args.get("limit", 10)
    )

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results
    })


# ============================================================
# PLACE SEARCH API
# ============================================================

@app.route("/api/places", methods=["GET"])
def api_places():
    query = clean_text(
        request.args.get("q", "")
    )

    if len(query) > MAX_QUERY_LENGTH:
        return json_error(
            "जगह का नाम बहुत लंबा है।"
        )

    results = search_places(
        query,
        request.args.get("limit", 10)
    )

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results
    })


# ============================================================
# NEWS API
# ============================================================

@app.route("/api/news", methods=["GET"])
def api_news():
    query = clean_text(
        request.args.get("q", "")
    )

    if len(query) > MAX_QUERY_LENGTH:
        return json_error(
            "खोज का शब्द बहुत लंबा है।"
        )

    refresh = request.args.get(
        "refresh",
        ""
    ).lower() in ("1", "true", "yes")

    results = fetch_news(
        query=query,
        force_refresh=refresh
    )

    limit = bounded_limit(
        request.args.get("limit", 20),
        20,
        MAX_NEWS_ITEMS
    )

    results = results[:limit]

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
        "source": "RSS feeds",
        "updated_at": utc_now()
    })


# ============================================================
# WEATHER API
# ============================================================

@app.route("/api/weather", methods=["GET"])
def api_weather():
    place = clean_text(
        request.args.get("place")
        or request.args.get("q")
        or "Bali, Rajasthan"
    )

    if len(place) > 100:
        return json_error(
            "जगह का नाम बहुत लंबा है।"
        )

    result = get_weather(place)

    status = (
        200
        if result.get("success")
        else 502
    )

    return jsonify(result), status


# ============================================================
# RATE SOURCES API
# ============================================================

@app.route("/api/rates", methods=["GET"])
def api_rates():
    place = clean_text(
        request.args.get("place", "Rajasthan")
    )

    if len(place) > 100:
        return json_error(
            "जगह का नाम बहुत लंबा है।"
        )

    return jsonify(
        get_rates(place)
    )


# ============================================================
# NOTIFICATION PUBLIC KEY API
# ============================================================

@app.route(
    "/api/notifications/public-key",
    methods=["GET"]
)
def notification_public_key():
    settings = get_vapid_settings()

    if not settings["public_key"]:
        return json_error(
            "Notification public key सेट नहीं है।",
            503
        )

    return jsonify({
        "success": True,
        "publicKey": settings["public_key"]
    })


@app.route(
    "/api/notifications/config",
    methods=["GET"]
)
def notification_config():
    settings = get_vapid_settings()

    return jsonify({
        "success": True,
        "enabled": bool(
            settings["public_key"]
            and settings["private_key"]
        ),
        "public_key": settings["public_key"],
        "subject": settings["subject"]
    })


@app.route(
    "/api/notifications/status",
    methods=["GET"]
)
def notification_status():
    config = push_configuration()

    return jsonify({
        "success": True,
        "version": APP_VERSION,
        "push_configured": config["configured"],
        "configuration": config,
        "subscription_count": len(
            load_subscriptions()
        ),
        "time": utc_now()
    })


# ============================================================
# NOTIFICATION SUBSCRIBE
# ============================================================

@app.route(
    "/api/notifications/subscribe",
    methods=["POST"]
)
def notification_subscribe():
    settings = get_vapid_settings()

    if not settings["public_key"]:
        return json_error(
            "Push notification configuration उपलब्ध नहीं है।",
            503
        )

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return json_error(
            "गलत subscription data।"
        )

    endpoint = safe_url(
        payload.get("endpoint")
    )

    keys = payload.get("keys", {})

    if not endpoint or not isinstance(keys, dict):
        return json_error(
            "Subscription details अधूरी हैं।"
        )

    p256dh = clean_text(
        keys.get("p256dh")
    )

    auth = clean_text(
        keys.get("auth")
    )

    if not p256dh or not auth:
        return json_error(
            "Subscription keys उपलब्ध नहीं हैं।"
        )

    subscription = {
        "endpoint": endpoint,
        "expirationTime": payload.get(
            "expirationTime"
        ),
        "keys": {
            "p256dh": p256dh,
            "auth": auth
        },
        "created_at": utc_now()
    }

    with _subscription_lock:
        subscriptions = load_subscriptions()

        subscriptions = [
            item for item in subscriptions
            if item.get("endpoint") != endpoint
        ]

        if len(subscriptions) >= 10000:
            return json_error(
                "Subscription की अधिकतम सीमा पूरी है।",
                429
            )

        subscriptions.append(subscription)

        if not save_subscriptions(subscriptions):
            return json_error(
                "Subscription सेव नहीं हो सका।",
                500
            )

    return jsonify({
        "success": True,
        "message": "Notification subscription सेव हो गया।",
        "subscription_count": len(subscriptions)
    })


# ============================================================
# NOTIFICATION UNSUBSCRIBE
# ============================================================

@app.route(
    "/api/notifications/unsubscribe",
    methods=["POST"]
)
def notification_unsubscribe():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return json_error(
            "गलत अनुरोध।"
        )

    endpoint = safe_url(
        payload.get("endpoint")
    )

    if not endpoint:
        return json_error(
            "Subscription endpoint नहीं मिला।"
        )

    with _subscription_lock:
        subscriptions = load_subscriptions()

        updated = [
            item for item in subscriptions
            if item.get("endpoint") != endpoint
        ]

        if not save_subscriptions(updated):
            return json_error(
                "Subscription हटाया नहीं जा सका।",
                500
            )

    return jsonify({
        "success": True,
        "message": "Subscription हटा दिया गया।",
        "subscription_count": len(updated)
    })


# ============================================================
# ADMIN PUSH NOTIFICATION SEND
# Requires NOTIFICATION_ADMIN_TOKEN.
# ============================================================

@app.route(
    "/api/notifications/send",
    methods=["POST"]
)
def notification_send():
    if not notification_admin_authorized():
        return json_error(
            "Admin authorization जरूरी है।",
            403
        )

    config = push_configuration()

    if not config["configured"]:
        return json_error(
            "Push notification configuration पूरी नहीं है।",
            503
        )

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return json_error(
            "गलत notification data।"
        )

    title = clean_text(
        payload.get("title") or APP_NAME
    )[:100]

    body = clean_text(
        payload.get("body") or "नई जानकारी उपलब्ध है।"
    )[:300]

    target_url = payload.get("url") or "/"

    if target_url != "/":
        target_url = safe_url(target_url)

        if not target_url:
            return json_error(
                "Notification URL सही नहीं है।"
            )

        parsed_target = urllib.parse.urlparse(
            target_url
        )

        parsed_base = urllib.parse.urlparse(
            request.host_url
        )

        if parsed_target.netloc != parsed_base.netloc:
            return json_error(
                "Notification URL इसी वेबसाइट का होना चाहिए।"
            )

    settings = get_vapid_settings()

    try:
        from pywebpush import (
            webpush,
            WebPushException
        )

    except ImportError:
        return json_error(
            "pywebpush package उपलब्ध नहीं है।",
            503
        )

    subscriptions = load_subscriptions()

    sent = 0
    failed = 0
    expired = []

    notification_data = json.dumps({
        "title": title,
        "body": body,
        "url": target_url,
        "icon": "/static/logo.png"
    })

    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=subscription,
                data=notification_data,
                vapid_private_key=settings["private_key"],
                vapid_claims={
                    "sub": settings["subject"]
                }
            )

            sent += 1

        except WebPushException as error:
            failed += 1

            status_code = getattr(
                getattr(error, "response", None),
                "status_code",
                None
            )

            if status_code in (404, 410):
                expired.append(
                    subscription.get("endpoint")
                )

            logger.warning(
                "Push delivery failed: %s",
                error
            )

        except Exception:
            failed += 1
            logger.exception(
                "Unexpected push notification error"
            )

    if expired:
        remaining = [
            item for item in subscriptions
            if item.get("endpoint") not in expired
        ]

        save_subscriptions(remaining)

    return jsonify({
        "success": True,
        "attempted": len(subscriptions),
        "sent": sent,
        "failed": failed,
        "expired_removed": len(expired)
    })


# ============================================================
# WEBSITE STATUS
# ============================================================

@app.route("/api/status", methods=["GET"])
def api_status():
    config = push_configuration()

    return jsonify({
        "success": True,
        "app": APP_NAME,
        "owner": OWNER_NAME,
        "version": APP_VERSION,
        "status": "online",
        "services": {
            "service_directory": SERVICES_FILE.is_file(),
            "notifications": config["configured"],
            "government_centres": True,
            "news": True,
            "weather": True,
            "image_search": True
        },
        "time": utc_now()
    })


# ============================================================
# ADMIN STATISTICS
# ============================================================

@app.route(
    "/api/admin/stats",
    methods=["GET"]
)
def api_admin_stats():
    if not notification_admin_authorized():
        return json_error(
            "Admin authorization जरूरी है।",
            403
        )

    with _trending_lock:
        total_searches = sum(
            _trending_searches.values()
        )

        unique_searches = len(
            _trending_searches
        )

    return jsonify({
        "success": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "statistics": {
            "total_searches": total_searches,
            "unique_searches": unique_searches,
            "services_count": len(load_services()),
            "notification_subscriptions": len(
                load_subscriptions()
            )
        },
        "time": utc_now()
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def page_not_found(error):
    if request.path.startswith("/api/"):
        return json_error(
            "यह API endpoint उपलब्ध नहीं है।",
            404
        )

    return jsonify({
        "success": False,
        "error": "यह पेज नहीं मिला।"
    }), 404


@app.errorhandler(413)
def request_too_large(error):
    return json_error(
        "भेजा गया डेटा बहुत बड़ा है।",
        413
    )


@app.errorhandler(500)
def internal_server_error(error):
    logger.exception(
        "Internal server error"
    )

    if request.path.startswith("/api/"):
        return json_error(
            "Server पर समस्या आई है।",
            500
        )

    return jsonify({
        "success": False,
        "error": "Server पर समस्या आई है।"
    }), 500


# ============================================================
# SECURITY RESPONSE HEADERS
# ============================================================

@app.after_request
def add_security_headers(response):
    response.headers.setdefault(
        "X-Content-Type-Options",
        "nosniff"
    )

    response.headers.setdefault(
        "X-Frame-Options",
        "SAMEORIGIN"
    )

    response.headers.setdefault(
        "Referrer-Policy",
        "strict-origin-when-cross-origin"
    )

    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()"
    )

    if request.is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains"
        )

    return response


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
