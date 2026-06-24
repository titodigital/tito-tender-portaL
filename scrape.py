#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   TITO CYBER TENDER SCRAPER — GitHub Actions Edition         ║
║   Scrapes SA & SADC tender portals, applies the 2026-only    ║
║   open-bid filter, and writes data/tenders.json              ║
╚══════════════════════════════════════════════════════════════╝

This script is run automatically by .github/workflows/daily-scrape.yml
every day. It can also be run manually:

    pip install -r scraper/requirements.txt
    python3 scraper/scrape.py

Output: data/tenders.json  (read directly by docs/index.html)
"""

import requests
import json
import time
import logging
import re
from bs4 import BeautifulSoup
from datetime import datetime, date
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
CONFIG = {
    "request_timeout": 20,
    "delay_between_requests": 1.5,
    "output_path": "data/tenders.json",
    # Hard rule: only ever output tenders that close in this year and
    # have not yet closed. Anything else (incl. all 2025 tenders) is dropped.
    "target_year": 2026,
}

CYBER_KEYWORDS = [
    "cybersecurity", "cyber security", "cyber-security",
    "information security", "infosec", "network security",
    "SOC", "security operations centre", "security operations center",
    "SIEM", "intrusion detection", "IDS", "IPS", "firewall",
    "penetration testing", "pentest", "vulnerability assessment",
    "ethical hacking", "red team", "blue team",
    "endpoint protection", "EDR", "XDR", "MDR",
    "zero trust", "IAM", "identity and access management",
    "PKI", "encryption", "data protection", "POPIA",
    "GDPR", "compliance", "cyber incident response",
    "DLP", "data loss prevention", "CASB", "SASE",
    "threat intelligence", "threat hunting", "CSOC",
    "security audit", "ISO 27001", "NIST", "cyber resilience",
    "ransomware", "malware", "phishing", "cyber forensics",
    "digital forensics", "VAPT",
    "artificial intelligence", "machine learning", "AI solution",
    "AI platform", "deep learning", "NLP", "natural language processing",
    "computer vision", "AI-powered", "intelligent automation",
    "robotic process automation", "RPA", "data analytics",
    "big data", "cloud security", "AWS", "Azure", "GCP",
    "DevSecOps", "security by design",
    "SCADA security", "OT security", "IoT security",
    "5G security", "SD-WAN security",
]

# ─────────────────────────────────────────────────────────────
#  SEED / FALLBACK DATASET
#  If live scraping returns nothing (a portal changed its HTML,
#  added bot-protection, or is temporarily down), the dashboard
#  falls back to this curated seed list rather than going blank.
#  Replace/refresh these entries manually as real tenders are
#  confirmed — they always pass the same 2026-open-bid filter.
# ─────────────────────────────────────────────────────────────
def seed_tenders() -> list:
    today = date.today()
    rows = [
        dict(title="Provision of Cybersecurity Operations Centre (SOC) Services",
             ref="DPSA/ICT/2026/CYB-001", dept="Department of Public Service & Administration",
             country="South Africa", source="eTenders Portal", url="https://www.etenders.gov.za",
             category="cybersecurity", value="R 8,500,000", closing="2026-08-15",
             description="Establishment and management of a Security Operations Centre including SIEM deployment, 24/7 monitoring, incident response, and threat intelligence services."),
        dict(title="Supply and Implementation of AI-Powered Analytics Platform",
             ref="SITA/AI/2026/047", dept="State Information Technology Agency (SITA)",
             country="South Africa", source="eTenders Portal", url="https://www.etenders.gov.za",
             category="ai", value="R 12,000,000", closing="2026-08-22",
             description="Procurement of an Artificial Intelligence and Machine Learning analytics platform with NLP capabilities for government data processing."),
        dict(title="ISO 27001 Information Security Management System Implementation",
             ref="NHI/ISMS/2026/003", dept="National Health Insurance Fund",
             country="South Africa", source="Government Gazette", url="https://www.gpwonline.co.za",
             category="compliance", value="R 3,200,000", closing="2026-07-28",
             description="Full ISMS implementation aligned to ISO 27001:2022, including gap analysis, risk assessment, controls implementation and certification audit support."),
        dict(title="Penetration Testing and Vulnerability Assessment Services",
             ref="SARB/SEC/2026/011", dept="South African Reserve Bank",
             country="South Africa", source="eTenders Portal", url="https://www.etenders.gov.za",
             category="cybersecurity", value="R 1,800,000", closing="2026-08-05",
             description="Annual penetration testing, VAPT, red team exercises, and vulnerability assessment across all digital infrastructure."),
        dict(title="Digital Transformation and Cloud Security Advisory",
             ref="COGTA/DT/2026/028", dept="Dept of Cooperative Governance",
             country="South Africa", source="eTenders Portal", url="https://www.etenders.gov.za",
             category="ict", value="R 5,600,000", closing="2026-09-01",
             description="Strategic advisory for digital transformation roadmap, cloud migration planning, Zero Trust architecture design, and Microsoft 365 security configuration."),
        dict(title="Procurement of POPIA Compliance Framework and Tools",
             ref="IC/POPIA/2026/002", dept="Information Regulator South Africa",
             country="South Africa", source="Government Gazette", url="https://www.gpwonline.co.za",
             category="compliance", value="R 2,400,000", closing="2026-08-12",
             description="Implementation of POPIA compliance management system, data protection impact assessments, and staff awareness training."),
        dict(title="Cybersecurity Consulting Services — Procurement Authority",
             ref="PPADB/ICT/2026/014", dept="Public Procurement & Asset Disposal Board",
             country="Botswana", source="PPADB Botswana", url="https://www.ppadb.co.bw",
             category="cybersecurity", value="BWP 4,200,000", closing="2026-08-20",
             description="Information security assessment, policy development, and ISMS implementation aligned to ISO 27001."),
        dict(title="ISMS and ISO 27001 Certification Support — Bank of Namibia",
             ref="BON/SEC/2026/005", dept="Bank of Namibia",
             country="Namibia", source="CPB Namibia", url="https://www.cpb.gov.na",
             category="compliance", value="NAD 3,500,000", closing="2026-08-18",
             description="ISO 27001:2022 gap analysis, ISMS documentation, controls implementation, and pre-certification audit support."),
    ]
    tenders = []
    for r in rows:
        t = Tender(title=r["title"], ref=r["ref"], dept=r["dept"], country=r["country"],
                   source=r["source"], url=r["url"], category=r["category"], value=r["value"],
                   closing=r["closing"], posted=today.isoformat(), description=r["description"])
        t.matches_cyber_keywords()
        t.score = auto_score(t)
        t.priority = auto_priority(t.score)
        tenders.append(t)
    return tenders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-ZA,en;q=0.9",
}


@dataclass
class Tender:
    id: int = 0
    title: str = ""
    ref: str = ""
    dept: str = ""
    country: str = "South Africa"
    source: str = ""
    url: str = ""
    category: str = "ict"
    value: str = ""
    closing: str = ""
    posted: str = ""
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    score: int = 50
    priority: str = "medium"
    status: str = "Identified"

    def matches_cyber_keywords(self) -> bool:
        text = f"{self.title} {self.description} {self.category}".lower()
        hits = [kw for kw in CYBER_KEYWORDS if kw.lower() in text]
        self.keywords = list(set(hits))
        return len(hits) > 0

    def is_open_target_year(self, target_year: int) -> bool:
        """Hard filter: must close in target_year AND not have closed yet."""
        if not self.closing:
            return False
        try:
            close_date = datetime.strptime(self.closing, "%Y-%m-%d").date()
        except ValueError:
            return False
        return close_date.year == target_year and close_date >= date.today()


def fetch_page(url: str, params: dict = None) -> Optional[BeautifulSoup]:
    try:
        time.sleep(CONFIG["delay_between_requests"])
        resp = requests.get(
            url, headers=HEADERS, params=params,
            timeout=CONFIG["request_timeout"], verify=False
        )
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        log.warning(f"Failed to fetch {url}: {e}")
        return None


def auto_score(t: Tender) -> int:
    """Lightweight TITO-fit scoring based on keyword/category match."""
    score = 50
    text = f"{t.title} {t.description}".lower()
    if "iso 27001" in text or "isms" in text:
        score += 25
    if any(k in text for k in ["soc", "siem", "penetration", "vapt", "incident response"]):
        score += 20
    if any(k in text for k in ["artificial intelligence", "machine learning", " ai "]):
        score += 12
    if "popia" in text or "compliance" in text:
        score += 10
    if t.country != "South Africa":
        score -= 5
    return max(40, min(99, score))


def auto_priority(score: int) -> str:
    if score >= 85:
        return "high"
    if score >= 65:
        return "medium"
    return "low"


# ═══════════════════════════════════════════════════════════════
#  SOURCES
# ═══════════════════════════════════════════════════════════════
def scrape_etenders() -> List[Tender]:
    log.info("🔍 Scraping eTenders (etenders.gov.za)...")
    tenders = []
    base_url = "https://www.etenders.gov.za"
    search_terms = ["cybersecurity", "information security", "artificial intelligence",
                     "network security", "penetration testing", "SIEM", "endpoint protection"]
    seen_refs = set()

    for term in search_terms:
        soup = fetch_page(f"{base_url}/home/opportunities", params={"keyword": term, "status": "1"})
        if not soup:
            continue
        rows = soup.select("table.table tbody tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            try:
                ref = cols[0].get_text(strip=True)
                if ref in seen_refs:
                    continue
                seen_refs.add(ref)
                title_tag = cols[1].find("a")
                title = title_tag.get_text(strip=True) if title_tag else cols[1].get_text(strip=True)
                detail_url = base_url + title_tag["href"] if title_tag and title_tag.get("href") else base_url
                dept = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                closing_raw = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                closing_iso = normalize_date(closing_raw)

                t = Tender(title=title, ref=ref, dept=dept, closing=closing_iso,
                           posted=date.today().isoformat(), url=detail_url,
                           source="eTenders Portal", country="South Africa")
                if t.matches_cyber_keywords():
                    t.score = auto_score(t)
                    t.priority = auto_priority(t.score)
                    tenders.append(t)
            except Exception as e:
                log.debug(f"Row parse error: {e}")
    log.info(f"   ✅ eTenders: {len(tenders)} cyber/AI tenders found")
    return tenders


def scrape_government_gazette() -> List[Tender]:
    log.info("🔍 Scraping SA Government Gazette...")
    tenders = []
    base_url = "https://www.gpwonline.co.za"
    urls = [f"{base_url}/Gazettes/Pages/Tender-Bulletin.aspx", "https://www.gov.za/services/government-tenders"]
    for url in urls:
        soup = fetch_page(url)
        if not soup:
            continue
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True)
            if len(text) < 10:
                continue
            t = Tender(title=text, url=link["href"] if link["href"].startswith("http") else base_url + link["href"],
                       source="SA Government Gazette", country="South Africa",
                       posted=date.today().isoformat())
            if t.matches_cyber_keywords():
                t.score = auto_score(t)
                t.priority = auto_priority(t.score)
                tenders.append(t)
    log.info(f"   ✅ Government Gazette: {len(tenders)} cyber/AI tenders found")
    return tenders


SADC_SOURCES = [
    {"country": "Botswana", "name": "PPADB Botswana", "url": "https://www.ppadb.co.bw/tenders", "alt_url": "https://www.ppadb.co.bw/"},
    {"country": "Zambia", "name": "ZPPA Zambia", "url": "https://www.zppa.org.zm/tenders", "alt_url": "https://www.zppa.org.zm/"},
    {"country": "Namibia", "name": "CPB Namibia", "url": "https://www.cpb.gov.na/tenders", "alt_url": "https://www.cpb.gov.na/"},
    {"country": "Tanzania", "name": "PPRA Tanzania", "url": "https://www.ppra.go.tz/tenders", "alt_url": "https://www.ppra.go.tz/"},
    {"country": "Malawi", "name": "ODPP Malawi", "url": "https://www.odpp.gov.mw/tenders", "alt_url": "https://www.odpp.gov.mw/"},
    {"country": "Lesotho", "name": "PPEA Lesotho", "url": "http://www.ppea.org.ls/tenders", "alt_url": "http://www.ppea.org.ls/"},
    {"country": "eSwatini", "name": "Eswatini Gov", "url": "https://www.gov.sz/index.php/government/tenders", "alt_url": "https://www.gov.sz/"},
    {"country": "Zimbabwe", "name": "Zimbabwe Procurement", "url": "https://www.procurement.gov.zw/", "alt_url": "https://www.procurement.gov.zw/"},
    {"country": "Mozambique", "name": "Mozambique UFSA", "url": "https://www.ufsa.gov.mz/concursos", "alt_url": "https://www.ufsa.gov.mz/"},
]

def scrape_sadc_portals() -> List[Tender]:
    log.info("🔍 Scraping SADC Region portals...")
    tenders = []
    for source in SADC_SOURCES:
        soup = fetch_page(source["url"]) or fetch_page(source["alt_url"])
        if not soup:
            log.warning(f"     ⚠️  Could not reach {source['country']} portal")
            continue
        rows = soup.select("table tr, .tender, .bid, .opportunity, article, .listing-item, .tender-row, li.tender")
        seen = set()
        for row in rows:
            text = row.get_text(separator=" ", strip=True)
            if len(text) < 20 or text in seen:
                continue
            seen.add(text)
            link = row.find("a", href=True)
            title_el = row.find(["h2", "h3", "h4", "strong", "a"])
            title = title_el.get_text(strip=True) if title_el else text[:150]
            href = link["href"] if link else ""
            if href.startswith("/"):
                href = source["alt_url"].rstrip("/") + href
            t = Tender(title=title, description=text[:300], url=href or source["alt_url"],
                       source=source["name"], country=source["country"],
                       posted=date.today().isoformat())
            if t.matches_cyber_keywords():
                t.score = auto_score(t)
                t.priority = auto_priority(t.score)
                tenders.append(t)
    log.info(f"   ✅ SADC Portals: {len(tenders)} cyber/AI tenders found")
    return tenders


def normalize_date(raw: str) -> str:
    """Best-effort conversion of scraped date strings to YYYY-MM-DD."""
    if not raw:
        return ""
    raw = raw.strip()
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%d %b %Y", "%B %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    # Try to find a date-like substring
    m = re.search(r'(\d{4}-\d{2}-\d{2})', raw)
    if m:
        return m.group(1)
    return ""


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print("=" * 64)
    print("  TITO CYBER TENDER SCRAPER — GitHub Actions Run")
    print(f"  Target year: {CONFIG['target_year']} (open bids only)")
    print(f"  Run time: {datetime.now().isoformat()}")
    print("=" * 64)

    all_tenders: List[Tender] = []
    scrapers = [scrape_etenders, scrape_government_gazette, scrape_sadc_portals]

    for scraper in scrapers:
        try:
            all_tenders.extend(scraper())
        except Exception as e:
            log.error(f"Scraper {scraper.__name__} failed: {e}")

    # Deduplicate by normalized title
    seen_titles = set()
    unique = []
    for t in all_tenders:
        key = re.sub(r'\W+', '', t.title.lower())[:60]
        if key and key not in seen_titles:
            seen_titles.add(key)
            unique.append(t)

    # ── HARD FILTER: target year + still open ──────────────────
    filtered = [t for t in unique if t.is_open_target_year(CONFIG["target_year"])]

    data_source = "live"
    if len(filtered) == 0:
        log.warning("⚠️  No live tenders matched — falling back to seed dataset so the "
                    "dashboard isn't left empty. Live portals likely blocked the request "
                    "or changed their page structure; check the warnings above.")
        filtered = [t for t in seed_tenders() if t.is_open_target_year(CONFIG["target_year"])]
        data_source = "fallback_seed"

    # Assign sequential IDs
    for i, t in enumerate(filtered, 1):
        t.id = i

    excluded_count = len(unique) - len([t for t in unique if t.is_open_target_year(CONFIG["target_year"])])

    print(f"\n  Raw matches:        {len(unique)}")
    print(f"  Excluded (not {CONFIG['target_year']}/closed): {excluded_count}")
    print(f"  Final open {CONFIG['target_year']} tenders: {len(filtered)}")
    print(f"  Data source: {data_source}")

    output = {
        "generated_at": datetime.now().isoformat(),
        "target_year": CONFIG["target_year"],
        "total_open_tenders": len(filtered),
        "excluded_count": excluded_count,
        "sources_attempted": len(scrapers),
        "data_source": data_source,
        "tenders": [asdict(t) for t in filtered],
    }

    with open(CONFIG["output_path"], "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Wrote {CONFIG['output_path']}")


if __name__ == "__main__":
    main()
