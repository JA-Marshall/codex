import re
from collections import Counter

def counts(text):
    return dict(Counter(re.findall(r"[^\W_]+", text.casefold())))
