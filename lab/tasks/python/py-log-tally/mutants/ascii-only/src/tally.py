import re
from collections import Counter

def tally(text, limit):
    words = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)*", text.casefold())
    counts = Counter(words)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return {"total": len(words), "unique": len(counts),
            "top": [{"word": word, "count": count} for word, count in ranked[:limit]]}
