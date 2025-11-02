import re
from typing import List, Dict
import yfinance as yf


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

    headlines = []
    scores = []
    for item in news[:max_headlines]:
        # yfinance news items may have 'title' or 'headline'
        title = item.get('title') or item.get('headline') or ''
        if title:
            headlines.append(title)
            scores.append(_score_headline(title))

    total_score = sum(scores)
    # normalize by number of headlines inspected to get a float
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

    # return per-headline scores as well
    headline_scores = []
    for h, s in zip(headlines, scores):
        headline_scores.append({'headline': h, 'score': s})

    return {
        'score': norm,
        'label': label,
        'headlines': headlines,
        'headline_scores': headline_scores,
        'events': events,
    }
