"""
Shared utilities for AIKnowledgeDistill pipeline scripts.
"""
import re


# ─── Language Detection ──────────────────────────────────────────────────────

# Top function words per language (appear frequently in any topic)
LANG_MARKERS = {
    "en": {
        "the", "is", "are", "was", "were", "have", "has", "been", "will",
        "would", "could", "should", "with", "from", "this", "that", "what",
        "which", "there", "their", "they", "your", "about", "into", "just",
        "also", "been", "being", "does", "doing", "during", "before", "after",
        "between", "those", "these", "through", "while", "where", "here",
    },
    "nl": {
        "een", "het", "van", "dat", "die", "niet", "ook", "als", "zijn",
        "maar", "dan", "bij", "heb", "moet", "naar", "geen", "wel", "dit",
        "dus", "deze", "aan", "nog", "hebben", "heeft", "wordt", "haar",
        "zij", "wij", "hij", "jullie", "hun", "veel", "weinig", "gaan",
        "doen", "zien", "komen", "staan", "geven", "laten", "houden",
        "eigenlijk", "natuurlijk", "daarom", "ongeveer", "verder", "altijd",
        "nooit", "soms", "vaak", "gewoon", "beetje", "volgens", "namelijk",
    },
    "fr": {
        "les", "des", "une", "est", "pas", "que", "qui", "dans", "sur",
        "pour", "avec", "plus", "sont", "nous", "vous", "ils", "elle",
        "mais", "aussi", "cette", "tout", "bien", "fait", "peut", "comme",
        "leurs", "entre", "encore", "alors", "depuis", "avant", "autres",
    },
    "de": {
        "der", "die", "das", "ein", "eine", "ist", "sind", "war", "hat",
        "mit", "auf", "fur", "von", "den", "dem", "des", "sich", "nicht",
        "auch", "noch", "aber", "wird", "oder", "wenn", "nach", "kann",
        "nur", "sehr", "dann", "hier", "diese", "diesem", "dieser",
    },
    "es": {
        "los", "las", "una", "del", "por", "con", "para", "que", "son",
        "pero", "como", "mas", "fue", "hay", "tiene", "desde", "esta",
        "cuando", "entre", "puede", "todos", "hacia", "donde", "quien",
    },
}

LANG_NAMES = {
    "en": "English",
    "nl": "Dutch",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "unknown": "Unknown",
}


def detect_language(text, min_words=10):
    """Detect language from text using function word frequency."""
    words = re.findall(r"[a-z\u00e0-\u024f]+", text.lower())
    if len(words) < min_words:
        return "unknown"

    word_set = set(words)
    scores = {}
    for lang, markers in LANG_MARKERS.items():
        hits = len(word_set & markers)
        scores[lang] = hits

    if not scores or max(scores.values()) < 3:
        return "unknown"

    return max(scores, key=scores.get)


def keyword_in_text(keyword, text):
    """Check if keyword appears in text with word boundary awareness.

    All single-word keywords use word boundary matching to prevent false
    positives like 'compose' matching 'composers' or 'design' matching
    'designated'. Multi-word phrases use substring matching since they're
    inherently specific (e.g., 'raspberry pi', 'power bi').
    """
    if " " not in keyword:
        pattern = r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])"
        return bool(re.search(pattern, text, re.IGNORECASE))
    else:
        return keyword.lower() in text.lower()


# ─── Stop Words (EN + NL + FR) ──────────────────────────────────────────────

STOP_WORDS = {
    # English function words
    "the", "a", "an", "is", "it", "in", "on", "at", "to", "for", "of", "and",
    "or", "but", "not", "with", "from", "by", "as", "this", "that", "was",
    "are", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "can", "if", "then",
    "so", "no", "yes", "up", "out", "all", "just", "also", "about", "its",
    "my", "your", "their", "our", "his", "her", "me", "you", "we", "they",
    "i", "he", "she", "what", "which", "who", "how", "when", "where", "why",
    "one", "two", "three", "some", "any", "each", "more", "most", "other",
    "new", "old", "first", "last", "get", "got", "like", "want", "need",
    "make", "use", "know", "see", "way", "thing", "here", "there", "very",
    "still", "now", "than", "too", "even", "much", "many", "well", "back",
    "only", "over", "such", "after", "before", "between", "same", "own",
    "while", "because", "through", "both", "few", "those", "these", "into",
    "them", "him", "us", "something", "nothing", "everything", "anything",
    "don", "doesn", "didn", "won", "wouldn", "couldn", "shouldn", "isn",
    "aren", "wasn", "weren", "hasn", "haven", "hadn", "let", "say", "said",
    "think", "look", "come", "go", "take", "give", "tell", "ask", "try",
    "call", "find", "put", "keep", "help", "show", "work", "part", "place",
    "case", "point", "hand", "turn", "start", "end", "line", "move", "long",
    "right", "left", "high", "big", "small", "great", "good", "bad", "sure",
    "able", "already", "really", "actually", "please", "thanks", "thank",
    "okay", "ok", "hi", "hello", "hey", "using", "used", "also", "just",
    "like", "want", "need", "make", "sure", "different", "specific",
    "example", "based", "create", "add", "set", "means", "lot", "bit",
    # Dutch function words
    "een", "het", "van", "dat", "die", "niet", "ook", "als", "zijn", "maar",
    "dan", "bij", "heb", "moet", "naar", "geen", "wil", "wel", "dit", "maak",
    "dus", "deze", "aan", "geef", "welke", "maken", "tot", "nog", "hebben",
    "mijn", "waar", "waarom", "uit", "worden", "alleen", "hoeveel", "per",
    "meer", "goed", "nee", "heeft", "andere", "jaar", "iets", "kan", "wat",
    "hoe", "met", "voor", "toch", "weer", "omdat", "heel", "over", "zou",
    "daar", "hier", "echt", "mag", "ben", "wordt", "alles", "graag", "weet",
    "misschien", "kun", "zelf", "waren", "werd", "hadden", "zonder",
    "onder", "door", "haar", "hem", "ons", "zij", "wij", "hij", "ik", "jij",
    "jullie", "hun", "uw", "erg", "veel", "weinig", "gaan", "doen", "zien",
    "komen", "staan", "geven", "vragen", "laten", "nemen", "zetten", "houden",
    "liggen", "lopen", "zitten", "brengen", "denken", "willen", "kunnen",
    "moeten", "zullen", "mogen", "eerst", "tweede", "derde", "bijvoorbeeld",
    "echter", "eigenlijk", "natuurlijk", "daarom", "ongeveer", "daarna",
    "verder", "altijd", "nooit", "soms", "vaak", "elke", "elk", "ander",
    "zelfde", "nieuwe", "grote", "kleine", "goede", "hele", "volgende",
    "vorige", "laatste", "eerste", "twee", "drie", "vier", "vijf",
    "meestal", "meest", "vind", "weten", "gebruik", "verschillende",
    "bepaalde", "soort", "manier", "zeker", "beetje", "gewoon", "best",
    "nog", "net", "toe", "samen", "tussen", "langs", "achter", "boven",
    "beneden", "binnen", "buiten", "klopt", "precies", "inderdaad",
    "volgens", "namelijk", "zodat", "zodra", "voordat", "totdat",
    # French function words
    "les", "des", "une", "est", "pas", "que", "qui", "dans", "sur", "pour",
    "avec", "plus", "sont", "nous", "vous", "ils", "elle", "mais", "aussi",
    "cette", "tout", "bien", "fait", "peut",
}

# Words that pass stop word filters but are too generic to define a topic.
# These appear in many conversations regardless of subject matter.
GENERIC_WORDS = {
    # Dutch generic filler
    "kunt", "waarbij", "nodig", "extra", "vooral", "enkele", "inclusief",
    "geschikt", "wilt", "mensen", "zoals", "modern", "hieronder",
    "overzicht", "vraag", "direct", "belangrijke", "belangrijk", "simpel",
    "hoog", "correct", "uitleg", "combinatie", "bekend", "aantal", "times",
    "voorbeeld", "ervoor", "berekenen", "text", "beste", "makkelijk",
    "welk", "gebruiken", "tips", "bijv.", "punt", "stel", "elkaar", "stap",
    "vul", "netjes", "klein", "frac", "gewone", "factoren", "geval",
    "betekent", "helder", "jouw", "normaal", "hebt", "blijven", "wanneer",
    "iedereen", "keer", "ziet", "duidelijk", "waarschijnlijk", "etc.",
    "komt", "vrijwel", "vervangen", "gebruikt", "anders", "hangt", "werkt",
    "concreet", "alle", "basis", "klinkt", "specifiek", "meerdere",
    "bereken", "totaal", "doorgaans", "waaronder", "biedt", "verschillen",
    "volledig", "gaat", "zorgt", "zich", "staat", "krijgt", "minder",
    "spelen", "optie.", "situatie", "doet", "beide", "risico", "tijd",
    "praktische", "recepten", "prima", "laag", "structuur", "klassieke",
    "dezelfde", "verslag", "zoekt", "perfect", "echte", "kosten", "prijs",
    "algemene", "volgt", "gegeven", "formule", "gelijk", "voorbeelden",
    "gebaseerd", "traditionele", "onderdeel", "specifieke", "functies",
    "functie", "werken", "standaard", "vaste", "landen", "automatisch",
    "systeem", "maken.", "begin", "gemiddelde", "mooi", "strak", "super",
    "vergelijking", "afbeelding", "laat", "plek", "cultuur", "groot",
    "excuses", "morgen", "wandelen", "stappen", "terug", "open",
    "doel", "ruimte", "mogelijk", "details", "logische",
    "waarden", "waarde", "tabel", "kolom", "draait", "tonen",
    "toon", "eens", "bekende", "resultaat", "zorgen", "aangepaste",
    "versie", "omgeving", "termen", "term", "onderscheid",
    "hoewel", "typisch", "eventueel", "beheren", "taken", "oude",
    "plaats", "terwijl", "rond", "rest", "iemand", "dingen", "blijft",
    "kort", "gebeurt",
    # Dutch verbs/adjectives that appear across all topics
    "selecteer", "kies", "klik", "gericht", "bevat", "voldoen",
    "eisen", "zakelijke", "antwoord", "genoemd", "vinden",
    "neem", "bent", "geeft", "stellen", "begrijpen", "leiden",
    "punten", "leggen", "ontwerp", "vast", "bestaande", "correcte",
    "eigen", "juiste", "allemaal", "stuk", "ervan", "genoeg",
    "zorg", "zowel", "erbij", "stijl", "richting", "liefst",
    "duur", "eenvoudig", "mogelijke", "helder", "praktisch",
    "vanuit", "keuze", "breed", "aspecten", "technische",
    "rollen", "verantwoordelijkheden", "locatie", "gezien", "tegen",
    "oorzaak", "oorzaken", "hoge", "kant", "probleem", "alternatief",
    "zoek", "meiden", "instellingen", "nederland",
    # English generic filler
    "entire", "check", "once", "happens", "answer", "including",
    "technical", "provide", "include", "information", "typically",
    "event", "detection", "sometimes", "basically", "probably",
    "definitely", "maybe", "simple", "short", "clean", "formally",
    "basic", "important", "state", "directly", "seems", "searching",
    "source", "search", "looking", "often", "known", "full", "figures",
    "down", "break", "support", "organization", "difference", "works",
    "ensure", "service", "object", "close", "real", "roll", "together",
    "compared", "third-party", "touch", "data", "needs", "common",
    "process", "management", "style", "prompt", "steps", "usually",
    "especially", "people", "terms", "technology", "digital",
    "breakdown", "examples", "without", "platform", "type",
    "single", "within", "chat", "access", "roles", "entity",
    "products", "selections", "background", "size",
    # English conversational/structural filler
    "working", "time", "project", "structure", "below", "structured",
    "setup", "clear", "select", "click", "running", "likely",
    "current", "minimal", "elements", "white", "image",
    "detailed", "environment", "cannot", "explicitly", "must",
    "feel", "free", "looks", "around", "question", "message",
    "explanation", "focus", "general", "application",
    "columns", "list", "analysis", "active", "apps", "services",
    "setting", "lighting", "soft", "aspect", "online",
    "capabilities", "training", "team", "platforms",
    # English verbs/adverbs/adjectives that appear across all topics
    "involves", "provides", "allows", "allow", "trying", "existing",
    "understood", "showing", "continue", "practical", "critical",
    "clearly", "however", "unless", "fully", "several", "generally",
    "typical", "possible", "limited", "goal", "purpose", "objectives",
    "value", "reasons", "issues", "function", "replacement", "role",
    "pattern", "follow", "during", "higher", "lower", "mean",
    "true", "global", "multi", "always", "almost", "instead",
    "next", "across", "multiple", "exactly",
    "reference", "angle", "beyond", "session", "original", "primary",
    "normal", "window", "things", "require", "made", "feature",
    "option", "options", "near", "distinct", "consistent", "lines",
    "head", "slightly", "side", "pack", "measure", "factors",
    "refers", "central", "approach", "manage", "cause", "damage",
    # Dutch generic verbs/adjectives/filler
    "professioneel", "professionele", "inhoudelijk", "sterke",
    "aanpassingen", "bekijken", "verdere", "geleverd", "relatie",
    "werk", "prestaties", "voordelen", "omvat", "gelden", "regels",
    "geldt", "ergens", "taak", "voorwaarden", "uitvoeren",
    "extreem", "klassiek", "sneller", "apart", "achtig", "aparte",
    "fout", "lekker", "zegt", "meteen", "lagere", "voorkomen",
    "nadruk", "benadrukt", "verandering", "vastgelegd", "wijzigingen",
    "beschrijft", "lengte", "rechts",
    # Dutch reference/connector words (pass stop word filter but aren't topics)
    "hierbij", "daarbij", "daarmee", "daarin", "daarvoor", "daarvan",
    "daaruit", "hiervan", "hierin", "hiermee", "hierop", "hiervoor",
    "waarop", "waarvan", "waarmee", "waarvoor", "waarin", "waaruit",
    # English generic (remaining)
    "managing", "effectively", "principles", "creating", "consider",
    "maintain", "suitable", "generate", "offers", "advanced",
    "range", "center", "longer", "become", "actual", "depends",
    "definition", "customers", "connections",
    # ChatGPT search/product artifacts
    "turn0search0", "turn0search1", "turn0search2", "turn0search3",
    "turn0search4", "turn0search5", "turn0search6", "turn0search7",
    "turn0search8", "turn0search9", "turn0search10",
    "turn0product0", "turn0product1", "turn0product2", "turn0product3",
    "turn0product4", "turn0product5", "turn0product6", "turn0product7",
    "referenced_image_ids", "x1024",
    # Image/DALL-E description words (not topics)
    "blue", "bright", "yellow", "green", "dark", "light", "black", "white",
    "wearing", "hair", "large", "scene", "color", "colors", "sharp",
    "overall", "tall", "bold", "standing", "sitting", "holding", "photo",
    "person", "woman", "background", "foreground", "portrait", "realistic",
    "transparent", "logo", "visible", "smooth", "texture", "shadow",
    "illustration", "cartoon", "rendering", "composition", "visual",
    "suggesties", "zoeken",
    # Assistant response filler (not topics — these leak from GPT's writing style)
    "crucial", "specifically", "accurate", "focused", "required",
    "related", "controls", "external",
    "needed", "shows", "choose", "enough", "better",
    "errors", "focuses",
    "referenced",
    "deliverables", "resultaten",
    "gestandaardiseerde",
    "toepassing", "maximale", "betrouwbare", "minimale",
    "begrip", "vermeld",
}


def tokenize(text):
    """Split text into lowercase tokens, min length 3, filtering stop words."""
    words = re.findall(r"[a-z\u00e0-\u024f][a-z\u00e0-\u024f0-9]{2,}", text.lower())
    return [w for w in words if w not in STOP_WORDS]
