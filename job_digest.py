"""Daily remote-job digest -> Email (Gmail).

Sources: RemoteOK, We Work Remotely, Remotive, Jobicy, Himalayas, Working Nomads.
Env vars (set as GitHub Secrets):
  EMAIL_ADDRESS       your Gmail address (sends to itself)
  EMAIL_APP_PASSWORD  a Gmail "app password" (not your normal password)
"""
import json
import os
import re
import smtplib
import time
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from pathlib import Path

import requests

# ---- Edit these ----------------------------------------------------------
INCLUDE = [
    "automation", "automate", "n8n", "zapier", "make.com", "workflow",
    "no-code", "no code", "low-code", "low code", "rpa", "integration",
    "data analyst", "data analysis", "data analytics", "business analyst",
    "bi analyst", "bi developer", "power bi", "reporting analyst",
    "operations analyst", "python", "sql", "ai agent", "ai automation",
    "prompt engineer",
    # admin and operations
    "administrator", "admin", "operations", "coordinator", "office",
    "virtual assistant", "executive assistant", "data entry", "back office",
    # IT and customer support
    "it support", "technical support", "tech support", "help desk",
    "helpdesk", "service desk", "support specialist", "support engineer",
    "support agent", "customer support", "customer service",
    "customer success", "client support",
    # banking and finance background
    "banking", "bank ", "fintech", "payments", "kyc", "compliance",
    "reconciliation", "bookkeeper",
]
EXCLUDE = [
    "senior", "sr.", "sr ", "lead", "principal", "staff", "director",
    "head of", "vp ", "manager", "architect",
]
MAX_PER_DIGEST = 40
# --------------------------------------------------------------------------

WWR_FEEDS = [
    "https://weworkremotely.com/remote-jobs.rss",
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/all-other-remote-jobs.rss",
]
REMOTIVE_SEARCHES = ["automation", "data analyst"]
JOBICY_TAGS = ["automation", "n8n", "data analyst", "python"]
HIMALAYAS_KEYWORDS = ["automation", "data analyst", "operations", "customer support", "it support"]

SEEN_FILE = Path(__file__).with_name("seen.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (personal job-digest script)"}


def get(url, **kwargs):
    time.sleep(1)  # be polite to the websites
    r = requests.get(url, headers=HEADERS, timeout=30, **kwargs)
    r.raise_for_status()
    r.encoding = "utf-8"  # avoids garbled characters like "â€”"
    return r


def fetch_remoteok():
    data = json.loads(get("https://remoteok.com/api").text)
    jobs = []
    for item in data[1:]:  # first element is a legal notice
        jobs.append({
            "title": item.get("position", ""),
            "company": item.get("company", ""),
            "url": item.get("url", ""),
            "tags": " ".join(item.get("tags", []) or []),
            "source": "RemoteOK",
        })
    return jobs


def fetch_wwr():
    jobs = []
    for feed in WWR_FEEDS:
        try:
            root = ET.fromstring(get(feed).content)
        except Exception as e:
            print(f"WWR feed failed {feed}: {e}")
            continue
        for item in root.iter("item"):
            raw = (item.findtext("title") or "").strip()
            company, _, title = raw.partition(": ")
            if not title:
                company, title = "", raw
            jobs.append({
                "title": title,
                "company": company,
                "url": (item.findtext("link") or "").strip(),
                "tags": "",
                "source": "WeWorkRemotely",
            })
    return jobs


def fetch_remotive():
    jobs = []
    for term in REMOTIVE_SEARCHES:
        try:
            data = get("https://remotive.com/api/remote-jobs",
                       params={"search": term, "limit": 100}).json()
        except Exception as e:
            print(f"Remotive '{term}' failed: {e}")
            continue
        for item in data.get("jobs", []):
            jobs.append({
                "title": item.get("title", ""),
                "company": item.get("company_name", ""),
                "url": item.get("url", ""),
                "tags": " ".join(item.get("tags", []) or []),
                "source": "Remotive",
            })
    return jobs


def fetch_jobicy():
    jobs = []
    for tag in JOBICY_TAGS:
        try:
            data = get("https://jobicy.com/api/v2/remote-jobs",
                       params={"count": 50, "tag": tag}).json()
        except Exception as e:
            print(f"Jobicy '{tag}' failed: {e}")
            continue
        for item in data.get("jobs", []):
            jobs.append({
                "title": item.get("jobTitle", ""),
                "company": item.get("companyName", ""),
                "url": item.get("url", ""),
                "tags": "",
                "source": "Jobicy",
            })
    return jobs


def fetch_himalayas():
    jobs = []
    for kw in HIMALAYAS_KEYWORDS:
        try:
            data = get("https://himalayas.app/jobs/api/search",
                       params={"keyword": kw, "limit": 20}).json()
        except Exception as e:
            print(f"Himalayas '{kw}' failed: {e}")
            continue
        for item in data.get("jobs", []):
            cats = item.get("categories") or []
            jobs.append({
                "title": item.get("title", ""),
                "company": item.get("companyName", ""),
                "url": item.get("applicationLink") or item.get("guid") or item.get("url", ""),
                "tags": " ".join(cats) if isinstance(cats, list) else str(cats),
                "source": "Himalayas",
            })
    return jobs


def fetch_workingnomads():
    data = get("https://www.workingnomads.com/api/exposed_jobs/").json()
    if isinstance(data, dict):
        data = data.get("jobs") or data.get("results") or []
    jobs = []
    for item in data:
        tags = item.get("tags", "")
        if isinstance(tags, list):
            tags = " ".join(tags)
        jobs.append({
            "title": item.get("title", ""),
            "company": item.get("company_name") or item.get("companyName", ""),
            "url": item.get("url", ""),
            "tags": f"{tags} {item.get('category_name') or item.get('category', '')}",
            "source": "WorkingNomads",
        })
    return jobs


def matches(job):
    text = f"{job['title']} {job['tags']}".lower()
    if any(x in text for x in EXCLUDE):
        return False
    return any(re.search(r"\b" + re.escape(k), text) for k in INCLUDE)


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def send_email(subject, body):
    address = os.environ["EMAIL_ADDRESS"]
    password = os.environ["EMAIL_APP_PASSWORD"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = address
    msg["To"] = address
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(address, password)
        server.send_message(msg)


def main():
    seen = load_seen()
    all_jobs = []
    for fetch in (fetch_remoteok, fetch_wwr, fetch_remotive, fetch_jobicy,
                  fetch_himalayas, fetch_workingnomads):
        try:
            found = fetch()
            print(f"{fetch.__name__}: {len(found)} jobs")
            all_jobs += found
        except Exception as e:
            print(f"{fetch.__name__} failed: {e}")

    new, urls_this_run = [], set()
    for job in all_jobs:
        url = job["url"]
        if url and url not in seen and url not in urls_this_run and matches(job):
            new.append(job)
            urls_this_run.add(url)

    print(f"{len(all_jobs)} fetched, {len(new)} new matches")
    if new:
        batch = new[:MAX_PER_DIGEST]
        lines = [f"- {j['title']} | {j['company']} [{j['source']}]\n  {j['url']}"
                 for j in batch]
        body = "\n\n".join(lines)
        if len(new) > len(batch):
            body += f"\n\n(+{len(new) - len(batch)} more will arrive in the next digest)"
        body += "\n\nSources: RemoteOK, We Work Remotely, Remotive, Jobicy, Himalayas, Working Nomads."
        send_email(f"{len(new)} new remote jobs", body)
        # Only mark the jobs we actually emailed as seen
        seen.update(j["url"] for j in batch)

    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=0))


if __name__ == "__main__":
    main()
