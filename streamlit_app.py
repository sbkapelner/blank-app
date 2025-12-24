#!/usr/bin/env python3
import re
import time
import requests
import streamlit as st
from bs4 import BeautifulSoup

DEFAULT_FIELDS = [
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
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15",
            "Accept-Encoding": "gzip, deflate",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

    def url_from_patno(self, no: str) -> str:
        return f"https://patents.google.com/patent/{no}/en?oq={no}"

    def get_html(self, url: str):
        resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        return resp, resp.status_code

    def parse_core(self, response) -> dict:
        soup = BeautifulSoup(response.text, "html.parser")

        # Patent number + title from <title>
        title_tag = soup.find("title")
        patent_no, title = None, None
        if title_tag and title_tag.text:
            parts = re.split(r" - |\n", title_tag.text)
            if len(parts) >= 2:
                patent_no = parts[0].strip()
                title = parts[1].strip()

        # Inventor
        inventor = None
        inventor_tag = soup.find("dd", itemprop="inventor")
        if inventor_tag and inventor_tag.text:
            inventor = inventor_tag.text.strip()

        # Assignee
        assignee = None
        assignee_tag = soup.find("span", itemprop="assigneeSearch")
        if assignee_tag and assignee_tag.text:
            assignee_text = assignee_tag.text.strip()
            if inventor and assignee_text == inventor:
                assignee = None
            else:
                assignee = assignee_text

        # Priority date
        priority_date = None
        pr_tag = soup.find(attrs={"itemprop": "priorityDate"})
        if pr_tag and pr_tag.text:
            priority_date = pr_tag.text.strip()

        # Status + expiration
        status_val = None
        exp_date = None

        status_tag = soup.find("span", itemprop="status")
        if status_tag and status_tag.text:
            status_val = status_tag.text.strip()
            if "Expired" in status_val:
                status_val = "Expired"

        exp_tag = soup.find("time", itemprop="expiration")
        if exp_tag and exp_tag.text:
            exp_date = exp_tag.text.strip()

        if status_val:
            if status_val == "Active" and exp_date:
                status_str = f"{status_val} (Exp. {exp_date})"
            else:
                status_str = status_val
        else:
            status_str = "No status or exp date"

        return {
            "patent_no": patent_no or "",
            "title": title or "",
            "inventor": f"Inventor: {inventor}" if inventor else "Inventor: None",
            "assignee": f"Assignee: {assignee}" if assignee else "Assignee: None",
            "status": status_str,
            "priority_date": priority_date or "DATE MISSING",
            "exp_date": exp_date or "DATE MISSING",
        }

@st.cache_data(show_spinner=False, ttl=60 * 60)
def fetch_one(pat: str, timeout: int) -> dict:
    client = GooglePatentsClient(timeout=timeout)
    url = client.url_from_patno(pat)
    resp, code = client.get_html(url)
    if code != 200:
        return {"_pat_input": pat, "_url": url, "_error": f"HTTP {code}"}
    data = client.parse_core(resp)
    data["_pat_input"] = pat
    data["_url"] = url
    data["_error"] = ""
    return data

def parse_patent_list(raw: str) -> list[str]:
    # Accept whitespace, commas, tabs; ignore a header like "Patent Number"
    toks = re.split(r"[\s,]+", raw.strip())
    pats = []
    for t in toks:
        t = t.strip()
        if not t:
            continue
        if t.lower() in {"patent", "number", "patentnumber", "patent_no", "patent-no"}:
            continue
        pats.append(t)
    # de-dupe preserving order
    seen = set()
    out = []
    for p in pats:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

def main():
    st.set_page_config(page_title="Patent Fetcher", layout="wide")
    st.title("Google Patents Fetcher")
    st.write("Paste patent/publication numbers, select fields, and get a table + CSV/TSV output.")

    with st.sidebar:
        st.subheader("Fields to return")
        # “Radio buttons” are single-choice; fields need multi-choice.
        # Using checkboxes (closest UX) + “select all/none”.
        select_all = st.checkbox("Select all fields", value=True)
        if select_all:
            selected_fields = DEFAULT_FIELDS[:]
        else:
            selected_fields = []
            for f in DEFAULT_FIELDS:
                if st.checkbox(f, value=(f in {"patent_no", "priority_date", "exp_date"})):
                    selected_fields.append(f)

        st.subheader("Options")
        include_url = st.checkbox("Include URL column", value=False)
        timeout = st.number_input("Timeout (seconds)", min_value=5, max_value=120, value=30, step=5)
        delay = st.number_input("Delay between requests (seconds)", min_value=0.0, max_value=2.0, value=0.0, step=0.1)

        output_format = st.radio("Output format", ["CSV", "TSV"], index=0)

    raw = st.text_area(
        "Paste patent numbers (any whitespace/comma separated):",
        height=180,
        placeholder="US10772732\nUS11026798\nUS11484413\n...",
    )

    pats = parse_patent_list(raw) if raw.strip() else []
    st.caption(f"Detected {len(pats)} unique patent numbers.")

    if st.button("Fetch", type="primary", disabled=(len(pats) == 0 or len(selected_fields) == 0)):
        rows = []
        prog = st.progress(0)
        status = st.empty()

        for i, pat in enumerate(pats, start=1):
            status.write(f"Fetching {i}/{len(pats)}: {pat}")
            try:
                data = fetch_one(pat, int(timeout))
            except requests.RequestException as e:
                data = {"_pat_input": pat, "_url": GooglePatentsClient().url_from_patno(pat), "_error": str(e)}

            row = {}
            row["pat_input"] = data.get("_pat_input", pat)
            if include_url:
                row["url"] = data.get("_url", "")
            if data.get("_error"):
                row["error"] = data["_error"]
            else:
                row["error"] = ""

            for f in selected_fields:
                row[f] = data.get(f, "")
            rows.append(row)

            prog.progress(i / len(pats))
            if delay > 0:
                time.sleep(float(delay))

        st.success("Done.")
        st.dataframe(rows, use_container_width=True)

        sep = "," if output_format == "CSV" else "\t"
        headers = list(rows[0].keys()) if rows else []
        lines = [sep.join(headers)]
        for r in rows:
            # basic escaping: quote if separator/newline present
            out_cells = []
            for h in headers:
                val = "" if r.get(h) is None else str(r.get(h))
                if sep in val or "\n" in val or '"' in val:
                    val = '"' + val.replace('"', '""') + '"'
                out_cells.append(val)
            lines.append(sep.join(out_cells))
        out_text = "\n".join(lines)

        st.download_button(
            label=f"Download {output_format}",
            data=out_text,
            file_name=f"patents_output.{ 'csv' if output_format == 'CSV' else 'tsv' }",
            mime="text/plain",
        )
        st.text_area("Copy/paste output:", out_text, height=220)

if __name__ == "__main__":
    main()