
from flask import Flask, render_template, request, jsonify
from pathlib import Path
from datetime import datetime
import re
import json
import html
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

app = Flask(__name__)

APP_NAME = "Ishwar Search"
OWNER = "Ishwar Ghanchi"
BASE_DIR = Path(__file__).resolve().parent

# सभी सेवाएँ इसी फ़ाइल में रखी गई हैं।
# प्रारूप: नाम, श्रेणी, खोज शब्द, वेबसाइट URL
RAW_SERVICES = [
    ("Indian Railways", "Railway", "railway train रेल रेलगाड़ी", "https://indianrailways.gov.in/"),
    ("Railway Recruitment Boards", "Jobs", "rrb railway recruitment भर्ती", "https://www.rrbapply.gov.in/"),
    ("Railway Recruitment Control Board", "Jobs", "rrcb railway भर्ती", "https://rrcb.gov.in/"),
    ("National Career Service", "Jobs", "job jobs नौकरी रोजगार", "https://www.ncs.gov.in/"),
    ("Employment News", "Jobs", "employment news सरकारी नौकरी", "https://employmentnews.gov.in/"),
    ("UPSC", "Jobs", "upsc civil services आईएएस", "https://upsc.gov.in/"),
    ("SSC", "Jobs", "ssc staff selection आयोग", "https://ssc.gov.in/"),
    ("Institute of Banking Personnel Selection", "Jobs", "ibps bank banking बैंक भर्ती", "https://www.ibps.in/"),
    ("SBI Careers", "Jobs", "sbi bank job बैंक भर्ती", "https://sbi.co.in/web/careers"),
    ("Rajasthan Public Service Commission", "Rajasthan Jobs", "rpsc राजस्थान भर्ती", "https://rpsc.rajasthan.gov.in/"),
    ("Rajasthan Staff Selection Board", "Rajasthan Jobs", "rssb rsmssb राजस्थान कर्मचारी चयन", "https://rssb.rajasthan.gov.in/"),
    ("Rajasthan SSO", "Rajasthan", "rajasthan sso राजस्थान एसएसओ", "https://sso.rajasthan.gov.in/"),
    ("Rajasthan Government", "Rajasthan", "rajasthan government राजस्थान सरकार", "https://rajasthan.gov.in/"),
    ("Rajasthan Jan Aadhaar", "Rajasthan", "jan aadhaar जन आधार राजस्थान", "https://janaadhaar.rajasthan.gov.in/"),
    ("Rajasthan Sampark", "Rajasthan", "rajasthan sampark complaint शिकायत", "https://sampark.rajasthan.gov.in/"),
    ("Rajasthan High Court", "Legal", "rajasthan high court राजस्थान उच्च न्यायालय", "https://hcraj.nic.in/"),
    ("Rajasthan Police", "Safety", "rajasthan police पुलिस", "https://police.rajasthan.gov.in/"),
    ("Rajasthan Board of Secondary Education", "Education", "rbse ajmer board राजस्थान बोर्ड", "https://rajeduboard.rajasthan.gov.in/"),
    ("Rajasthan University", "Education", "uniraj university राजस्थान विश्वविद्यालय", "https://www.uniraj.ac.in/"),
        ("Rajasthan College Education Department", "Education", "rajasthan college education higher education राजस्थान कॉलेज", "https://hte.rajasthan.gov.in/"),
    ("Rajasthan Government College Directory", "Education", "rajasthan government college list सरकारी कॉलेज सूची", "https://dceapp.rajasthan.gov.in/DCE_Application/DceWebCollegeList.aspx"),
    ("Rajasthan Technical University", "Education", "rtu kota technical university राजस्थान तकनीकी विश्वविद्यालय", "https://www.rtu.ac.in/"),
        ("Government College, Bali", "Education", "government college bali pali सरकारी कॉलेज बाली पाली", "https://dceapp.rajasthan.gov.in/DCE_Application/DceWebCollegeList.aspx"),
    ("Bangur Government P.G. College, Pali", "Education", "bangur college pali बांगड़ कॉलेज पाली", "https://dceapp.rajasthan.gov.in/DCE_Application/DceWebCollegeList.aspx"),
    ("Government College, Sumerpur", "Education", "government college sumerpur pali सरकारी कॉलेज सुमेरपुर", "https://dceapp.rajasthan.gov.in/DCE_Application/DceWebCollegeList.aspx"),
    ("Government College, Jaitaran", "Education", "government college jaitaran pali सरकारी कॉलेज जैतारण", "https://dceapp.rajasthan.gov.in/DCE_Application/DceWebCollegeList.aspx"),
    ("Rajasthan Government College List", "Education", "all government colleges rajasthan राजस्थान सरकारी कॉलेज सूची", "https://dceapp.rajasthan.gov.in/DCE_Application/DceWebCollegeList.aspx"),
    ("Mohanlal Sukhadia University (MLSU)", "Education", "mlsu mohanlal sukhadia university udaipur एमएलएसयू मोहनलाल सुखाड़िया विश्वविद्यालय", "https://mlsu.ac.in/"),
    ("Jai Narain Vyas University (JNVU)", "Education", "jnvu jai narain vyas university jodhpur जेएनवीयू जयनारायण व्यास विश्वविद्यालय", "https://jnvu.info/"),
    ("University of Kota", "Education", "uok kota university कोटा यूनिवर्सिटी विश्वविद्यालय", "https://uok.ac.in/"),
        ("Maharshi Dayanand Saraswati University (MDSU)", "Education", "mdsu ajmer university एमडीएसयू अजमेर", "https://mdsu.ac.in/"),
    ("MDSU Admission and Examination", "Education", "mdsu admission exam form परीक्षा फॉर्म", "https://mdsu.ac.in/"),
    ("MDSU Results", "Education", "mdsu result results रिजल्ट परिणाम", "https://mdsu.ac.in/"),

    ("University of Rajasthan Jaipur", "Education", "uniraj rajasthan university jaipur राजस्थान विश्वविद्यालय", "https://uniraj.ac.in/"),
    ("Rajasthan University Admission", "Education", "uniraj admission online form एडमिशन प्रवेश फॉर्म", "https://admissions.univraj.org/"),
    ("Rajasthan University Results", "Education", "uniraj results result रिजल्ट परिणाम", "https://results.uniraj.ac.in/"),

    ("MLSU Udaipur Admission and Examination", "Education", "mlsu udaipur admission examination form एमएलएसयू", "https://mlsuexamination.sumsraj.com/"),
    ("MLSU Results", "Education", "mlsu udaipur results result रिजल्ट", "https://mlsuexamination.sumsraj.com/"),

    ("JNVU Jodhpur Admission and Examination", "Education", "jnvu jodhpur admission examination form जेएनवीयू", "https://jnvu.info/"),
    ("JNVU Results", "Education", "jnvu jodhpur results result रिजल्ट", "https://jnvu.info/"),

    ("University of Kota Admission and Examination", "Education", "uok kota admission examination form कोटा यूनिवर्सिटी", "https://uok.ac.in/"),
    ("University of Kota Results", "Education", "uok kota university results result रिजल्ट", "https://uok.ac.in/"),

    ("Rajasthan Technical University Admission and Examination", "Education", "rtu kota admission examination form आरटीयू", "https://www.rtu.ac.in/"),
    ("Rajasthan Technical University Results", "Education", "rtu kota results result रिजल्ट", "https://www.rtu.ac.in/"),

    ("Maharaja Ganga Singh University (MGSU)", "Education", "mg su bikaner university एमजीएसयू बीकानेर", "https://mgsubikaner.ac.in/"),
    ("Vardhman Mahaveer Open University (VMOU)", "Education", "vmou kota open university वर्धमान महावीर खुला विश्वविद्यालय", "https://www.vmou.ac.in/"),
    ("Govind Guru Tribal University (GGTU)", "Education", "ggtu banswara tribal university गोविंद गुरु जनजातीय विश्वविद्यालय", "https://www.ggtu.ac.in/"),
    ("Shekhawati University", "Education", "pdusu sikar shekhawati university शेखावाटी विश्वविद्यालय", "https://www.shekhauni.ac.in/"),
        # SOCIAL MEDIA
    ("YouTube", "Social Media", "youtube video shorts यूट्यूब वीडियो", "https://www.youtube.com/"),
    ("Facebook", "Social Media", "facebook social media फेसबुक", "https://www.facebook.com/"),
    ("Instagram", "Social Media", "instagram reels photos इंस्टाग्राम", "https://www.instagram.com/"),
    ("WhatsApp", "Social Media", "whatsapp chat messaging व्हाट्सएप", "https://www.whatsapp.com/"),
    ("Telegram", "Social Media", "telegram messages groups टेलीग्राम", "https://telegram.org/"),
    ("X", "Social Media", "x twitter posts एक्स ट्विटर", "https://x.com/"),
    ("LinkedIn", "Social Media", "linkedin jobs professional लिंक्डइन", "https://www.linkedin.com/"),
    ("Pinterest", "Social Media", "pinterest photos ideas पिन्टरेस्ट", "https://www.pinterest.com/"),
    ("Reddit", "Social Media", "reddit discussions community रेडिट", "https://www.reddit.com/"),
    ("Snapchat", "Social Media", "snapchat stories snaps स्नैपचैट", "https://www.snapchat.com/"),
    ("Threads", "Social Media", "threads instagram text social थ्रेड्स", "https://www.threads.net/"),
    ("Discord", "Social Media", "discord chat gaming community डिस्कॉर्ड", "https://discord.com/"),
    ("Twitch", "Social Media", "twitch live streaming gaming लाइव स्ट्रीम", "https://www.twitch.tv/"),
    ("Tumblr", "Social Media", "tumblr blogging photos ब्लॉग", "https://www.tumblr.com/"),
    ("Mastodon", "Social Media", "mastodon decentralized social network", "https://joinmastodon.org/"),
    ("Bluesky", "Social Media", "bluesky social posts ब्लूस्काई", "https://bsky.app/"),
    ("Quora", "Social Media", "quora questions answers सवाल जवाब", "https://www.quora.com/"),
    ("Medium", "Social Media", "medium articles blogging लेख", "https://medium.com/"),
    ("Vimeo", "Social Media", "vimeo video hosting वीडियो", "https://vimeo.com/"),
    ("Dailymotion", "Social Media", "dailymotion videos वीडियो", "https://www.dailymotion.com/"),
    ("SoundCloud", "Social Media", "soundcloud music audio संगीत", "https://soundcloud.com/"),
    ("Spotify", "Social Media", "spotify music podcasts गाने पॉडकास्ट", "https://open.spotify.com/"),
    ("Behance", "Social Media", "behance creative portfolio design", "https://www.behance.net/"),
    ("Dribbble", "Social Media", "dribbble design creative designers", "https://dribbble.com/"),
    ("Flickr", "Social Media", "flickr photography photos फोटोग्राफी", "https://www.flickr.com/"),
    ("Product Hunt", "Technology", "product hunt new apps startups", "https://www.producthunt.com/"),
    ("GitLab", "Technology", "gitlab coding software development", "https://gitlab.com/"),
    ("CodePen", "Technology", "codepen web design html css javascript", "https://codepen.io/"),
    ("Replit", "Technology", "replit online coding programming", "https://replit.com/"),
    ("Kaggle", "Technology", "kaggle datasets machine learning data", "https://www.kaggle.com/"),
    # GOOGLE SERVICES
    ("Google", "Technology", "google search गूगल सर्च", "https://www.google.com/"),
    ("Gmail", "Technology", "gmail email जीमेल ईमेल", "https://mail.google.com/"),
    ("Google Maps", "Technology", "google maps location directions रास्ता", "https://maps.google.com/"),
    ("Google Drive", "Technology", "google drive files storage फाइल", "https://drive.google.com/"),
    ("Google Translate", "Education", "google translate hindi english अनुवाद", "https://translate.google.com/"),
    ("Google Meet", "Technology", "google meet online meeting वीडियो मीटिंग", "https://meet.google.com/"),

    # AI TOOLS
    ("ChatGPT", "AI Tools", "chatgpt artificial intelligence एआई", "https://chatgpt.com/"),
    ("Google Gemini", "AI Tools", "google gemini ai assistant जेमिनी", "https://gemini.google.com/"),
    ("Microsoft Copilot", "AI Tools", "microsoft copilot ai कोपायलट", "https://copilot.microsoft.com/"),

    # DESIGN AND CREATION
    ("Canva", "Design", "canva poster logo design कैनवा", "https://www.canva.com/"),
    ("Adobe Express", "Design", "adobe express photo poster design", "https://www.adobe.com/express/"),
    ("CapCut", "Video Tools", "capcut video editing वीडियो एडिटिंग", "https://www.capcut.com/"),

    # CODING AND TECHNOLOGY
    ("GitHub", "Technology", "github coding programming गिटहब", "https://github.com/"),
    ("Stack Overflow", "Technology", "stack overflow programming coding", "https://stackoverflow.com/"),
    ("Python", "Technology", "python programming language पाइथन", "https://www.python.org/"),

    # GOVERNMENT AND PUBLIC INFORMATION
    ("India Government Web Directory", "Government", "official government websites india सरकारी वेबसाइट", "https://igod.gov.in/"),
    ("MyGov India", "Government", "mygov india government schemes सरकारी योजनाएं", "https://www.mygov.in/"),
    ("National Cyber Crime Reporting Portal", "Safety", "cyber crime complaint online fraud साइबर शिकायत", "https://cybercrime.gov.in/"),
    ("Rajasthan Single Sign On", "Rajasthan", "sso login राजस्थान", "https://sso.rajasthan.gov.in/"),

    ("UIDAI Aadhaar", "Government", "aadhaar aadhar आधार uidai", "https://uidai.gov.in/"),
    ("My Aadhaar", "Government", "download aadhaar आधार डाउनलोड", "https://myaadhaar.uidai.gov.in/"),
    ("Income Tax e-Filing", "Government", "income tax pan आयकर पैन", "https://www.incometax.gov.in/"),
    ("PAN Services NSDL Protean", "Government", "pan card पैन कार्ड", "https://www.protean-tinpan.com/"),
    ("DigiLocker", "Government", "digilocker documents दस्तावेज", "https://www.digilocker.gov.in/"),
    ("UMANG", "Government", "umang government services सरकारी सेवा", "https://web.umang.gov.in/"),
    ("National Scholarship Portal", "Education", "scholarship छात्रवृत्ति स्कॉलरशिप", "https://scholarships.gov.in/"),
    ("National Portal of India", "Government", "india government भारत सरकार", "https://www.india.gov.in/"),
    ("MyScheme", "Government", "scheme yojana सरकारी योजना", "https://www.myscheme.gov.in/"),
    ("Public Grievances Portal", "Government", "pgportal complaint grievance शिकायत", "https://pgportal.gov.in/"),
    ("National Consumer Helpline", "Safety", "consumer complaint ग्राहक शिकायत", "https://consumerhelpline.gov.in/"),
    ("Cyber Crime Reporting Portal", "Safety", "cyber crime fraud online fraud साइबर ठगी", "https://cybercrime.gov.in/"),
    ("eCourts Services", "Legal", "ecourts court case अदालत केस", "https://ecourts.gov.in/"),
    ("India Code", "Legal", "india code law कानून अधिनियम", "https://www.indiacode.nic.in/"),
    ("National Legal Services Authority", "Legal", "nalsa legal aid मुफ्त कानूनी सहायता", "https://nalsa.gov.in/"),
    ("Passport Seva", "Government", "passport पासपोर्ट", "https://www.passportindia.gov.in/"),
    ("Voter Services", "Government", "voter id election वोटर कार्ड", "https://voters.eci.gov.in/"),
    ("Election Commission of India", "Government", "election चुनाव", "https://www.eci.gov.in/"),
    ("EPFO", "Government", "epfo pf provident fund पीएफ", "https://www.epfindia.gov.in/"),
    ("ESIC", "Government", "esic employee insurance", "https://www.esic.gov.in/"),
    ("Public Distribution System", "Government", "ration card राशन कार्ड", "https://nfsa.gov.in/"),
    ("PM Kisan", "Government", "pm kisan farmer किसान सम्मान निधि", "https://pmkisan.gov.in/"),
    ("eShram", "Government", "eshram labour श्रमिक कार्ड", "https://eshram.gov.in/"),
    ("Ayushman Bharat PM-JAY", "Health", "ayushman bharat आयुष्मान कार्ड", "https://pmjay.gov.in/"),
    ("ABHA Health Account", "Health", "abha health account स्वास्थ्य", "https://abha.abdm.gov.in/"),
    ("Ministry of Health", "Health", "health ministry स्वास्थ्य मंत्रालय", "https://mohfw.gov.in/"),
    ("CoWIN", "Health", "cowin vaccine टीकाकरण", "https://www.cowin.gov.in/"),
    ("Bharat BillPay", "Payments", "bill payment बिजली बिल", "https://www.bharatbillpay.com/"),
    ("National Scholarship Information", "Education", "scholarships education छात्रवृत्ति", "https://www.education.gov.in/"),
    ("AICTE", "Education", "aicte technical education", "https://www.aicte-india.org/"),
    ("UGC", "Education", "ugc university कॉलेज", "https://www.ugc.gov.in/"),
    ("National Testing Agency", "Education", "nta exam परीक्षा", "https://nta.ac.in/"),
    ("CBSE", "Education", "cbse school result बोर्ड", "https://www.cbse.gov.in/"),
    ("NCERT", "Education", "ncert books textbook किताबें", "https://ncert.nic.in/"),
    ("National Digital Library", "Education", "digital library किताबें अध्ययन", "https://ndl.iitkgp.ac.in/"),
    ("SWAYAM", "Education", "swayam online course पढ़ाई", "https://swayam.gov.in/"),
    ("Khan Academy", "Education", "khan academy maths science सीखें", "https://www.khanacademy.org/"),
    ("NCVT MIS", "ITI", "ncvt iti mis आईटीआई", "https://www.ncvtmis.gov.in/"),
    ("Skill India Digital Hub", "ITI", "skill india sidh कौशल प्रशिक्षण", "https://www.skillindiadigital.gov.in/"),
    ("Apprenticeship India", "ITI Jobs", "apprenticeship apprentice अप्रेंटिस", "https://www.apprenticeshipindia.gov.in/"),
    ("Directorate General of Training", "ITI", "dgt iti fitter training", "https://dgt.gov.in/"),
    ("AICTE Internship Portal", "Jobs", "internship student इंटर्नशिप", "https://internship.aicte-india.org/"),
]

RAW_SERVICES += [
    ("Google Search", "Search", "google web search इंटरनेट खोज", "https://www.google.com/"),
    ("Bing Search", "Search", "bing web search", "https://www.bing.com/"),
    ("DuckDuckGo", "Search", "duckduckgo private search", "https://duckduckgo.com/"),
    ("Wikipedia Hindi", "Learning", "wikipedia knowledge जानकारी", "https://hi.wikipedia.org/"),
    ("Google Translate", "Tools", "translate language अनुवाद", "https://translate.google.com/"),
    ("Google Maps", "Maps", "maps map रास्ता नक्शा", "https://maps.google.com/"),
    ("OpenStreetMap", "Maps", "openstreetmap map नक्शा", "https://www.openstreetmap.org/"),
    ("Google Drive", "Files", "drive cloud file storage", "https://drive.google.com/"),
    ("Microsoft OneDrive", "Files", "onedrive cloud files", "https://onedrive.live.com/"),
    ("Adobe Acrobat Online", "PDF", "pdf merge convert पीडीएफ", "https://www.adobe.com/acrobat/online.html"),
    ("Canva", "Design", "canva poster design पोस्टर", "https://www.canva.com/"),
    ("Photopea", "Image", "photopea photo image editor फोटो", "https://www.photopea.com/"),
    ("Remove.bg", "Image", "remove background background remover", "https://www.remove.bg/"),
    ("Unsplash", "Image", "unsplash photos तस्वीर", "https://unsplash.com/"),
    ("Pexels", "Media", "pexels free photos videos", "https://www.pexels.com/"),
    ("Pixabay", "Media", "pixabay images videos", "https://pixabay.com/"),
    ("YouTube", "Video", "youtube video वीडियो", "https://www.youtube.com/"),
    ("Google News", "News", "news समाचार खबर", "https://news.google.com/"),
    ("BBC Hindi", "News", "bbc hindi news समाचार", "https://www.bbc.com/hindi"),
    ("DD News", "News", "dd news india समाचार", "https://ddnews.gov.in/"),
    ("PIB India", "News", "pib press information bureau सरकारी समाचार", "https://pib.gov.in/"),
    ("ChatGPT", "AI", "chatgpt artificial intelligence एआई चैट", "https://chatgpt.com/"),
    ("Google Gemini", "AI", "gemini google ai", "https://gemini.google.com/"),
    ("Microsoft Copilot", "AI", "copilot microsoft ai", "https://copilot.microsoft.com/"),
    ("Claude", "AI", "claude ai assistant", "https://claude.ai/"),
    ("Perplexity", "AI", "perplexity ai answer search", "https://www.perplexity.ai/"),
    ("Hugging Face", "AI", "huggingface machine learning models", "https://huggingface.co/"),
    ("GitHub", "Technology", "github coding code repository", "https://github.com/"),
    ("GitLab", "Technology", "gitlab source code development", "https://gitlab.com/"),
    ("Stack Overflow", "Technology", "programming coding questions", "https://stackoverflow.com/"),
    ("Python", "Technology", "python programming language", "https://www.python.org/"),
    ("MDN Web Docs", "Technology", "html css javascript web development", "https://developer.mozilla.org/"),
    ("W3Schools", "Learning", "html css javascript coding सीखें", "https://www.w3schools.com/"),
    ("CodePen", "Technology", "codepen html css javascript", "https://codepen.io/"),
    ("Replit", "Technology", "replit online coding", "https://replit.com/"),
    ("FreeCodeCamp", "Learning", "free coding course programming", "https://www.freecodecamp.org/"),
    ("Coursera", "Learning", "coursera online course", "https://www.coursera.org/"),
    ("edX", "Learning", "edx online courses", "https://www.edx.org/"),
    ("Google Trends", "Tools", "google trends trending topics", "https://trends.google.com/"),
    ("Internet Archive", "Learning", "archive books website history", "https://archive.org/"),
    ("India Post", "Government", "india post post office डाक", "https://www.indiapost.gov.in/"),
    ("IRCTC", "Railway", "irctc train ticket रेलवे टिकट", "https://www.irctc.co.in/"),
    ("National Highways Authority", "Transport", "nhai highway road", "https://nhai.gov.in/"),
    ("Parivahan", "Transport", "driving licence vehicle आरसी लाइसेंस", "https://parivahan.gov.in/"),
    ("VAHAN", "Transport", "vahan vehicle registration", "https://vahan.parivahan.gov.in/"),
    ("Sarathi", "Transport", "sarathi driving licence", "https://sarathi.parivahan.gov.in/"),
    ("Bhuvan ISRO", "Maps", "bhuvan satellite map isro", "https://bhuvan.nrsc.gov.in/"),
    ("ISRO", "Science", "isro space science", "https://www.isro.gov.in/"),
    ("DRDO", "Jobs", "drdo defence research recruitment", "https://www.drdo.gov.in/"),
    ("BHEL", "Jobs", "bhel recruitment apprentice", "https://www.bhel.com/"),
    ("ONGC", "Jobs", "ongc recruitment careers", "https://ongcindia.com/"),
    ("Indian Oil", "Jobs", "indian oil recruitment apprentice", "https://iocl.com/"),
    ("Bharat Petroleum", "Jobs", "bpcl careers recruitment", "https://www.bharatpetroleum.in/"),
    ("Coal India", "Jobs", "coal india recruitment", "https://www.coalindia.in/"),
    ("AAI", "Jobs", "airport authority recruitment", "https://www.aai.aero/"),
    ("NABARD", "Jobs", "nabard agriculture bank recruitment", "https://www.nabard.org/"),
    ("RBI", "Finance", "rbi reserve bank india", "https://www.rbi.org.in/"),
    ("SEBI", "Finance", "sebi securities market", "https://www.sebi.gov.in/"),
    ("National Stock Exchange", "Finance", "nse stock market", "https://www.nseindia.com/"),
    ("Bombay Stock Exchange", "Finance", "bse stock market", "https://www.bseindia.com/"),
    ("Startup India", "Business", "startup business उद्यम", "https://www.startupindia.gov.in/"),
    ("Udyam Registration", "Business", "udyam msme registration उद्योग", "https://udyamregistration.gov.in/"),
    ("GeM Portal", "Business", "gem government e marketplace tender", "https://gem.gov.in/"),
    ("GST Portal", "Business", "gst goods services tax", "https://www.gst.gov.in/"),
    ("MCA Portal", "Business", "mca company registration", "https://www.mca.gov.in/"),
    ("e-NAM", "Agriculture", "enam mandi farmer कृषि मंडी", "https://enam.gov.in/"),
    ("Agriculture Ministry", "Agriculture", "agriculture किसान कृषि", "https://agriwelfare.gov.in/"),
    ("PM Fasal Bima Yojana", "Agriculture", "fasal bima crop insurance फसल बीमा", "https://pmfby.gov.in/"),
    ("Soil Health Card", "Agriculture", "soil health card मिट्टी", "https://soilhealth.dac.gov.in/"),
    ("Jal Jeevan Mission", "Government", "jal jeevan mission water पानी", "https://jaljeevanmission.gov.in/"),
    ("Swachh Bharat Mission", "Government", "swachh bharat cleanliness स्वच्छता", "https://swachhbharatmission.ddws.gov.in/"),
    ("National Health Mission", "Health", "nhm health mission", "https://nhm.gov.in/"),
    ("Food Safety Authority", "Health", "fssai food safety खाद्य सुरक्षा", "https://www.fssai.gov.in/"),
    ("National Disaster Management Authority", "Safety", "ndma disaster emergency आपदा", "https://ndma.gov.in/"),
    ("India Meteorological Department", "Weather", "imd weather forecast मौसम", "https://mausam.imd.gov.in/"),
    ("National Portal for Disaster Alerts", "Safety", "disaster alert emergency चेतावनी", "https://sachet.ndma.gov.in/"),
]

def normalize(value):
    value = str(value or "").lower().strip()
    value = value.replace("आधार", "aadhaar")
    value = value.replace("छात्रवृत्ति", "scholarship")
    value = value.replace("राजस्थान", "rajasthan")
    value = value.replace("रेलवे", "railway")
    value = value.replace("नौकरी", "job")
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def build_services():
    result = []
    seen = set()

    for name, category, keywords, url in RAW_SERVICES:
        if url in seen:
            continue
        if not url.startswith("https://"):
            continue

        seen.add(url)
        result.append({
            "name": name,
            "category": category,
            "keywords": keywords,
            "url": url
        })

    # Extra services from services.json, if that file exists.
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
                    if not name or not url.startswith("https://") or url in seen:
                        continue
                    seen.add(url)
                    result.append({
                        "name": name[:120],
                        "category": str(item.get("category", "Other"))[:60],
                        "keywords": str(item.get("keywords", ""))[:500],
                        "url": url
                    })
        except (OSError, json.JSONDecodeError):
            app.logger.warning("services.json could not be read")

    return result


SERVICES = build_services()


def search_services(query):
    q = normalize(query)
    if not q:
        return []


    aliases = {
        "railway": "rail train rrb railway रेलवे",
        "scholarship": "scholarship छात्रवृत्ति",
        "aadhaar": "aadhaar aadhar आधार uidai",
        "aadhar": "aadhaar aadhar आधार uidai",
        "rajasthan": "rajasthan राजस्थान rpsc rssb sso",
        "jobs": "job jobs career recruitment भर्ती नौकरी",
        "iti": "iti ncvt fitter apprentice",
        "fitter": "fitter iti ncvt apprentice",
        "pan": "pan card income tax",
        "police": "police राजस्थान पुलिस",
        "news": "news समाचार pib bbc",
        "ai": "ai artificial intelligence chatgpt gemini",
        "map": "map maps नक्शा google",
    }

    expanded = aliases.get(q, q)
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
        if q in name:
            score += 60
        if q in category:
            score += 20
        if q in keywords:
            score += 25
        if q in url:
            score += 10

        matched = sum(1 for term in terms if term and term in searchable)
        score += matched * 5

        if score > 0:
            ranked.append((score, service))

    ranked.sort(key=lambda pair: (-pair[0], pair[1]["name"].lower()))
    return [service for _, service in ranked[:50]]
# Smart Search Suggestions — existing services are preserved
SMART_SUGGESTIONS = [
    {
        "name": "Railway Recruitment Boards (RRB)",
        "category": "Railway Jobs",
        "keywords": "railway rrb recruitment vacancy railway jobs भर्ती",
        "url": "https://www.rrbapply.gov.in/"
    },
    {
        "name": "Indian Railways",
        "category": "Railway",
        "keywords": "railway train रेलगाड़ी railway information",
        "url": "https://indianrailways.gov.in/"
    },
    {
        "name": "IRCTC Train Ticket Booking",
        "category": "Railway",
        "keywords": "train ticket booking reservation irctc टिकट",
        "url": "https://www.irctc.co.in/"
    },
    {
        "name": "National Train Enquiry System",
        "category": "Railway",
        "keywords": "train status running status train enquiry",
        "url": "https://enquiry.indianrail.gov.in/"
    },
    {
        "name": "RRB NTPC Recruitment",
        "category": "Railway Jobs",
        "keywords": "rrb ntpc graduate undergraduate 12th exam",
        "url": "https://www.rrbapply.gov.in/"
    },
    {
        "name": "Railway ALP Recruitment",
        "category": "Railway Jobs",
        "keywords": "alp assistant loco pilot railway exam",
        "url": "https://www.rrbapply.gov.in/"
    },
    {
        "name": "Railway Group D Recruitment",
        "category": "Railway Jobs",
        "keywords": "group d level 1 railway vacancy",
        "url": "https://www.rrbapply.gov.in/"
    },
    {
        "name": "Railway Technician Recruitment",
        "category": "Railway Jobs",
        "keywords": "technician railway fitter iti recruitment",
        "url": "https://www.rrbapply.gov.in/"
    },
    {
        "name": "RRC North Western Railway",
        "category": "Railway Jobs",
        "keywords": "rrc nwr jaipur apprentice railway राजस्थान",
        "url": "https://nwr.indianrailways.gov.in/"
    },
    {
        "name": "National Career Service",
        "category": "Jobs",
        "keywords": "government private job employment नौकरी",
        "url": "https://www.ncs.gov.in/"
    },
    {
        "name": "Apprenticeship India",
        "category": "ITI Jobs",
        "keywords": "iti fitter apprenticeship apprentice अप्रेंटिस",
        "url": "https://www.apprenticeshipindia.gov.in/"
    },
    {
        "name": "NCVT MIS",
        "category": "ITI",
        "keywords": "iti ncvt marksheet certificate pntc fitter",
        "url": "https://www.ncvtmis.gov.in/"
    },
    {
        "name": "Skill India Digital Hub",
        "category": "ITI",
        "keywords": "sidh skill india iti training कौशल",
        "url": "https://www.skillindiadigital.gov.in/"
    },
    {
        "name": "Staff Selection Commission",
        "category": "Jobs",
        "keywords": "ssc government job recruitment परीक्षा",
        "url": "https://ssc.gov.in/"
    },
    {
        "name": "Rajasthan Staff Selection Board",
        "category": "Rajasthan Jobs",
        "keywords": "rssb rsmssb राजस्थान भर्ती",
        "url": "https://rssb.rajasthan.gov.in/"
    },
    {
        "name": "Rajasthan Public Service Commission",
        "category": "Rajasthan Jobs",
        "keywords": "rpsc राजस्थान सरकारी भर्ती",
        "url": "https://rpsc.rajasthan.gov.in/"
    },
    {
        "name": "National Scholarship Portal",
        "category": "Education",
        "keywords": "scholarship student छात्रवृत्ति",
        "url": "https://scholarships.gov.in/"
    },
    {
        "name": "Rajasthan Sampark Complaints",
        "category": "Complaints",
        "keywords": "complaint shikayat sampark राजस्थान शिकायत",
        "url": "https://sampark.rajasthan.gov.in/"
    },
    {
        "name": "National Consumer Helpline",
        "category": "Complaints",
        "keywords": "consumer complaint customer ग्राहक शिकायत",
        "url": "https://consumerhelpline.gov.in/"
    },
    {
        "name": "National Cyber Crime Reporting Portal",
        "category": "Safety",
        "keywords": "online fraud cyber crime scam साइबर ठगी",
        "url": "https://cybercrime.gov.in/"
    },
]


def get_suggestions(query, limit=10):
    """Return relevant suggestions without changing the main search."""
    q = normalize(query)

    if len(q) < 2:
        return []

    # Existing services and new suggestions are combined.
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
            score += 55
        if q in category:
            score += 30
        if q in keywords:
            score += 25

        query_terms = q.split()
        score += sum(
            8 for term in query_terms
            if len(term) > 1 and term in searchable
        )

        if score > 0:
            ranked.append((score, service))

    ranked.sort(key=lambda item: (-item[0], item[1]["name"].lower()))

    return [
        {
            "name": service["name"],
            "category": service["category"],
            "url": service["url"]
        }
        for _, service in ranked[:limit]
    ]


@app.route("/api/suggestions")
def api_suggestions():
    query = request.args.get("q", "").strip()[:160]
    return jsonify({
        "success": True,
        "query": query,
        "results": get_suggestions(query)
    })
RSS_FEEDS = [
    ("Google News India", "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi"),
    ("PIB India", "https://pib.gov.in/RssMain.aspx"),
    ("BBC Hindi", "https://feeds.bbci.co.uk/hindi/rss.xml"),
]


def fetch_news(limit=15):
    articles = []

    for source, url in RSS_FEEDS:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "IshwarSearch/1.0"}
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                root = ET.fromstring(response.read())

            for item in root.findall(".//item"):
                title = html.unescape(item.findtext("title", "")).strip()
                link = item.findtext("link", "").strip()
                date = item.findtext("pubDate", "").strip()

                if title and link.startswith("https://"):
                    articles.append({
                        "title": title,
                        "url": link,
                        "source": source,
                        "date": date
                    })

                if len(articles) >= limit:
                    return articles

        except Exception:
            app.logger.info("News source unavailable: %s", source)

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
        categories=sorted({s["category"] for s in SERVICES}),
        current_year=datetime.now().year,
        owner=OWNER,
        app_name=APP_NAME
    )


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()[:160]
    results = search_services(query)

    return jsonify({
        "success": True,
        "query": query,
        "count": len(results),
        "results": results
    })


@app.route("/api/news")
def api_news():
    return jsonify({
        "success": True,
        "results": fetch_news()
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": APP_NAME,
        "owner": OWNER,
        "services": len(SERVICES)
    })


if __name__ == "__main__":
    print("=" * 42)
    print(f"{APP_NAME} is starting")
    print(f"Owner: {OWNER}")
    print(f"Services loaded: {len(SERVICES)}")
    print("Open http://127.0.0.1:5000")
    print("=" * 42)

    app.run(host="127.0.0.1", port=5000, debug=True)
