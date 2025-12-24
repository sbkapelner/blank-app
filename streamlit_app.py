import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
import pandas as pd

# ------------------------------
# Patent Fetching Logic
# ------------------------------

FIELDS = [
    "patent_no",
    "title",
    "inventor",
    "assignee",
    "status",
    "priority_date",
    "exp_date",
]

class GooglePatentsClient:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "gzip, deflate",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

    def url_from_patno(self, no: str) -> str:
        return f"https://patents.google.com/patent/{no}/en?oq={no}"

    def get_html(self, url: str):
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            return resp, resp.status_code
        except Exception as e:
            return None, 0

    def parse(self, response):
        soup = BeautifulSoup(response.text, "html.parser")

        # From <title>
        title_tag = soup.find("title")
        patent_no, title = "", ""
        if title_tag and title_tag.text:
            parts = re.split(r" - |\n", title_tag.text)
            if len(parts) >= 2:
                patent_no = parts[0].strip()
                title = parts[1].strip()

        # Inventor
        inventor_tag = soup.find("dd", itemprop="inventor")
        inventor = inventor_tag.text.strip() if inventor_tag else None

        # Assignee
        assignee_tag = soup.find("span", itemprop="assigneeSearch")
        assignee = assignee_tag.text.strip() if assignee_tag else None
        if assignee == inventor:
            assignee = None

        # Priority Date
        pr_tag = soup.find(attrs={"itemprop": "priorityDate"})
        priority_date = pr_tag.text.strip() if pr_tag else "DATE MISSING"

        # Status + Expiration
        status_tag = soup.find("span", itemprop="status")
        exp_tag = soup.find("time", itemprop="expiration")

        status_val = status_tag.text.strip() if status_tag else None
        exp_date = exp_tag.text.strip() if exp_tag else "DATE MISSING"

        if status_val:
            if "Expired" in status_val:
                status = "Expired"
            elif status_val == "Active" and exp_tag:
                status = f"Active (Exp. {exp_date})"
            else:
                status = status_val
        else:
            status = "No status or exp date"

        return {
            "patent_no": patent_no,
            "title": title,
            "inventor": inventor or "None",
            "assignee": assignee or "None",
            "status": status,
            "priority_date": priority_date,
            "exp_date": exp_date,
        }

# ------------------------------
# Streamlit UI
# ------------------------------

st.title("Google Patents Fetcher")

st.write("Paste patent/publication numbers, select fields, and fetch structured data.")

raw_patents = st.text_area(
    "Paste patent numbers (any whitespace or commas):",
    height=200,
    placeholder="US10772732\nUS11026798\nUS11484413\n..."
)

# Normalize input
patent_list = sorted(
    set(re.split(r"[\s,]+", raw_patents.strip())) - {""}
)

st.write(f"**Detected {len(patent_list)} unique patent numbers.**")

# Field selection (checkbox UI)
st.subheader("Select which fields to return:")
selected_fields = []
cols = st.columns(3)

for i, field in enumerate(FIELDS):
    with cols[i % 3]:
        if st.checkbox(field, value=(field in ["patent_no", "status"])):
            selected_fields.append(field)

include_url = st.checkbox("Include Google Patents URL", value=False)

fetch = st.button("Fetch")

client = GooglePatentsClient()

# ------------------------------
# Fetch & Display Results
# ------------------------------
if fetch:
    rows = []
    for pat in patent_list:
        url = client.url_from_patno(pat)
        response, code = client.get_html(url)

        if code != 200:
            rows.append({"patent_no": pat, "error": f"HTTP {code}"})
            continue

        data = client.parse(response)
        row = {f: data[f] for f in selected_fields}
        if include_url:
            row["url"] = url
        rows.append(row)

    df = pd.DataFrame(rows)

    st.subheader("Results")
    st.dataframe(df, use_container_width=True)

    # Downloads
    st.download_button(
        "Download CSV",
        df.to_csv(index=False),
        file_name="patents.csv",
        mime="text/csv"
    )

    st.download_button(
        "Download TSV",
        df.to_csv(index=False, sep="\t"),
        file_name="patents.tsv",
        mime="text/tab-separated-values"
    )