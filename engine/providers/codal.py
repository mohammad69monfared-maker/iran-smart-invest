from urllib.parse import urlencode, urljoin, urlsplit
from .common import ProviderError, get_json, now, rows


class Codal:
    def __init__(self, fetch=get_json):
        self.fetch = fetch

    def disclosures(self, symbol, page=1):
        if not isinstance(symbol, str) or not 0 < len(symbol.strip()) <= 64 or not isinstance(page, int) or page < 1:
            raise ProviderError("Invalid symbol or page")
        url = "https://search.codal.ir/api/search/v2/q?" + urlencode({
            "Symbol": symbol, "PageNumber": page, "IsNotAudited": "true", "Audited": "true",
            "NotAudited": "true", "Mains": "true", "Childs": "true"})
        received = now()
        result = []
        for item in rows(self.fetch(url), "Letters"):
            if str(item.get("Symbol", "")).strip() != symbol.strip():
                continue
            if not item.get("PublishDateTime") or not item.get("Title"):
                raise ProviderError("Invalid disclosure metadata")
            link = urljoin("https://codal.ir/", item.get("Url") or "")
            parts = urlsplit(link)
            valid_url = parts.scheme == "https" and parts.hostname in ("codal.ir", "www.codal.ir")
            result.append(dict(symbol=symbol, title=item["Title"], published_at=item["PublishDateTime"],
                               tracking_number=item.get("TracingNo"), letter_code=item.get("LetterCode"),
                               period=None, audited=item.get("IsAudited"), url=link if valid_url else None,
                               source="Codal", fetched_at=received))
        return result

