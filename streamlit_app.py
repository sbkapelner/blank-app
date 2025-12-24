import streamlit as st
import requests
from bs4 import BeautifulSoup
import re

# -------------------------------
# Patent scraping logic
# -------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "*/*",
    "Connection": "keep-alive",
}

def fetch_html(pat_no):
    url = f"https://patents.google.com/patent/{pat_no}/en?oq={pat_no}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        return r, r.status_code, url
    except Exception as e:
        return None, 0, url

def parse_expiration(soup):
    """
    Return the expiration date by trying multiple known paths used by Google Patents.
    """

    # 1. Normal utility patent expiration: <time itemprop="expiration">
    t = soup.find("time", itemprop="expiration")
    if t and t.get("datetime"):
        return t["datetime"]

    # 2. Adjusted expiration (often used for utility patents)
    events = soup.find_all("dd", itemprop="events")
    for ev in events:
        time_tag = ev.find("time")
        title_tag = ev.find("span", itemprop="title")
        if time_tag and time_tag.get("datetime"):
            title_text = title_tag.get_text(strip=True).lower() if title_tag else ""
            if "adjusted expiration" in title_text:
                return time_tag["datetime"]

    # 3. Anticipated expiration (design patents)
    for ev in events:
        time_tag = ev.find("time")
        title_tag = ev.find("span", itemprop="title")
        if time_tag and time_tag.get("datetime"):
            title_text = title_tag.get_text(strip=True).lower() if title_tag else ""
            if "anticipated expiration" in title_text:
                return time_tag["datetime"]

    # 4. Fallback: first datetime-looking value under "events"
    for ev in events:
        t = ev.find("time")
        if t and t.get("datetime"):
            return t["datetime"]

    return "DATE MISSING"

def parse_priority_date(soup):
    """
    Try all known priority date markers.
    """

    # 1. Normal Google Patents priority date
    t = soup.find(attrs={"itemprop": "priorityDate"})
    if t and t.text.strip():
        return t.text.strip()

    # 2. Alternative: prior art date
    t = soup.find("time", itemprop="priorArtDate")
    if t and t.get("datetime"):
        return t["datetime"]

    return "DATE MISSING"


def parse_patent(pat_no, html_response):
    soup = BeautifulSoup(html_response.text, "html.parser")

    # Title + patent number
    patent_no_clean = ""
    title = ""
    tag = soup.find("title")
    if tag and tag.text:
        parts = re.split(r" - |\n", tag.text)
        if len(parts) >= 2:
            patent_no_clean = parts[0].strip()
            title = parts[1].strip()

    # Inventor
    inventor_tag = soup.find("dd", itemprop="inventor")
    inventor = inventor_tag.get_text(strip=True) if inventor_tag else "None"

    # Assignee
    assignee_tag = soup.find("span", itemprop="assigneeSearch")
    assignee = assignee_tag.get_text(strip=True) if assignee_tag else "None"

    # Status
    status_tag = soup.find("span", itemprop="status")
    status_val = status_tag.get_text(strip=True) if status_tag else "Unknown"

    # Expiration date (new robust method)
    exp_date = parse_expiration(soup)

    # Priority date (robust)
    priority_date = parse_priority_date(soup)

    return {
        "patent_no": patent_no_clean,
        "title": title,
        "inventor": inventor,
        "assignee": assignee,
        "status": status_val,
        "priority_date": priority_date,
        "exp_date": exp_date,
    }

# -------------------------------
# Streamlit UI
# -------------------------------

st.title("Patent Metadata Extractor")

st.write("Paste your patent numbers (one per line):")

input_text = st.text_area("Patent Numbers")

all_fields = [
    "patent_no",
    "title",
    "inventor",
    "assignee",
    "status",
    "priority_date",
    "exp_date",
]

st.write("Select fields to return:")

selected_fields = []
for field in all_fields:
    if st.checkbox(field, value=(field in ["patent_no", "status", "exp_date"])):
        selected_fields.append(field)

if st.button("Fetch Metadata"):
    if not input_text.strip():
        st.error("Please paste at least one patent number.")
    else:
        pat_list = [p.strip() for p in input_text.split("\n") if p.strip()]

        results = []

        for pat in pat_list:
            html, code, url = fetch_html(pat)
            if code != 200:
                results.append({field: f"ERROR ({code})" for field in selected_fields})
                continue
            data = parse_patent(pat, html)
            # maintain order; only take selected fields
            results.append({field: data[field] for field in selected_fields})

        st.success("Done!")
        st.write("Results:")
        st.dataframe(results)