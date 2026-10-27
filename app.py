
import os
import json
import re
import logging
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote_plus

from flask import Flask, request, jsonify, render_template, make_response

APP_NAME = "Ishwar Search"
OWNER_NAME = "Ishwar Ghanchi"
APP_VERSION = "2.0.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICES_FILE = os.path.join(BASE_DIR, "services.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ishwar_search")

app = Flask(__name__)

# Request size limit: 10 MB
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["JSON_AS_ASCII"] = False


RAW_SERVICES = [
    {
        "name": "Indian Railways",
        "url": "https://indianrailways.gov.in/",
        "category": "railway",
        "keywords": ["railway", "train", "रेलवे", "ट्रेन"]
    },
    {
        "name": "IRCTC",
        "url": "https://www.irctc.co.in/",
        "category": "railway",
        "keywords": ["ticket", "train ticket", "टिकट", "रेल टिकट"]
    },
    {
        "name": "Railway Recruitment Board",
        "url": "https://www.rrbcdg.gov.in/",
        "category": "jobs",
        "keywords": ["rrb", "railway jobs", "रेलवे भर्ती", "नौकरी"]
    },
    {
        "name": "National Career Service",
        "url": "https://www.ncs.gov.in/",
        "category": "jobs",
        "keywords": ["jobs", "employment", "रोजगार", "जॉब"]
    },
    {
        "name": "Staff Selection Commission",
        "url": "https://ssc.gov.in/",
        "category": "jobs",
        "keywords": ["ssc", "government jobs", "सरकारी नौकरी"]
    },
    {
        "name": "Union Public Service Commission",
        "url": "https://upsc.gov.in/",
        "category": "education",
        "keywords": ["upsc", "civil services", "यूपीएससी"]
    },
    {
        "name": "National Testing Agency",
        "url": "https://nta.ac.in/",
        "category": "education",
        "keywords": ["nta", "exam", "entrance exam", "परीक्षा"]
    },
    {
        "name": "DigiLocker",
        "url": "https://www.digilocker.gov.in/",
        "category": "documents",
        "keywords": ["marksheet", "certificate", "डिजिलॉकर", "मार्कशीट"]
    },
    {
        "name": "UIDAI Aadhaar",
        "url": "https://uidai.gov.in/",
        "category": "documents",
        "keywords": ["aadhaar", "aadhar", "आधार", "आधार कार्ड"]
    },
    {
        "name": "Income Tax Department",
        "url": "https://www.incometax.gov.in/",
        "category": "finance",
        "keywords": ["income tax", "itr", "इनकम टैक्स", "आयकर"]
    },
    {
        "name": "PAN Services - Protean",
        "url": "https://www.protean-tinpan.com/",
        "category": "documents",
        "keywords": ["pan card", "पैन कार्ड", "pan application"]
    },
    {
        "name": "Rajasthan Government",
        "url": "https://rajasthan.gov.in/",
        "category": "rajasthan",
        "keywords": ["rajasthan", "राजस्थान", "राजस्थान सरकार"]
    },
    {
        "name": "Rajasthan Public Service Commission",
        "url": "https://rpsc.rajasthan.gov.in/",
        "category": "jobs",
        "keywords": ["rpsc", "राजस्थान भर्ती", "राजस्थान परीक्षा"]
    },
    {
        "name": "Rajasthan Single Sign On",
        "url": "https://sso.rajasthan.gov.in/",
        "category": "rajasthan",
        "keywords": ["sso", "राजस्थान एसएसओ", "सरकारी सेवाएं"]
    },
    {
        "name": "Employment News",
        "url": "https://www.employmentnews.gov.in/",
        "category": "jobs",
        "keywords": ["employment news", "job notification", "भर्ती समाचार"]
    },
    {
        "name": "National Scholarship Portal",
        "url": "https://scholarships.gov.in/",
        "category": "education",
        "keywords": ["scholarship", "छात्रवृत्ति", "छात्रवृति", "स्कॉलरशिप"]
    },
    {
        "name": "SWAYAM Online Courses",
        "url": "https://swayam.gov.in/",
        "category": "education",
        "keywords": ["online course", "study", "ऑनलाइन पढ़ाई", "कोर्स"]
    },
    {
        "name": "University of Rajasthan",
        "url": "https://www.uniraj.ac.in/",
        "category": "education",
        "keywords": ["uniraj", "rajasthan university", "राजस्थान यूनिवर्सिटी"]
    },
    {
        "name": "Maharshi Dayanand Saraswati University",
        "url": "https://www.mdsuajmer.ac.in/",
        "category": "education",
        "keywords": ["mdsu", "ajmer university", "एमडीएसयू", "अजमेर यूनिवर्सिटी"]
    },
    {
        "name": "Rajasthan State Road Transport Corporation",
        "url": "https://rsrtconline.rajasthan.gov.in/",
        "category": "travel",
        "keywords": ["rsrtc", "bus", "बस", "राजस्थान रोडवेज"]
    },
    {
        "name": "Reserve Bank of India",
        "url": "https://www.rbi.org.in/",
        "category": "finance",
        "keywords": ["rbi", "bank", "बैंक", "रिजर्व बैंक"]
    },
    {
        "name": "National Portal of India",
        "url": "https://www.india.gov.in/",
        "category": "government",
        "keywords": ["india government", "भारत सरकार", "सरकारी पोर्टल"]
    },
    {
        "name": "MyGov India",
        "url": "https://www.mygov.in/",
        "category": "government",
        "keywords": ["mygov", "government schemes", "सरकारी योजना"]
    },
    {
        "name": "Press Information Bureau",
        "url": "https://pib.gov.in/",
        "category": "news",
        "keywords": ["pib", "government news", "सरकारी समाचार"]
    },
    {
        "name": "National Consumer Helpline",
        "url": "https://consumerhelpline.gov.in/",
        "category": "legal",
        "keywords": ["consumer complaint", "शिकायत", "उपभोक्ता"]
    },
    {
        "name": "Cyber Crime Reporting Portal",
        "url": "https://cybercrime.gov.in/",
        "category": "legal",
        "keywords": ["cyber crime", "online fraud", "साइबर फ्रॉड", "ऑनलाइन ठगी"]
    },
    {
        "name": "eCourts Services",
        "url": "https://ecourts.gov.in/",
        "category": "legal",
        "keywords": ["court", "case status", "कोर्ट", "केस स्टेटस"]
    },
    {
        "name": "Ayushman Bharat PM-JAY",
        "url": "https://pmjay.gov.in/",
        "category": "health",
        "keywords": ["ayushman", "health card", "आयुष्मान कार्ड"]
    },
    {
        "name": "ABHA Health Account",
        "url": "https://abha.abdm.gov.in/",
        "category": "health",
        "keywords": ["abha", "health id", "आभा कार्ड", "हेल्थ आईडी"]
    },
    {
        "name": "OpenStreetMap",
        "url": "https://www.openstreetmap.org/",
        "category": "maps",
        "keywords": ["map", "location", "नक्शा", "लोकेशन"]
    },
    {
        "name": "Wikipedia Hindi",
        "url": "https://hi.wikipedia.org/",
        "category": "knowledge",
        "keywords": ["wikipedia", "जानकारी", "ज्ञान", "विकिपीडिया"]
    },
    {
        "name": "YouTube",
        "url": "https://www.youtube.com/",
        "category": "video",
        "keywords": ["video", "videos", "वीडियो", "यूट्यूब"]
    },
    {
        "name": "Google Maps",
        "url": "https://maps.google.com/",
        "category": "maps",
        "keywords": ["maps", "direction", "रास्ता", "मैप"]
    },
    {
        "name": "Google News",
        "url": "https://news.google.com/",
        "category": "news",
        "keywords": ["news", "latest news", "समाचार", "ताजा खबर"]
    },
    {
        "name": "Amazon India",
        "url": "https://www.amazon.in/",
        "category": "shopping",
        "keywords": ["shopping", "buy", "खरीदारी", "ऑनलाइन सामान"]
    },
    {
        "name": "Flipkart",
        "url": "https://www.flipkart.com/",
        "category": "shopping",
        "keywords": ["flipkart", "shopping", "ऑनलाइन खरीदारी"]
    },
    {
        "name": "Meesho",
        "url": "https://www.meesho.com/",
        "category": "shopping",
        "keywords": ["meesho", "low price", "सस्ता सामान"]
    },
    {
        "name": "GitHub",
        "url": "https://github.com/",
        "category": "technology",
        "keywords": ["coding", "programming", "कोडिंग", "प्रोग्रामिंग"]
    },
    {
        "name": "Python",
        "url": "https://www.python.org/",
        "category": "technology",
        "keywords": ["python", "learn python", "पायथन"]
    },
    {
        "name": "MDN Web Docs",
        "url": "https://developer.mozilla.org/",
        "category": "technology",
        "keywords": ["html", "css", "javascript", "वेब डेवलपमेंट"]
    }
]

# =========================================================
# HINDI / ENGLISH SEARCH ALIASES
# =========================================================

ALIASES = {
    "railway": [
        "railway", "railways", "train", "rrb", "रेलवे", "रेलगाड़ी"
    ],
    "scholarship": [
        "scholarship", "scholarships", "छात्रवृत्ति",
        "छात्रवृति", "स्कॉलरशिप"
    ],
    "aadhaar": [
        "aadhaar", "aadhar", "आधार", "आधार कार्ड"
    ],
    "jobs": [
        "job", "jobs", "vacancy", "recruitment",
        "नौकरी", "भर्ती", "रोजगार", "रिक्तियां"
    ],
    "rajasthan": [
        "rajasthan", "राजस्थान", "राजस्थान सरकार"
    ],
    "news": [
        "news", "latest news", "समाचार", "खबर", "खबरें"
    ],
    "pan": [
        "pan", "pancard", "pan card", "पैन", "पैन कार्ड"
    ],
    "education": [
        "education", "study", "exam", "शिक्षा", "पढ़ाई", "परीक्षा"
    ],
    "fraud": [
        "fraud", "scam", "cyber crime", "फ्रॉड", "धोखाधड़ी", "ठगी"
    ]
}


def normalize_text(value):
    """Search text को सामान्य रूप में बदलता है."""
    if value is None:
        return ""

    value = unicodedata.normalize("NFKC", str(value))
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)

    return value


def expand_query(query):
    """Query के साथ मिलते-जुलते Hindi/English शब्द जोड़ता है."""
    normalized = normalize_text(query)

    if not normalized:
        return []

    terms = {normalized}

    for group, aliases in ALIASES.items():
        normalized_aliases = [
            normalize_text(alias) for alias in aliases
        ]

        if any(alias in normalized for alias in normalized_aliases):
            terms.add(group)
            terms.update(normalized_aliases)

    # Query को शब्दों में भी खोजें
    terms.update(normalized.split())

    return [term for term in terms if term]


def normalize_service(item):
    """पुरानी और नई services.json entries को समान रूप देता है."""
    if not isinstance(item, dict):
        return None

    name = str(item.get("name") or item.get("title") or "").strip()
    url = str(item.get("url") or item.get("link") or "").strip()

    if not name or not url:
        return None

    # केवल HTTP/HTTPS URLs स्वीकार करें
    if not url.startswith(("https://", "http://")):
        return None

    keywords = item.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [keywords]
    if not isinstance(keywords, list):
        keywords = []

    category = str(item.get("category") or "general").strip().lower()

    return {
        "name": name,
        "url": url,
        "category": category,
        "keywords": [str(word) for word in keywords],
        "description": str(item.get("description") or "")
    }


def load_services():
    """Built-in services और services.json को मिलाकर लोड करता है."""
    combined = list(RAW_SERVICES)

    if os.path.isfile(SERVICES_FILE):
        try:
            with open(SERVICES_FILE, "r", encoding="utf-8") as file:
                extra = json.load(file)

            if isinstance(extra, list):
                combined.extend(extra)
            elif isinstance(extra, dict):
                # {"services": [...]} फॉर्मेट भी स्वीकार करें
                services_list = extra.get("services", [])
                if isinstance(services_list, list):
                    combined.extend(services_list)

        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("services.json पढ़ने में समस्या: %s", exc)

    results = []
    seen_urls = set()

    for item in combined:
        service = normalize_service(item)
        if not service:
            continue

        key = service["url"].rstrip("/").lower()

        if key in seen_urls:
            continue

        seen_urls.add(key)
        results.append(service)

    return results


SERVICES = load_services()


def search_services(query, limit=30):
    """स्थानीय services में सरल ranked search."""
    query = normalize_text(query)

    if not query:
        return []

    terms = expand_query(query)
    matches = []

    for service in SERVICES:
        name = normalize_text(service["name"])
        category = normalize_text(service["category"])
        description = normalize_text(service["description"])
        keywords = " ".join(service["keywords"])
        keywords = normalize_text(keywords)

        searchable = f"{name} {category} {description} {keywords}"
        score = 0

        if query == name:
            score += 100
        elif query in name:
            score += 50

        if query == category:
            score += 30

        if query in keywords:
            score += 25

        for term in terms:
            if term and term in searchable:
                score += 5

        if score > 0:
            result = dict(service)
            result["score"] = score
            matches.append(result)

    matches.sort(
        key=lambda item: (-item["score"], item["name"].lower())
    )

    return matches[:max(1, min(int(limit), 100))]


def current_utc_time():
    return datetime.now(timezone.utc).isoformat()


from flask import abort
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import xml.etree.ElementTree as ET
import urllib.parse
import html
import time


# ---------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    try:
        return render_template("index.html")
    except Exception:
        logger.exception("index.html load नहीं हुई")

        return (
            "<!doctype html><html lang='hi'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Ishwar Search</title>"
            "<body style='font-family:Arial;max-width:750px;margin:50px auto;"
            "padding:20px;background:#f5f7fb;color:#172033'>"
            "<h1>Ishwar Search</h1>"
            "<p>Owner: Ishwar Ghanchi</p>"
            "<p>Website का index.html template नहीं मिला। "
            "GitHub में templates/index.html की मौजूदगी जाँचें।</p>"
            "</body></html>",
            200
        )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "success": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "services_count": len(SERVICES),
        "status": "running",
        "time": current_utc_time()
    })


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "success": True,
        "app": APP_NAME,
        "status": "ok",
        "version": APP_VERSION,
        "services_count": len(SERVICES)
    })


# ---------------------------------------------------------
# SEARCH API
# ---------------------------------------------------------

@app.route("/api/search", methods=["GET", "POST"])
def api_search():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        query = payload.get("q") or payload.get("query") or ""
        limit = payload.get("limit", 30)
    else:
        query = request.args.get("q") or request.args.get("query") or ""
        limit = request.args.get("limit", 30)

    query = str(query).strip()

    if not query:
        return jsonify({
            "success": True,
            "query": "",
            "count": 0,
            "results": [],
            "message": "अपना सवाल या शब्द लिखें।"
        })

    if len(query) > 250:
        return jsonify({
            "success": False,
            "error": "Search query बहुत लंबी है।"
        }), 400

    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 30

    results = search_services(query, limit=limit)

    # Search result format को frontend के लिए सरल रखें
    formatted = []

    for item in results:
        formatted.append({
            "name": item["name"],
            "title": item["name"],
            "url": item["url"],
            "link": item["url"],
            "category": item["category"],
            "description": item.get("description", ""),
            "score": item.get("score", 0)
        })

    return jsonify({
        "success": True,
        "query": query,
        "count": len(formatted),
        "results": formatted,
        "source": "Ishwar Search local services"
    })


# ---------------------------------------------------------
# SEARCH SUGGESTIONS
# ---------------------------------------------------------

@app.route("/api/suggestions", methods=["GET"])
def api_suggestions():
    query = (
        request.args.get("q")
        or request.args.get("query")
        or ""
    ).strip()

    if not query:
        defaults = [
            "Railway recruitment",
            "Rajasthan jobs",
            "Scholarship",
            "Aadhaar card",
            "PAN card",
            "Online fraud complaint"
        ]

        return jsonify({
            "success": True,
            "suggestions": defaults
        })

    if len(query) > 150:
        query = query[:150]

    results = search_services(query, limit=8)

    suggestions = []
    for item in results:
        if item["name"] not in suggestions:
            suggestions.append(item["name"])

    return jsonify({
        "success": True,
        "query": query,
        "suggestions": suggestions
    })


# ---------------------------------------------------------
# NEWS API
# External RSS feeds are used; results depend on feed access.
# ---------------------------------------------------------

RSS_FEEDS = [
    {
        "name": "Google News India",
        "url": "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"
    },
    {
        "name": "BBC Hindi",
        "url": "https://feeds.bbci.co.uk/hindi/rss.xml"
    },
    {
        "name": "PIB India",
        "url": "https://pib.gov.in/RssMain.aspx"
    }
]


def fetch_news(query="", limit=15):
    news_items = []
    seen = set()

    for feed in RSS_FEEDS:
        if len(news_items) >= limit:
            break

        try:
            req = Request(
                feed["url"],
                headers={
                    "User-Agent": "IshwarSearch/2.0 (+news reader)"
                }
            )

            with urlopen(req, timeout=8) as response:
                xml_data = response.read(2_000_000)

            root = ET.fromstring(xml_data)

            for item in root.findall(".//item"):
                title = item.findtext("title", default="").strip()
                link = item.findtext("link", default="").strip()
                description = item.findtext(
                    "description", default=""
                ).strip()
                pub_date = item.findtext("pubDate", default="").strip()

                if not title or not link:
                    continue

                if not link.startswith(("https://", "http://")):
                    continue

                # RSS descriptions often contain HTML
                description = re.sub(
                    r"<[^>]+>", " ", description
                )
                description = html.unescape(description)
                description = re.sub(r"\s+", " ", description).strip()

                if query:
                    search_text = normalize_text(
                        title + " " + description
                    )
                    if normalize_text(query) not in search_text:
                        continue

                key = link.rstrip("/").lower()
                if key in seen:
                    continue
                seen.add(key)

                news_items.append({
                    "title": html.unescape(title),
                    "url": link,
                    "link": link,
                    "description": description[:500],
                    "published": pub_date,
                    "source": feed["name"]
                })

                if len(news_items) >= limit:
                    break

        except (URLError, HTTPError, ET.ParseError, TimeoutError, OSError) as exc:
            logger.warning(
                "News feed unavailable (%s): %s",
                feed["name"], exc
            )
        except Exception:
            logger.exception("News feed processing error: %s", feed["name"])

    return news_items


@app.route("/api/news", methods=["GET"])
def api_news():
    query = request.args.get("q", "").strip()

    try:
        limit = int(request.args.get("limit", 15))
    except (ValueError, TypeError):
        limit = 15

    limit = max(1, min(limit, 30))

    try:
        results = fetch_news(query=query, limit=limit)

        return jsonify({
            "success": True,
            "count": len(results),
            "results": results,
            "source_note": (
                "RSS समाचार स्रोतों से प्राप्त। "
                "कुछ स्रोत अस्थायी रूप से उपलब्ध नहीं हो सकते।"
            ),
            "updated_at": current_utc_time()
        })

    except Exception:
        logger.exception("News API failed")

        return jsonify({
            "success": False,
            "count": 0,
            "results": [],
            "error": "अभी समाचार लोड नहीं हो पाए।"
        }), 503


# ---------------------------------------------------------
# WEATHER API
# Uses free Open-Meteo endpoints; no API key required.
# ---------------------------------------------------------

WEATHER_CITIES = {
    "jaipur": (26.9124, 75.7873, "Jaipur"),
    "जयपुर": (26.9124, 75.7873, "Jaipur"),
    "delhi": (28.6139, 77.2090, "Delhi"),
    "दिल्ली": (28.6139, 77.2090, "Delhi"),
    "mumbai": (19.0760, 72.8777, "Mumbai"),
    "मुंबई": (19.0760, 72.8777, "Mumbai"),
    "ajmer": (26.4499, 74.6399, "Ajmer"),
    "अजमेर": (26.4499, 74.6399, "Ajmer"),
    "jodhpur": (26.2389, 73.0243, "Jodhpur"),
    "जोधपुर": (26.2389, 73.0243, "Jodhpur"),
    "udaipur": (24.5854, 73.7125, "Udaipur"),
    "उदयपुर": (24.5854, 73.7125, "Udaipur"),
    "alwar": (27.5530, 76.6346, "Alwar"),
    "अलवर": (27.5530, 76.6346, "Alwar"),
    "bengaluru": (12.9716, 77.5946, "Bengaluru"),
    "bangalore": (12.9716, 77.5946, "Bengaluru"),
    "chennai": (13.0827, 80.2707, "Chennai"),
    "kolkata": (22.5726, 88.3639, "Kolkata"),
    "hyderabad": (17.3850, 78.4867, "Hyderabad"),
    "pune": (18.5204, 73.8567, "Pune")
}


def weather_description(code):
    descriptions = {
        0: "साफ आसमान",
        1: "मुख्यतः साफ",
        2: "कुछ बादल",
        3: "बादल छाए हुए",
        45: "कोहरा",
        48: "जमा हुआ कोहरा",
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
        81: "तेज बौछारें",
        82: "बहुत तेज बौछारें",
        95: "आंधी-तूफान",
        96: "ओलों के साथ तूफान",
        99: "तेज तूफान और ओले"
    }

    try:
        return descriptions.get(int(code), "मौसम की जानकारी उपलब्ध")
    except (ValueError, TypeError):
        return "मौसम की जानकारी उपलब्ध"


@app.route("/api/weather", methods=["GET"])
def api_weather():
    city_input = (
        request.args.get("city")
        or request.args.get("q")
        or "Jaipur"
    ).strip()

    if not city_input or len(city_input) > 80:
        return jsonify({
            "success": False,
            "error": "शहर का नाम सही तरीके से लिखें।"
        }), 400

    city_key = normalize_text(city_input)

    # Known cities: coordinates from the list above
    city_data = WEATHER_CITIES.get(city_key)

    # Other city names: try Open-Meteo geocoding
    try:
        if city_data:
            latitude, longitude, city_name = city_data
        else:
            geo_url = (
                "https://geocoding-api.open-meteo.com/v1/search?"
                + urllib.parse.urlencode({
                    "name": city_input,
                    "count": 1,
                    "language": "en",
                    "format": "json"
                })
            )

            req = Request(
                geo_url,
                headers={"User-Agent": "IshwarSearch/2.0"}
            )

            with urlopen(req, timeout=8) as response:
                geo_data = json.loads(response.read().decode("utf-8"))

            places = geo_data.get("results") or []
            if not places:
                return jsonify({
                    "success": False,
                    "city": city_input,
                    "error": "यह शहर नहीं मिला। अंग्रेज़ी में नाम लिखकर देखें।"
                }), 404

            place = places[0]
            latitude = float(place["latitude"])
            longitude = float(place["longitude"])
            city_name = place.get("name", city_input)

        weather_url = (
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode({
                "latitude": latitude,
                "longitude": longitude,
                "current": (
                    "temperature_2m,relative_humidity_2m,"
                    "apparent_temperature,is_day,precipitation,"
                    "weather_code,wind_speed_10m"
                ),
                "timezone": "auto"
            })
        )

        req = Request(
            weather_url,
            headers={"User-Agent": "IshwarSearch/2.0"}
        )

        with urlopen(req, timeout=10) as response:
            weather_data = json.loads(response.read().decode("utf-8"))

        current = weather_data.get("current", {})

        if not current:
            raise ValueError("Weather provider returned no current data")

        temperature = current.get("temperature_2m")
        code = current.get("weather_code")

        result = {
            "success": True,
            "city": city_name,
            "country": "India",
            "temperature": temperature,
            "temp": temperature,
            "description": weather_description(code),
            "condition": weather_description(code),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "apparent_temperature": current.get("apparent_temperature"),
            "current": current,
            "units": weather_data.get("current_units", {}),
            "source": "Open-Meteo",
            "updated_at": current.get("time")
        }

        return jsonify(result)

    except (URLError, HTTPError, TimeoutError, OSError, ValueError, KeyError) as exc:
        logger.warning("Weather API unavailable: %s", exc)

        return jsonify({
            "success": False,
            "city": city_input,
            "error": "मौसम सेवा अभी उपलब्ध नहीं है। थोड़ी देर बाद कोशिश करें।"
        }), 503

    except Exception:
        logger.exception("Unexpected weather API error")

        return jsonify({
            "success": False,
            "city": city_input,
            "error": "मौसम की जानकारी प्राप्त नहीं हो सकी।"
        }), 500




import io
import mimetypes
from flask import send_file
from werkzeug.utils import secure_filename


# ---------------------------------------------------------
# APP INFORMATION
# ---------------------------------------------------------

@app.route("/api/about", methods=["GET"])
def api_about():
    return jsonify({
        "success": True,
        "name": APP_NAME,
        "owner": OWNER_NAME,
        "version": APP_VERSION,
        "features": [
            "Hindi and English local search",
            "Website directory",
            "News RSS reader",
            "Weather information",
            "AI chat integration endpoint",
            "File information tools",
            "Image information tools",
            "Website builder starter"
        ],
        "services_count": len(SERVICES)
    })


# ---------------------------------------------------------
# AI CHAT STARTER
# This endpoint does not pretend to be a real AI model.
# No paid API is enabled here.
# ---------------------------------------------------------

@app.route("/api/ai/chat", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def api_ai_chat():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({
            "success": False,
            "error": "कृपया सही JSON संदेश भेजें।"
        }), 400

    message = str(
        payload.get("message")
        or payload.get("prompt")
        or ""
    ).strip()

    if not message:
        return jsonify({
            "success": False,
            "error": "अपना सवाल लिखें।"
        }), 400

    if len(message) > 5000:
        return jsonify({
            "success": False,
            "error": "संदेश 5000 अक्षरों से छोटा रखें।"
        }), 400

    # Search-based assistance without an external AI model
    results = search_services(message, limit=5)

    return jsonify({
        "success": True,
        "mode": "starter",
        "message": message,
        "reply": (
            "Ishwar Search का AI Chat अभी शुरुआती मोड में है। "
            "यह अभी किसी वास्तविक AI मॉडल से जवाब नहीं बनाता। "
            "नीचे तुम्हारे सवाल से मिलती-जुलती वेबसाइटें दी गई हैं।"
        ),
        "results": [
            {
                "name": item["name"],
                "url": item["url"],
                "category": item["category"]
            }
            for item in results
        ],
        "ai_connected": False
    })


# ---------------------------------------------------------
# FILE TOOLS
# Safe basic file information only.
# No execution of uploaded files.
# ---------------------------------------------------------

ALLOWED_FILE_EXTENSIONS = {
    ".txt", ".csv", ".json", ".md", ".pdf",
    ".docx", ".xlsx", ".png", ".jpg", ".jpeg",
    ".webp", ".gif"
}


@app.route("/api/files/info", methods=["POST"])
def api_file_info():
    uploaded = request.files.get("file")

    if uploaded is None or not uploaded.filename:
        return jsonify({
            "success": False,
            "error": "पहले फ़ाइल चुनें।"
        }), 400

    safe_name = secure_filename(uploaded.filename)
    extension = os.path.splitext(safe_name)[1].lower()

    if extension not in ALLOWED_FILE_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "यह फ़ाइल प्रकार अभी समर्थित नहीं है।"
        }), 400

    try:
        content = uploaded.read(10 * 1024 * 1024 + 1)

        if len(content) > 10 * 1024 * 1024:
            return jsonify({
                "success": False,
                "error": "फ़ाइल का आकार 10 MB से कम रखें।"
            }), 413

        guessed_type = (
            uploaded.mimetype
            or mimetypes.guess_type(safe_name)[0]
            or "application/octet-stream"
        )

        result = {
            "success": True,
            "filename": safe_name,
            "extension": extension,
            "size_bytes": len(content),
            "mime_type": guessed_type,
            "message": (
                "फ़ाइल की बुनियादी जानकारी पढ़ ली गई है। "
                "यह endpoint अभी फ़ाइल की सामग्री को संपादित नहीं करता।"
            )
        }

        # Parse small UTF-8 text files for a simple preview
        if extension in {".txt", ".md", ".csv", ".json"}:
            try:
                text_content = content.decode("utf-8-sig")
                result["preview"] = text_content[:2000]
            except UnicodeDecodeError:
                result["preview"] = (
                    "यह फ़ाइल UTF-8 टेक्स्ट के रूप में नहीं पढ़ी जा सकी।"
                )

        return jsonify(result)

    except Exception:
        logger.exception("File information processing failed")

        return jsonify({
            "success": False,
            "error": "फ़ाइल की जानकारी पढ़ने में समस्या हुई।"
        }), 500


# ---------------------------------------------------------
# IMAGE TOOLS
# Basic metadata; actual image editing is not connected yet.
# ---------------------------------------------------------

ALLOWED_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif"
}


@app.route("/api/images/info", methods=["POST"])
def api_image_info():
    uploaded = request.files.get("file") or request.files.get("image")

    if uploaded is None or not uploaded.filename:
        return jsonify({
            "success": False,
            "error": "पहले इमेज चुनें।"
        }), 400

    safe_name = secure_filename(uploaded.filename)
    extension = os.path.splitext(safe_name)[1].lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "PNG, JPG, JPEG, WEBP या GIF इमेज चुनें।"
        }), 400

    try:
        content = uploaded.read(10 * 1024 * 1024 + 1)

        if len(content) > 10 * 1024 * 1024:
            return jsonify({
                "success": False,
                "error": "इमेज 10 MB से छोटी रखें।"
            }), 413

        # Check basic file signatures to reject obvious mismatches
        signatures = {
            ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            ".jpg": content.startswith(b"\xff\xd8\xff"),
            ".jpeg": content.startswith(b"\xff\xd8\xff"),
            ".gif": content.startswith((b"GIF87a", b"GIF89a")),
            ".webp": (
                len(content) >= 12
                and content[:4] == b"RIFF"
                and content[8:12] == b"WEBP"
            )
        }

        if not signatures.get(extension, False):
            return jsonify({
                "success": False,
                "error": "फ़ाइल का वास्तविक प्रकार और extension मेल नहीं खाते।"
            }), 400

        return jsonify({
            "success": True,
            "filename": safe_name,
            "extension": extension,
            "size_bytes": len(content),
            "message": (
                "इमेज प्राप्त हुई। यह शुरुआती endpoint केवल फ़ाइल "
                "की जाँच करता है; इमेज एडिटिंग अभी कनेक्ट नहीं है।"
            ),
            "image_editing_connected": False
        })

    except Exception:
        logger.exception("Image information processing failed")

        return jsonify({
            "success": False,
            "error": "इमेज की जाँच नहीं हो सकी।"
        }), 500


# ---------------------------------------------------------
# WEBSITE BUILDER STARTER
# Creates a simple HTML preview, not a hosted live website.
# ---------------------------------------------------------

@app.route("/api/website-builder", methods=["POST"])
def api_website_builder():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({
            "success": False,
            "error": "कृपया वेबसाइट का विवरण JSON में भेजें।"
        }), 400

    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()

    if not title:
        return jsonify({
            "success": False,
            "error": "वेबसाइट का नाम लिखें।"
        }), 400

    if len(title) > 100 or len(description) > 1000:
        return jsonify({
            "success": False,
            "error": "नाम या विवरण बहुत लंबा है।"
        }), 400

    # Escape user-provided text to prevent HTML injection
    safe_title = html.escape(title)
    safe_description = html.escape(description)

    html_preview = f"""<!doctype html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
<style>
body {{
    margin: 0;
    padding: 30px;
    font-family: Arial, sans-serif;
    background: #f3f6fb;
    color: #172033;
}}
main {{
    max-width: 800px;
    margin: 40px auto;
    padding: 28px;
    background: white;
    border-radius: 16px;
}}
h1 {{ color: #174ea6; }}
</style>
</head>
<body>
<main>
<h1>{safe_title}</h1>
<p>{safe_description}</p>
<footer>Made with Ishwar Search Website Builder</footer>
</main>
</body>
</html>"""

    return jsonify({
        "success": True,
        "title": title,
        "html": html_preview,
        "message": (
            "HTML preview तैयार है। इसे अभी किसी सार्वजनिक URL पर "
            "प्रकाशित नहीं किया गया है।"
        ),
        "published": False
    })


# ---------------------------------------------------------
# SIMPLE SEARCH EXPORT
# ---------------------------------------------------------

@app.route("/api/services", methods=["GET"])
def api_services():
    category = normalize_text(request.args.get("category", ""))

    results = SERVICES

    if category:
        results = [
            item for item in SERVICES
            if normalize_text(item["category"]) == category
        ]

    return jsonify({
        "success": True,
        "count": len(results),
        "results": [
            {
                "name": item["name"],
                "url": item["url"],
                "category": item["category"],
                "description": item.get("description", "")
            }
            for item in results
        ]
    })


# ---------------------------------------------------------
# ERROR HANDLERS
# ---------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/") or request.path == "/health":
        return jsonify({
            "success": False,
            "error": "यह API route उपलब्ध नहीं है।",
            "path": request.path
        }), 404

    return (
        "<!doctype html><html lang='hi'><meta charset='utf-8'>"
        "<title>Page Not Found</title>"
        "<body style='font-family:Arial;padding:30px'>"
        "<h1>Ishwar Search</h1>"
        "<p>यह पेज नहीं मिला।</p>"
        "<a href='/'>होम पेज पर जाएँ</a>"
        "</body></html>",
        404
    )


@app.errorhandler(413)
def too_large(error):
    return jsonify({
        "success": False,
        "error": "अपलोड की गई फ़ाइल बहुत बड़ी है। अधिकतम आकार 10 MB है।"
    }), 413


@app.errorhandler(500)
def internal_error(error):
    logger.exception("Internal server error")

    return jsonify({
        "success": False,
        "error": "सर्वर पर समस्या हुई। कृपया बाद में कोशिश करें।"
    }), 500


# ---------------------------------------------------------
# SECURITY HEADERS
# ---------------------------------------------------------

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Do not cache dynamic API results
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"

    return response


# ---------------------------------------------------------
# FINAL CONFIGURATION
# Render sets the PORT environment variable.
# ---------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
