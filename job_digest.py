"""Daily remote-job digest: RemoteOK + We Work Remotely -> Email (Gmail).

Env vars (set as GitHub Secrets):
  EMAIL_ADDRESS       your Gmail address (sends to itself)
  EMAIL_APP_PASSWORD  a Gmail "app password" (not your normal password)
"""
import json
import os
import re
import smtplib
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from pathlib import Path

import requests

# ---- Edit these ----------------------------------------------------------
INCLUDE = ["automation engineer", "data analyst", "artificial intelligence", "workflow automation", "python", "powerBi", "animation",
           "customer service", "administrator", "MIS Analyst", "Financial Analyst", "Workflow Automation Specialist", "Junior Automation Engineer","Business Process Automation Analyst", "AI Automation Specialist","IT Support Specialist", "Data Analyst Junior"]
EXCLUDE = ["senior director", "vp ", "head of", "principal", "staff "]
MAX_PER_DIGEST = 30
# --------------------------------------------------------------------------

WWR_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-design-jobs.rss",
]
SEEN_FILE = Path(__file__).with_name("seen.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (job-digest script)"}


def fetch_remoteok():
    r = requests.get("https://remoteok.com/api", headers=HEADERS, timeout=30)
    r.raise_for_status()
    jobs = []
    for item in r.json()[1:]:  # first element is a legal notice
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
            r = requests.get(feed, headers=HEADERS, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.content)
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
    for fetch in (fetch_remoteok, fetch_wwr):
        try:
            all_jobs += fetch()
        except Exception as e:
            print(f"{fetch.__name__} failed: {e}")

    new = []
    for job in all_jobs:
        if job["url"] and job["url"] not in seen and matches(job):
            new.append(job)
            seen.add(job["url"])

    print(f"{len(all_jobs)} fetched, {len(new)} new matches")
    if new:
        batch = new[:MAX_PER_DIGEST]
        lines = []
        for j in batch:
            lines.append(f"• {j['title']} — {j['company']} [{j['source']}]\n{j['url']}")
        body = "\n\n".join(lines)
        send_email(f"{len(new)} new remote jobs", body)

    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=0))


if __name__ == "__main__":
    main()
