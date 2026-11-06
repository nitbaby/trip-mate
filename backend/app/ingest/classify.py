import re

RULES = {
    "confirmation": r"confirmation|booking ref|check-?in|check-?out|reservation|e-?ticket|boarding|pnr",
    "rules": r"customs|visa|prohibited|permitted|regulation|import|restricted|entry requirements|medication",
    "itinerary": r"itinerary|day \d|schedule|agenda|depart(?:ure|s)|arriv(?:al|es)",
    "guide": r"guide|tips|recommend|neighbou?rhood|things to do|restaurants?",
}


def classify(text: str) -> str:
    low = text.lower()
    scores = {k: len(re.findall(rx, low)) for k, rx in RULES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "guide"
