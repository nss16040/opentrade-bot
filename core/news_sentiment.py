import re
from typing import List, Dict
import yfinance as yf
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any


POSITIVE_WORDS = {
    'gain', 'gains', 'up', 'surge', 'surges', 'beat', 'beats', 'upgrade', 'upgraded',
    'record', 'strong', 'positive', 'outperform', 'outperformance', 'benefit', 'benefits',
    'profit', 'profits', 'win', 'wins'
}

NEGATIVE_WORDS = {
    'drop', 'drops', 'down', 'fall', 'falls', 'decline', 'declines', 'miss', 'misses',
    'downgrade', 'downgraded', 'weak', 'negative', 'underperform', 'loss', 'losses', 'halt'
}


def _tokenize(text: str) -> List[str]:
    # simple tokenization: split on non-alphanumeric
    return [t for t in re.split(r'[^a-zA-Z0-9]+', text.lower()) if t]


def _score_headline(headline: str) -> int:
    tokens = _tokenize(headline)
    score = 0
    for t in tokens:
        if t in POSITIVE_WORDS:
            score += 1
        if t in NEGATIVE_WORDS:
            score -= 1
    return score


def _fetch_google_news(query: str, max_headlines: int = 5) -> List[str]:
    """Fetch headlines from Google News RSS for `query`.

    This is a lightweight fallback when yfinance.news is empty. It performs a
    search query on Google News RSS and returns a list of headline strings.
    Uses only stdlib (urllib, xml.etree) to avoid new dependencies.
    """
    q = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = resp.read()
    try:
        root = ET.fromstring(data)
    except Exception:
        return []

    headlines = []
    # RSS feed structure: /rss/channel/item/title
    for item in root.findall('.//item')[:max_headlines]:
        title_el = item.find('title')
        pub_el = item.find('pubDate')
        title = title_el.text.strip() if title_el is not None and title_el.text else None
        pub = pub_el.text.strip() if pub_el is not None and pub_el.text else None
        if title:
            headlines.append({'title': title, 'pubDate': pub})
        if len(headlines) >= max_headlines:
            break
    return headlines


# simple in-memory cache to avoid repeated RSS/network calls during a single
# dashboard session. Keyed by query string.
_RSS_CACHE: Dict[str, List[str]] = {}


def get_news_sentiment(symbol: str, max_headlines: int = 5) -> Dict:
    """Fetch recent news for `symbol` and return a simple sentiment score.

    Returns a dict with keys:
      - 'score': float normalized score (sum(scores)/max(1, total_words))
      - 'label': 'positive'|'negative'|'neutral'
      - 'headlines': list of headlines inspected

    This is intentionally lightweight and does not require external NLP
    dependencies. It's suitable for a heuristic to adjust strategy selection.
    """
    ticker = yf.Ticker(f"{symbol}.NS")
    try:
        news = ticker.news or []
    except Exception:
        news = []

    headlines: List[Dict[str, Any]] = []
    scores: List[int] = []
    for item in news[:max_headlines]:
        # yfinance news items may have 'title' or 'headline'
        title = item.get('title') or item.get('headline') or ''
        pub = item.get('providerPublishTime') or item.get('pubDate')
        if title:
            headlines.append({'title': title, 'pubDate': pub})
            scores.append(_score_headline(title))

    # If yfinance provided no headlines (common), try a lightweight RSS
    # fallback (Google News search) so we still have some text to analyze.
    if len(headlines) == 0:
        # Prefer querying by company long name (better results) when available
        # from yfinance.Ticker.info. Fall back to the raw symbol if that fails.
        rss_queries = [symbol]
        try:
            info = ticker.info or {}
            name = info.get('longName') or info.get('shortName')
            if name:
                # try company name first, then the raw symbol
                rss_queries.insert(0, name)
        except Exception:
            pass

        for q in rss_queries:
            try:
                # use cached results when available
                cached = _RSS_CACHE.get(q)
                if cached is not None:
                    rss = cached
                else:
                    rss = _fetch_google_news(q, max_headlines)
                    _RSS_CACHE[q] = rss
                for t in rss:
                    # t may be a dict with 'title' and 'pubDate'
                    if isinstance(t, dict):
                        title = t.get('title')
                        pub = t.get('pubDate')
                    else:
                        title = t
                        pub = None
                    if title:
                        headlines.append({'title': title, 'pubDate': pub})
                        scores.append(_score_headline(title))
                if len(headlines) > 0:
                    break
            except Exception:
                # ignore and try next query
                continue

    total_score = sum(scores)
    # normalize by number of headlines inspected to get a float
    if len(headlines) == 0:
        # no headlines available -> report explicit 'no_news' label so callers
        # can distinguish between neutral sentiment and absence of data.
        return {
            'score': 0.0,
            'label': 'no_news',
            'headlines': [],
            'headline_scores': [],
            'events': [],
        }

    norm = float(total_score) / max(1, len(headlines))

    if norm >= 0.5:
        label = 'positive'
    elif norm <= -0.5:
        label = 'negative'
    else:
        label = 'neutral'

    # Gather simple "major events" information from the ticker where available.
    events = []
    try:
        cal = ticker.calendar
        if cal is not None and not cal.empty:
            # calendar is typically a DataFrame with one column; transpose to key/value
            try:
                d = cal.T.to_dict()[0]
            except Exception:
                # fallback: convert values to strings
                d = {str(idx): str(val[0]) for idx, val in cal.items()} if hasattr(cal, 'items') else {}
            for k, v in d.items():
                events.append({'event': str(k), 'value': str(v)})
    except Exception:
        # ignore calendar errors
        pass

    try:
        actions = ticker.actions
        if actions is not None and not actions.empty:
            # actions is a DataFrame indexed by date with columns like 'Dividends'/'Stock Splits'
            # collect the most recent non-zero actions
            recent = actions.tail(10)
            for idx, row in recent.iterrows():
                for col in recent.columns:
                    val = row.get(col)
                    if val and float(val) != 0:
                        events.append({'event': str(col), 'value': f"{idx.date()} -> {val}"})
    except Exception:
        pass

    # return per-headline scores as well (include pubDate when available)
    headline_scores = []
    for h, s in zip(headlines, scores):
        # h is dict {'title', 'pubDate'}
        if isinstance(h, dict):
            headline_scores.append({'headline': h.get('title'), 'score': s, 'pubDate': h.get('pubDate')})
        else:
            headline_scores.append({'headline': h, 'score': s, 'pubDate': None})

    return {
        'score': norm,
        'label': label,
        'headlines': headlines,
        'headline_scores': headline_scores,
        'events': events,
    }
