
from flask import Flask, request, jsonify, render_template
from pathlib import Path
from datetime import datetime
import re
import json
import html
import urllib.request
import xml.etree.ElementTree as ET

app = Flask(__name__)

APP_NAME = "Ishwar Search"
OWNER = "Ishwar Ghanchi"
BASE_DIR = Path(__file__).resolve().parent

RAW_SERVICES = [
    # Search engines
    ("Google Search", "Search", "google web search खोज", "https://www.google.com/"),
    ("Bing Search", "Search", "bing web search", "https://www.bing.com/"),
    ("DuckDuckGo", "Search", "private search", "https://duckduckgo.com/"),

    # Government and identity
    ("India Government Portal", "Government", "india government भारत सरकार", "https://www.india.gov.in/"),
    ("DigiLocker", "Government", "documents marksheet certificate", "https://www.digilocker.gov.in/"),
    ("UMANG", "Government", "government services सरकारी सेवाएं", "https://web.umang.gov.in/"),
    ("UIDAI Aadhaar", "Government", "aadhaar aadhar आधार uidai", "https://uidai.gov.in/"),
    ("My Aadhaar", "Government", "aadhaar services आधार सेवा", "https://myaadhaar.uidai.gov.in/"),
    ("PAN Income Tax", "Government", "pan card income tax पैन कार्ड", "https://www.incometax.gov.in/"),
    ("Passport Seva", "Government", "passport पासपोर्ट", "https://www.passportindia.gov.in/"),
    ("Voter Services", "Government", "voter id election वोटर कार्ड", "https://voters.eci.gov.in/"),
    ("EPFO", "Government", "pf provident fund पीएफ", "https://www.epfindia.gov.in/"),
    ("ESIC", "Government", "employee insurance कर्मचारी बीमा", "https://www.esic.gov.in/"),
    ("MyScheme", "Government", "government scheme yojana सरकारी योजना", "https://www.myscheme.gov.in/"),
    ("National Consumer Helpline", "Complaints", "consumer complaint ग्राहक शिकायत", "https://consumerhelpline.gov.in/"),
    ("CPGRAMS Grievance Portal", "Complaints", "government complaint grievance शिकायत", "https://pgportal.gov.in/"),
    ("Cyber Crime Reporting", "Safety", "online fraud cyber crime साइबर ठगी", "https://cybercrime.gov.in/"),
    ("RTI Online", "Government", "right to information सूचना अधिकार", "https://rtionline.gov.in/"),

    # Rajasthan services
    ("Rajasthan SSO", "Rajasthan", "rajasthan sso login राजस्थान एसएसओ", "https://sso.rajasthan.gov.in/"),
    ("Rajasthan Jan Aadhaar", "Rajasthan", "jan aadhaar जन आधार", "https://janaadhaar.rajasthan.gov.in/"),
    ("Rajasthan Sampark", "Complaints", "rajasthan complaint sampark शिकायत", "https://sampark.rajasthan.gov.in/"),
    ("Rajasthan Public Service Commission", "Jobs", "rpsc recruitment राजस्थान भर्ती", "https://rpsc.rajasthan.gov.in/"),
    ("Rajasthan Staff Selection Board", "Jobs", "rssb rsmssb recruitment राजस्थान भर्ती", "https://rssb.rajasthan.gov.in/"),
    ("Rajasthan High Court", "Legal", "rajasthan high court अदालत", "https://hcraj.nic.in/"),
    ("Rajasthan Tourism", "Travel", "rajasthan tourism राजस्थान पर्यटन", "https://www.tourism.rajasthan.gov.in/"),
    ("Rajasthan Agriculture Department", "Agriculture", "farmer agriculture किसान कृषि", "https://agriculture.rajasthan.gov.in/"),
    ("Bhu Naksha Rajasthan", "Agriculture", "land map जमीन नक्शा", "https://bhunaksha.rajasthan.gov.in/"),

    # Railways and jobs
    ("Indian Railways", "Railway", "railway train रेलवे", "https://indianrailways.gov.in/"),
    ("IRCTC", "Railway", "train ticket booking टिकट", "https://www.irctc.co.in/"),
    ("Railway Recruitment Boards", "Railway Jobs", "rrb railway recruitment भर्ती", "https://www.rrbcdg.gov.in/"),
    ("RRB Apply", "Railway Jobs", "rrb alp ntpc group d technician", "https://www.rrbapply.gov.in/"),
    ("Rail Madad", "Railway", "railway complaint रेलवे शिकायत", "https://railmadad.indianrailways.gov.in/"),
    ("National Train Enquiry", "Railway", "train status running status ट्रेन स्थिति", "https://enquiry.indianrail.gov.in/"),
    ("National Career Service", "Jobs", "job vacancy employment नौकरी", "https://www.ncs.gov.in/"),
    ("Staff Selection Commission", "Jobs", "ssc government jobs भर्ती", "https://ssc.gov.in/"),
    ("UPSC", "Jobs", "upsc civil services examination", "https://upsc.gov.in/"),
    ("Employment News", "Jobs", "employment news government jobs", "https://employmentnews.gov.in/"),
    ("Apprenticeship India", "ITI Jobs", "apprentice fitter iti अप्रेंटिस", "https://www.apprenticeshipindia.gov.in/"),
    ("NCVT MIS", "ITI", "ncvt iti marksheet certificate fitter", "https://www.ncvtmis.gov.in/"),
    ("Skill India Digital Hub", "ITI", "skill india sidh training कौशल", "https://www.skillindiadigital.gov.in/"),
    ("DRDO", "Jobs", "drdo careers recruitment", "https://www.drdo.gov.in/"),
    ("ISRO Careers", "Jobs", "isro space jobs अंतरिक्ष नौकरी", "https://www.isro.gov.in/"),
    ("BHEL", "Jobs", "bhel recruitment apprentice", "https://www.bhel.com/"),
    ("Indian Oil", "Jobs", "iocl careers apprentice", "https://iocl.com/"),
    ("Airport Authority of India", "Jobs", "aai recruitment airport jobs", "https://www.aai.aero/"),

    # Education
    ("National Scholarship Portal", "Education", "scholarship छात्रवृत्ति", "https://scholarships.gov.in/"),
    ("National Testing Agency", "Education", "nta exams परीक्षा", "https://nta.ac.in/"),
    ("CBSE", "Education", "cbse school board result", "https://www.cbse.gov.in/"),
    ("CBSE Results", "Education", "cbse results रिजल्ट", "https://results.cbse.nic.in/"),
    ("NCERT", "Education", "ncert books किताबें", "https://ncert.nic.in/"),
    ("NIOS", "Education", "nios open schooling", "https://www.nios.ac.in/"),
    ("UGC", "Education", "ugc university college", "https://www.ugc.gov.in/"),
    ("AICTE", "Education", "aicte technical education", "https://www.aicte-india.org/"),
    ("IGNOU", "Education", "ignou distance education", "https://www.ignou.ac.in/"),
    ("SWAYAM", "Education", "online courses पढ़ाई", "https://swayam.gov.in/"),
    ("DIKSHA", "Education", "learning education courses", "https://diksha.gov.in/"),
    ("Khan Academy", "Education", "free learning maths science", "https://www.khanacademy.org/"),
    ("FreeCodeCamp", "Education", "free coding programming", "https://www.freecodecamp.org/"),

    # Health and agriculture
    ("Ayushman Bharat PM-JAY", "Health", "ayushman card आयुष्मान", "https://pmjay.gov.in/"),
    ("ABHA Health Account", "Health", "abha digital health account", "https://abha.abdm.gov.in/"),
    ("eSanjeevani", "Health", "online doctor consultation", "https://esanjeevani.mohfw.gov.in/"),
    ("Ministry of Health", "Health", "health ministry स्वास्थ्य मंत्रालय", "https://mohfw.gov.in/"),
    ("PM Kisan", "Agriculture", "pm kisan farmer किसान", "https://pmkisan.gov.in/"),
    ("eShram", "Government", "labour worker श्रमिक कार्ड", "https://eshram.gov.in/"),
    ("e-NAM", "Agriculture", "farmer mandi कृषि मंडी", "https://enam.gov.in/"),
    ("PM Fasal Bima Yojana", "Agriculture", "crop insurance फसल बीमा", "https://pmfby.gov.in/"),
    ("India Meteorological Department", "Weather", "weather forecast मौसम", "https://mausam.imd.gov.in/"),

    # Finance and business
    ("Reserve Bank of India", "Finance", "rbi banking आरबीआई", "https://www.rbi.org.in/"),
    ("SEBI", "Finance", "sebi investor securities", "https://www.sebi.gov.in/"),
    ("GST Portal", "Business", "gst registration tax जीएसटी", "https://www.gst.gov.in/"),
    ("MCA Company Services", "Business", "company registration कंपनी", "https://www.mca.gov.in/"),
    ("Udyam Registration", "Business", "msme small business उद्योग", "https://udyamregistration.gov.in/"),
    ("Startup India", "Business", "startup business उद्यम", "https://www.startupindia.gov.in/"),
    ("Government e Marketplace", "Business", "gem government procurement", "https://gem.gov.in/"),

    # Search, maps and media
    ("Google Maps", "Maps", "maps directions रास्ता नक्शा", "https://maps.google.com/"),
    ("OpenStreetMap", "Maps", "openstreetmap maps नक्शा", "https://www.openstreetmap.org/"),
    ("Google Translate", "Tools", "translate language अनुवाद", "https://translate.google.com/"),
    ("Google News", "News", "news समाचार खबर", "https://news.google.com/"),
    ("PIB India", "News", "government press release सरकारी समाचार", "https://pib.gov.in/"),
    ("BBC Hindi", "News", "bbc hindi news समाचार", "https://www.bbc.com/hindi"),
    ("DD News", "News", "dd news india समाचार", "https://ddnews.gov.in/"),
    ("YouTube", "Video", "youtube video वीडियो", "https://www.youtube.com/"),
    ("Google Drive", "Files", "cloud storage files", "https://drive.google.com/"),
    ("DigiLocker", "Government", "digital documents डिजिलॉकर", "https://www.digilocker.gov.in/"),

    # AI and technology
    ("ChatGPT", "AI", "chatgpt artificial intelligence एआई", "https://chatgpt.com/"),
    ("Google Gemini", "AI", "gemini google ai", "https://gemini.google.com/"),
    ("Microsoft Copilot", "AI", "copilot microsoft ai", "https://copilot.microsoft.com/"),
    ("Claude", "AI", "claude ai assistant", "https://claude.ai/"),
    ("Perplexity", "AI", "perplexity ai search", "https://www.perplexity.ai/"),
    ("Hugging Face", "AI", "machine learning ai models", "https://huggingface.co/"),
    ("GitHub", "Technology", "github code repository coding", "https://github.com/"),
    ("Python", "Technology", "python programming language", "https://www.python.org/"),
    ("MDN Web Docs", "Technology", "html css javascript web development", "https://developer.mozilla.org/"),
    ("W3Schools", "Education", "html css javascript coding", "https://www.w3schools.com/"),
    ("Replit", "Technology", "online coding programming", "https://replit.com/"),
    ("Canva", "Design", "canva poster graphic design", "https://www.canva.com/"),
    ("Photopea", "Design", "photo editor image editing", "https://www.photopea.com/"),
    ("Blender", "Design", "3d modelling animation", "https://www.blender.org/"),
    ("OBS Studio", "Tools", "screen recording livestream", "https://obsproject.com/"),
    ("VirusTotal", "Security", "check suspicious file link", "https://www.virustotal.com/"),
    ("Mozilla Firefox", "Tools", "firefox browser", "https://www.mozilla.org/firefox/"),
    ("Brave Browser", "Tools", "brave browser privacy", "https://brave.com/"),

    # More everyday resources
    ("Wikipedia Hindi", "Knowledge", "wikipedia जानकारी", "https://hi.wikipedia.org/"),
    ("Internet Archive", "Knowledge", "archive books historical resources", "https://archive.org/"),
    ("Coursera", "Education", "online courses learning", "https://www.coursera.org/"),
    ("edX", "Education", "online courses education", "https://www.edx.org/"),
    ("Amazon India", "Shopping", "amazon online shopping", "https://www.amazon.in/"),
    ("Flipkart", "Shopping", "flipkart online shopping", "https://www.flipkart.com/"),
    ("Myntra", "Shopping", "myntra fashion clothes", "https://www.myntra.com/"),
    ("India Post", "Services", "india post postal services", "https://www.indiapost.gov.in/"),
    ("Parivahan", "Transport", "driving licence vehicle registration", "https://parivahan.gov.in/"),
    ("National Legal Services Authority", "Legal", "nalsa legal aid मुफ्त कानूनी सहायता", "https://nalsa.gov.in/"),
    ("eCourts Services", "Legal", "court case अदालत केस", "https://ecourts.gov.in/"),
    ("India Code", "Legal", "laws acts कानून", "https://www.indiacode.nic.in/"),
    ("National Disaster Management Authority", "Safety", "disaster emergency आपदा", "https://ndma.gov.in/"),
    ("Food Safety Authority of India", "Health", "fssai food safety", "https://www.fssai.gov.in/"),
    ("World Health Organization", "Health", "who public health", "https://www.who.int/"),
    ("NASA", "Science", "space science astronomy", "https://www.nasa.gov/"),
    ("ISRO", "Science", "space science india", "https://www.isro.gov.in/"),
    ("UNESCO", "Knowledge", "education science culture", "https://www.unesco.org/"),
]

def normalize(value):
    value = str(value or "").lower().strip()
    replacements = {
        "आधार": "aadhaar",
        "छात्रवृत्ति": "scholarship",
        "राजस्थान": "rajasthan",
        "रेलवे": "railway",
        "नौकरी": "job",
        "भर्ती": "recruitment",
        "किसान": "farmer",
        "पैन कार्ड": "pan card",
        "परीक्षा": "exam",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)

    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


ALIASES = {
    "railway": "railway train rrb recruitment",
    "scholarship": "scholarship student education",
    "aadhaar": "aadhaar aadhar uidai",
    "aadhar": "aadhaar aadhar uidai",
    "rajasthan": "rajasthan sso rpsc rssb sampark",
    "job": "jobs recruitment career vacancy",
    "jobs": "job jobs recruitment career",
    "iti": "iti ncvt fitter apprentice",
    "fitter": "fitter iti ncvt apprentice",
    "pan": "pan card income tax",
    "police": "police recruitment",
    "news": "news pib bbc india",
    "ai": "ai artificial intelligence chatgpt gemini",
    "map": "map maps google location",
    "complaint": "complaint grievance sampark consumer",
    "fraud": "fraud cyber crime online safety",
}


def build_services():
    result = []
    seen = set()

    for name, category, keywords, url in RAW_SERVICES:
        url = str(url).strip()
        if not url.startswith("https://") or url in seen:
            continue

        seen.add(url)
        result.append({
            "name": name,
            "category": category,
            "keywords": keywords,
            "url": url,
        })

    extra_file = BASE_DIR / "services.json"

    if extra_file.exists():
        try:
            data = json.loads(extra_file.read_text(encoding="utf-8"))

            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue

                    name = str(item.get("name", "")).strip()
                    url = str(item.get("url", "")).strip()

                    if not name or not url.startswith("https://"):
                        continue
                    if url in seen:
                        continue

                    seen.add(url)
                    result.append({
                        "name": name[:120],
                        "category": str(
                            item.get("category", "Other")
                        )[:60],
                        "keywords": str(
                            item.get("keywords", "")
                        )[:500],
                        "url": url,
                    })

        except (OSError, json.JSONDecodeError):
            app.logger.warning("Could not read services.json")

    return result


SERVICES = build_services()


def search_services(query, limit=50):
    q = normalize(query)

    if not q:
        return []

    expanded = ALIASES.get(q, q)
    terms = set(expanded.split())
    ranked = []

    for service in SERVICES:
        name = normalize(service["name"])
        category = normalize(service["category"])
        keywords = normalize(service["keywords"])
        url = normalize(service["url"])
        searchable = f"{name} {category} {keywords} {url}"

        score = 0

        if q == name:
            score += 100
        if name.startswith(q):
            score += 70
        elif q in name:
            score += 45
        if q in category:
            score += 20
        if q in keywords:
            score += 25
        if q in url:
            score += 10

        score += sum(
            8 for term in terms
            if len(term) > 1 and term in searchable
        )

        if score > 0:
            ranked.append((score, service))

    ranked.sort(
        key=lambda item: (-item[0], item[1]["name"].lower())
    )

    return [service for _, service in ranked[:limit]]


SMART_SUGGESTIONS = [
    {
        "name": "Railway Recruitment Boards",
        "category": "Railway Jobs",
        "keywords": "railway rrb alp ntpc group d technician",
        "url": "https://www.rrbapply.gov.in/",
    },
    {
        "name": "RRC North Western Railway",
        "category": "Railway Jobs",
        "keywords": "rrc nwr jaipur apprentice",
        "url": "https://nwr.indianrailways.gov.in/",
    },
    {
        "name": "Rajasthan Sampark",
        "category": "Complaints",
        "keywords": "rajasthan complaint shikayat",
        "url": "https://sampark.rajasthan.gov.in/",
    },
    {
        "name": "National Cyber Crime Reporting Portal",
        "category": "Safety",
        "keywords": "online fraud scam cyber crime",
        "url": "https://cybercrime.gov.in/",
    },
    {
        "name": "National Consumer Helpline",
        "category": "Complaints",
        "keywords": "consumer complaint customer grievance",
        "url": "https://consumerhelpline.gov.in/",
    },
    {
        "name": "NCVT MIS",
        "category": "ITI",
        "keywords": "iti marksheet certificate pntc fitter",
        "url": "https://www.ncvtmis.gov.in/",
    },
    {
        "name": "National Career Service",
        "category": "Jobs",
        "keywords": "job vacancy employment career",
        "url": "https://www.ncs.gov.in/",
    },
    {
        "name": "Rajasthan Staff Selection Board",
        "category": "Rajasthan Jobs",
        "keywords": "rssb rsmssb government recruitment",
        "url": "https://rssb.rajasthan.gov.in/",
    },
    {
        "name": "National Scholarship Portal",
        "category": "Education",
        "keywords": "scholarship student education",
        "url": "https://scholarships.gov.in/",
    },
    {
        "name": "Apprenticeship India",
        "category": "ITI Jobs",
        "keywords": "iti fitter apprenticeship apprentice",
        "url": "https://www.apprenticeshipindia.gov.in/",
    },
]


def get_suggestions(query, limit=10):
    q = normalize(query)

    if len(q) < 2:
        return []

    candidates = SERVICES + SMART_SUGGESTIONS
    ranked = []
    seen_urls = set()

    for service in candidates:
        url = service.get("url", "")

        if not url.startswith("https://") or url in seen_urls:
            continue

        seen_urls.add(url)

        name = normalize(service.get("name", ""))
        category = normalize(service.get("category", ""))
        keywords = normalize(service.get("keywords", ""))
        searchable = f"{name} {category} {keywords}"

        score = 0

        if q == name:
            score += 100
        if name.startswith(q):
            score += 80
        elif q in name:
            score += 50
        if q in category:
            score += 25
        if q in keywords:
            score += 20

        score += sum(
            8 for term in q.split()
            if len(term) > 1 and term in searchable
        )

        if score > 0:
            ranked.append((score, service))

    ranked.sort(
        key=lambda item: (-item[0], item[1]["name"].lower())
    )

    return [
        {
            "name": service["name"],
            "category": service["category"],
            "url": service["url"],
        }
        for _, service in ranked[:limit]
    ]


RSS_FEEDS = [
    (
        "Google News India",
        "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi",
    ),
    ("PIB India", "https://pib.gov.in/RssMain.aspx"),
    ("BBC Hindi", "https://feeds.bbci.co.uk/hindi/rss.xml"),
]


def fetch_news(limit=15):
    articles = []
    seen_links = set()

    for source, url in RSS_FEEDS:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "IshwarSearch/1.0"},
            )

            with urllib.request.urlopen(req, timeout=4) as response:
                root = ET.fromstring(response.read())

            for item in root.findall(".//item"):
                title = html.unescape(
                    item.findtext("title", "")
                ).strip()
                link = item.findtext("link", "").strip()
                date = item.findtext("pubDate", "").strip()

                if (
                    title
                    and link.startswith("https://")
                    and link not in seen_links
                ):
                    seen_links.add(link)
                    articles.append({
                        "title": title,
                        "url": link,
                        "source": source,
                        "date": date,
                    })

                if len(articles) >= limit:
                    return articles

        except Exception:
            app.logger.info("News feed unavailable: %s", source)

    return articles

@app.route("/")
def home():
    query = request.args.get("q", "").strip()[:160]
    results = search_services(query) if query else []

    return render_template(
        "index.html",
        query=query,
        results=results,
        news=[],
        service_count=len(SERVICES),
        services_count=len(SERVICES),
        categories=sorted({
            service["category"] for service in SERVICES
        }),
        current_year=datetime.now().year,
        owner=OWNER,
        app_name=APP_NAME,
    )


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()[:160]
    results = search_services(query)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
    })


@app.route("/api/suggestions")
def api_suggestions():
    query = request.args.get("q", "").strip()[:160]

    return jsonify({
        "success": True,
        "query": query,
        "results": get_suggestions(query),
    })


@app.route("/api/news")
def api_news():
    return jsonify({
        "success": True,
        "results": fetch_news(),
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": APP_NAME,
        "owner": OWNER,
        "services": len(SERVICES),
    })


if __name__ == "__main__":
    print("=" * 42)
    print(f"{APP_NAME} is starting")
    print(f"Owner: {OWNER}")
    print(f"Services loaded: {len(SERVICES)}")
    print("Open http://127.0.0.1:5000")
    print("=" * 42)

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )
