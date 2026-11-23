"""Conservative parser for Codal statement cells and conventional HTML tables."""
from html.parser import HTMLParser
import json
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.error import URLError
from .common import ProviderError, number

ALLOWED = {"codal.ir", "www.codal.ir"}
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك", "01234567890123456789یک")
PERIOD = re.compile(r"(?<!\d)(1[34]\d{2})[/-](0?[1-9]|1[0-2])[/-](0?[1-9]|[12]\d|3[01])(?!\d)")
LABELS = {
    "درآمدهای عملیاتی": "operating_revenue", "درآمد عملیاتی": "operating_revenue",
    "سود (زیان) خالص": "net_income", "سود زیان خالص": "net_income", "سود خالص": "net_income",
    "سود (زیان) خالص هر سهم": "eps", "سود (زیان) پایه هر سهم": "eps",
    "جمع بدهی ها": "total_liabilities", "جمع بدهیها": "total_liabilities",
    "جریان خالص ورود (خروج) نقد حاصل از فعالیت های عملیاتی": "operating_cash_flow",
    "جریان خالص وجه نقد حاصل از فعالیت های عملیاتی": "operating_cash_flow",
}


def clean(value):
    return " ".join(str(value or "").translate(DIGITS).replace("\u200c"," ").split())


def fiscal_period(title):
    match = PERIOD.search(clean(title))
    return "/".join(f"{int(value):02d}" for value in match.groups()) if match else None


def monetary_value(text):
    s = clean(text).replace(",", "").replace("٬","").replace("٫",".").replace("−","-")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", s):
        return None
    return number(s)


def safe_url(url):
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname in ALLOWED and parts.port in (443,None) and not parts.username and not parts.password


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl):
            raise ProviderError("Unexpected Codal redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get_report_html(url):
    if not safe_url(url):
        raise ProviderError("Unexpected Codal report URL")
    try:
        req = Request(url, headers={"User-Agent":"Mozilla/5.0 IranSmartInvest/1.0"})
        with build_opener(SafeRedirect()).open(req, timeout=10) as response:
            content = response.read(8_000_001)
        if len(content) > 8_000_000:
            raise ProviderError("Financial report too large")
        return content.decode("utf-8-sig")
    except (URLError, OSError, UnicodeError) as exc:
        raise ProviderError("Could not read Codal financial report") from exc


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = self.row = self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td","th") and self.row is not None:
            self.cell = []

    def handle_data(self, text):
        if self.cell is not None:
            self.cell.append(text)

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self.cell is not None:
            self.row.append(clean(" ".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = self.row = self.cell = None


def grids(html):
    parser = Tables()
    parser.feed(html)
    yield from parser.tables
    for match in re.finditer(r"\b(?:datasource|dataSource)\s*=\s*", html):
        try:
            doc, _ = json.JSONDecoder().raw_decode(html[match.end():].lstrip())
        except ValueError:
            continue
        for sheet in doc.get("sheets",[]) if isinstance(doc,dict) else []:
            for table in sheet.get("tables",[]):
                mapped = {}
                for cell in table.get("cells",[]):
                    address = re.fullmatch(r"\$?([A-Z]{1,2})\$?(\d{1,4})", str(cell.get("address","")))
                    if not address:
                        continue
                    col = 0
                    for c in address[1]:
                        col = col*26 + ord(c)-64
                    if col <= 80:
                        mapped.setdefault(int(address[2]),{})[col] = clean(cell.get("value"))
                width = max((max(cols) for cols in mapped.values()), default=0)
                yield [[mapped[row].get(col,"") for col in range(1,width+1)] for row in sorted(mapped)]


def metrics_from_report(html, period):
    if not period:
        return {}
    found = {}
    conflicts = set()
    for grid in grids(html):
        col = None
        for row in grid:
            matches = [i for i,val in enumerate(row) if fiscal_period(val)==period]
            if matches:
                col = matches[0] if len(matches)==1 else None
                continue
            if col is None or col >= len(row) or not row:
                continue
            label = next((LABELS[val] for val in row[:col] if val in LABELS), None)
            value = monetary_value(row[col])
            if label and value is not None:
                if label in found and found[label] != value:
                    conflicts.add(label)
                found[label] = value
    return {k:v for k,v in found.items() if k not in conflicts}

