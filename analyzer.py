"""Writing Analyzer metrics, extracted from `Writing Analyzer.ipynb` (cell 5).

The functions from `preprocess_text` to `compute_stats` are copied unchanged so the
numbers match the notebook. `to_json` at the bottom is new: it turns the stats dict
(which holds spaCy objects) into plain JSON for the web page.
"""
import re
from collections import Counter, OrderedDict
from difflib import SequenceMatcher

import numpy as np
import spacy

nlp = spacy.load("en_core_web_sm")

"""
Line-editing statistics for English prose.

Key conventions (deliberate, documented):

1. VERB counts exclude AUX. Under Universal Dependencies, `be` is AUX whenever it
   acts as copula, progressive or passive marker, so in be-heavy literary prose a
   large share of main predicates is NOT counted as a verb. The ratio is therefore
   labelled "lexical verb to common noun", and the AUX / be counts are printed
   next to it so the excluded mass is always visible.
2. One single word base is used for every denominator: tokens that are not
   punctuation, not whitespace, and not the possessive clitic. "Rester's" counts
   as one word, not two.
3. Ratios with a zero denominator return None and print as "N/A", never 0.00.
4. Adverbs are classified structurally (dependency + head POS), not by a spelling
   blacklist. Phrasal-verb particles carry tag_ == "RP" / dep_ == "prt" and are
   excluded that way rather than by listing "up", "out", "off" etc.
"""


# =============================================================================
# 0. PREPROCESSING
# =============================================================================

def preprocess_text(raw):
    """Strip markdown artefacts that would otherwise be tokenised or would
    corrupt sentence segmentation."""
    text = raw.replace("\u00a0", " ")
    # section separators on their own line: ***  ---  ___
    text = re.sub(r"(?m)^\s*(?:\*{3,}|-{3,}|_{3,})\s*$", "", text)
    # markdown emphasis markers
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"(?<![_\w])_(?=\w)|(?<=\w)_(?![_\w])", "", text)
    # collapse runs of blank lines into a single paragraph break
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_word(token):
    """The single word base used for every denominator in this script."""
    return (
        not token.is_punct
        and not token.is_space
        and token.tag_ != "POS"          # possessive clitic: Rester + 's -> 1 word
    )


# =============================================================================
# 1. SYLLABLES (approximation; documented as such)
# =============================================================================

def count_syllables(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|[^laeiouy]ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    groups = re.findall(r"[aeiouy]{1,2}", w)
    return max(1, len(groups))


# =============================================================================
# 2. ADVERB CLASSIFICATION (structural, mutually exclusive)
# =============================================================================

TEMPORAL_ADV = {
    "now", "then", "already", "soon", "later", "yesterday", "today",
    "tomorrow", "again", "afterwards", "afterward", "meanwhile", "tonight",
    "recently", "nowadays", "finally", "eventually", "once", "first",
    "last", "next",
}

DISCOURSE_ADV = {
    "however", "thus", "therefore", "instead", "furthermore", "moreover",
    "besides", "otherwise", "nevertheless", "nonetheless", "hence", "anyway",
    "also", "indeed",
}

FREQUENCY_ADV = {
    "always", "often", "rarely", "seldom", "sometimes", "usually",
    "ever", "occasionally", "frequently",
}

# Directional adverbs. spaCy only labels a subset of phrasal-verb particles as
# RP / prt: `step aside`, `came back`, `running around` all come back as plain
# RB / advmod, structurally identical to a manner adverb. A minimal closed list
# is therefore unavoidable, but it applies only when the head is verbal, so
# `holding still` and `far` in other roles are untouched.
DIRECTIONAL_ADV = {
    "out", "back", "away", "down", "up", "off", "around", "aside", "over",
    "in", "on", "through", "apart", "forward", "ahead", "along", "together",
    "home", "inside", "outside", "upstairs", "downstairs", "abroad",
}

# reported as an overlay, NOT deducted from any bucket
STANCE_ADV = {
    "always", "never", "often", "rarely", "seldom", "sometimes", "usually",
    "ever", "just", "even", "only", "still", "simply", "merely", "almost",
}

ADV_BUCKETS = ("manner", "degree", "temporal", "frequency", "negation",
               "discourse", "particle", "other")


def classify_adverb(token):
    """Return exactly one bucket from ADV_BUCKETS."""
    low = token.lower_
    if token.dep_ == "neg" or low in ("not", "n't", "never"):
        return "negation"
    if token.tag_ == "RP" or token.dep_ == "prt":
        return "particle"
    head_pos = token.head.pos_
    if low in DIRECTIONAL_ADV and head_pos in ("VERB", "AUX"):
        return "particle"
    if low in DISCOURSE_ADV:
        return "discourse"
    if low in TEMPORAL_ADV:
        return "temporal"
    if low in FREQUENCY_ADV:
        return "frequency"
    if head_pos in ("ADJ", "ADV"):
        return "degree"
    if low.endswith("ly"):
        return "manner"
    if token.dep_ in ("advmod", "npadvmod") and head_pos in ("VERB", "AUX"):
        return "manner"
    return "other"


def adverb_profile(words):
    buckets = Counter()
    examples = {k: [] for k in ADV_BUCKETS}
    for t in words:
        if t.pos_ != "ADV":
            continue
        cat = classify_adverb(t)
        buckets[cat] += 1
        examples[cat].append(t.text.lower())
    stance = Counter(
        t.lower_ for t in words if t.lower_ in STANCE_ADV
    )
    return buckets, examples, stance


# =============================================================================
# 3. POS RATIOS
# =============================================================================

def safe_ratio(numerator, denominator):
    """None, not 0.0, when the denominator is empty. 0.0 would read as the
    worst possible score when it actually means the category is absent."""
    if denominator <= 0:
        return None
    return numerator / denominator


def calculate_pos_ratios(words):
    nouns = sum(1 for t in words if t.pos_ == "NOUN")          # excludes PROPN
    propn = sum(1 for t in words if t.pos_ == "PROPN")
    verbs = sum(1 for t in words if t.pos_ == "VERB")          # excludes AUX
    aux = sum(1 for t in words if t.pos_ == "AUX")
    be_tokens = sum(1 for t in words if t.lemma_.lower() == "be")
    adjs = sum(1 for t in words if t.pos_ == "ADJ")

    buckets, adv_examples, stance = adverb_profile(words)
    manner_adv = buckets["manner"]

    return {
        "nouns_count": nouns,
        "propn_count": propn,
        "verbs_count": verbs,
        "aux_count": aux,
        "be_count": be_tokens,
        "adj_count": adjs,
        "adv_buckets": buckets,
        "adv_examples": adv_examples,
        "stance_adv": stance,
        "manner_adv_count": manner_adv,
        "v_n_ratio": safe_ratio(verbs, nouns),
        "v_adv_ratio": safe_ratio(verbs, manner_adv),
        "n_adj_ratio": safe_ratio(nouns, adjs),
    }


# =============================================================================
# 4. ZOMBIE NOUNS
# =============================================================================

ZOMBIE_SUFFIXES = (
    "tion", "sion", "ment", "ence", "ance", "ity", "ness",
    "ship", "ancy", "ency", "ism", "ure",
)

ZOMBIE_EXCEPTIONS = {
    "city", "moment", "century", "entity", "quality", "nature", "future",
    "picture", "creature", "gesture", "furniture", "sentence", "science",
    "silence", "audience", "figure", "measure", "leisure", "pleasure",
    "chance", "france", "prince", "office", "notice", "minute", "manure",
    "architecture", "temperature", "literature", "adventure", "structure",
    "culture", "capture", "venture", "society", "activity", "community",
}


def find_zombie_nouns(words):
    hits = []
    for t in words:
        if t.pos_ != "NOUN":
            continue
        low = t.lower_
        if len(low) < 6:
            continue
        if low in ZOMBIE_EXCEPTIONS or t.lemma_.lower() in ZOMBIE_EXCEPTIONS:
            continue
        if low.endswith(ZOMBIE_SUFFIXES):
            hits.append(low)
    return hits


# =============================================================================
# 5. ABSTRACT PRONOUNS
# =============================================================================

def find_abstract_pronouns(words):
    """`that` only as pronoun/determiner (never as complementiser);
    `there` only as expletive; `it` kept whole but reported separately."""
    counts = Counter()
    for t in words:
        low = t.lower_
        if low == "it":
            counts["it"] += 1
        elif low == "this":
            counts["this"] += 1
        elif low == "that":
            if t.pos_ in ("PRON", "DET") and t.dep_ != "mark":
                counts["that"] += 1
        elif low == "there":
            if t.dep_ == "expl":
                counts["there"] += 1
    return counts


# =============================================================================
# 6. SENTENCE TYPOLOGY (two independent, mutually exclusive dimensions)
# =============================================================================

SUB_DEPS = {"mark", "advcl", "relcl", "acl", "ccomp", "csubj", "csubjpass"}
CLAUSE_DEPS = {
    "ROOT", "ccomp", "xcomp", "advcl", "acl", "relcl",
    "csubj", "csubjpass", "pcomp",
}


def has_clausal_coordination(sent):
    """A `cc` counts only when it actually joins two clauses, i.e. its head has
    a verbal `conj` child. Otherwise `hopes and illusions` would read as
    parataxis."""
    for t in sent:
        if t.dep_ != "cc":
            continue
        head = t.head
        if head.pos_ in ("VERB", "AUX"):
            for child in head.children:
                if child.dep_ == "conj" and child.pos_ in ("VERB", "AUX"):
                    return True
    return False


def classify_sentence(sent):
    s_words = [t for t in sent if is_word(t)]
    s_len = len(s_words)

    position = None
    root_ratio = None
    if s_len > 0:
        root = next((t for t in sent if t.dep_ == "ROOT"), None)
        if root is not None and root in s_words:
            idx = [t.i for t in s_words].index(root.i)
            root_ratio = idx / s_len
            if root_ratio < 0.35:
                position = "Cumulative"
            elif root_ratio > 0.75:
                position = "Periodic"
            else:
                position = "Balanced"
    if position is None:
        position = "Unparsed"

    has_sub = any(
        t.dep_ in SUB_DEPS or t.pos_ == "SCONJ" for t in sent
    )
    if has_sub:
        connection = "Hypotaxis"
    elif has_clausal_coordination(sent):
        connection = "Parataxis"
    else:
        connection = "Simple"

    return position, connection, root_ratio, s_len


# =============================================================================
# 7. MAIN COMPUTATION
# =============================================================================

WEAK_VERB_LEMMAS = {"be", "have", "get", "make", "do", "feel"}
TARGET_MODIFIERS = {
    "very", "intensely", "strongly", "significantly",
    "simply", "only", "merely",
}


def compute_stats(raw_text):
    text = preprocess_text(raw_text)
    doc = nlp(text)

    words = [t for t in doc if is_word(t)]
    word_count = len(words)
    base = word_count or 1
    sentences = list(doc.sents)
    sent_count = len(sentences) or 1

    stats = {"doc": doc, "words": words, "sentences": sentences,
             "word_count": word_count, "sent_count": len(sentences)}

    # --- summary ---------------------------------------------------------
    stats["reading_time_min"] = word_count / 250.0

    lexical = [t for t in words
               if t.pos_ in ("NOUN", "PROPN", "VERB", "ADJ", "ADV")]
    stats["lexical_density"] = len(lexical) / base * 100

    total_syllables = sum(count_syllables(t.text) for t in words)
    asl = word_count / sent_count
    asw = total_syllables / base
    stats["asl"] = asl
    stats["asw"] = asw
    stats["flesch_ease"] = 206.835 - 1.015 * asl - 84.6 * asw
    stats["flesch_grade"] = 0.39 * asl + 11.8 * asw - 15.59

    # --- writer's diet (same word base as everything else) ---------------
    be_verbs = [t for t in words if t.lemma_.lower() == "be"]
    zombies = find_zombie_nouns(words)
    preps = [t for t in words if t.pos_ == "ADP"]
    ad_words = [t for t in words if t.pos_ in ("ADV", "ADJ")]
    abstract = find_abstract_pronouns(words)

    stats["diet"] = {
        "be_pct": len(be_verbs) / base * 100,
        "zombie_pct": len(zombies) / base * 100,
        "prep_pct": len(preps) / base * 100,
        "adword_pct": len(ad_words) / base * 100,
        "abstract_pct": sum(abstract.values()) / base * 100,
    }
    stats["be_count"] = len(be_verbs)
    stats["zombie_hits"] = Counter(zombies)
    stats["abstract_counts"] = abstract

    # --- ratios ----------------------------------------------------------
    stats["ratios"] = calculate_pos_ratios(words)

    # --- benchmark shares -------------------------------------------------
    all_adv = [t for t in words if t.pos_ == "ADV"]
    ly_adv = [t for t in all_adv if t.lower_.endswith("ly")]
    stats["shares"] = {
        "adv_pct": len(all_adv) / base * 100,
        "ly_pct": len(ly_adv) / base * 100,
        "adj_pct": stats["ratios"]["adj_count"] / base * 100,
        "adv_count": len(all_adv),
        "ly_count": len(ly_adv),
    }
    stats["shares"]["adj_adv_pct"] = (
        stats["shares"]["adj_pct"] + stats["shares"]["adv_pct"]
    )
    stats["ly_words"] = Counter(t.lower_ for t in ly_adv)

    stats["pos_counts"] = OrderedDict([
        ("Nouns (excl. PROPN)", stats["ratios"]["nouns_count"]),
        ("Proper Nouns", stats["ratios"]["propn_count"]),
        ("Adjectives", stats["ratios"]["adj_count"]),
        ("Lexical Verbs", stats["ratios"]["verbs_count"]),
        ("Auxiliaries", stats["ratios"]["aux_count"]),
        ("Manner Adverbs", stats["ratios"]["manner_adv_count"]),
        ("Prepositions", len(preps)),
        ("Pronouns", sum(1 for t in words if t.pos_ == "PRON")),
    ])
    stats["pos_pct"] = {k: v / base * 100 for k, v in stats["pos_counts"].items()}

    # --- sentences -------------------------------------------------------
    positions, connections, root_ratios, sent_lengths = [], [], [], []
    for sent in sentences:
        p, c, r, ln = classify_sentence(sent)
        positions.append(p)
        connections.append(c)
        if r is not None:
            root_ratios.append(r)
        sent_lengths.append(ln)

    stats["sent_lengths"] = sent_lengths
    stats["median_len"] = float(np.median(sent_lengths)) if sent_lengths else 0.0
    stats["std_len"] = float(np.std(sent_lengths)) if sent_lengths else 0.0
    stats["position_counts"] = Counter(positions)
    stats["connection_counts"] = Counter(connections)
    stats["root_ratio_mean"] = float(np.mean(root_ratios)) if root_ratios else None

    # shortest sentences: manual sanity check on segmentation
    order = sorted(range(len(sentences)), key=lambda i: sent_lengths[i])
    stats["shortest_sents"] = [
        (i + 1, sent_lengths[i], sentences[i].text.strip().replace("\n", " "))
        for i in order[:3]
    ]

    stats["openings"] = []
    for i, sent in enumerate(sentences):
        s_words = [t.text for t in sent if is_word(t)]
        stats["openings"].append((i + 1, " ".join(s_words[:4])))

    # --- clauses ---------------------------------------------------------
    clause_heads = [
        t for t in doc
        if t.dep_ in CLAUSE_DEPS and t.pos_ in ("VERB", "AUX")
    ]
    stats["clause_count"] = len(clause_heads)
    stats["clauses_per_sentence"] = len(clause_heads) / sent_count

    # --- parallelism -----------------------------------------------------
    pos_seqs = [[t.pos_ for t in sent if is_word(t)] for sent in sentences]
    parallels = []
    for i in range(len(pos_seqs) - 1):
        a, b = pos_seqs[i], pos_seqs[i + 1]
        if len(a) < 5 or len(b) < 5:
            continue
        if abs(len(a) - len(b)) / max(len(a), len(b)) > 0.20:
            continue
        sim = SequenceMatcher(None, a, b).ratio()
        if sim > 0.85:
            parallels.append((i + 1, i + 2, sim))
    stats["parallels"] = parallels

    # --- close repetition -------------------------------------------------
    sent_of_token = {}
    for s_i, sent in enumerate(sentences):
        for t in sent:
            sent_of_token[t.i] = s_i + 1

    last_seen = {}
    repeats = []
    for idx, token in enumerate(words):
        if token.pos_ not in ("NOUN", "VERB"):
            continue
        lemma = token.lemma_.lower()
        if lemma in WEAK_VERB_LEMMAS:
            continue
        if lemma in last_seen:
            prev_idx, prev_tok = last_seen[lemma]
            dist = idx - prev_idx
            if 0 < dist <= 20:
                repeats.append((
                    lemma, dist,
                    sent_of_token.get(prev_tok.i), sent_of_token.get(token.i),
                ))
        last_seen[lemma] = (idx, token)
    stats["repeats"] = repeats

    # --- vocabulary -------------------------------------------------------
    stats["weak_verbs"] = Counter(
        t.lower_ for t in words
        if t.lemma_.lower() in WEAK_VERB_LEMMAS and t.pos_ in ("VERB", "AUX")
    )
    stats["target_modifiers"] = Counter(
        t.lower_ for t in words if t.lower_ in TARGET_MODIFIERS
    )
    return stats


# =============================================================================
# 8. JSON FOR THE WEB PAGE (new; not in the notebook)
# =============================================================================

# Single-word list from the notebook's `highlighted_highrisk_words` (cell 9).
FILLER_WORDS = {
    "also", "only", "not", "however", "just", "too", "moreover", "besides",
    "case", "character", "degree", "factor", "instance", "level", "nature",
    "quality", "all", "something", "someone", "somebody", "anything", "anyone",
    "everything", "everyone", "nothing", "nobody", "each", "both", "few",
    "many", "several",
}


# The page's weak-verb list (from the mockup). The notebook's WEAK_VERB_LEMMAS is
# kept as is, since close-repetition detection uses it to skip common verbs.
# Only lexical verbs count, so the auxiliary in "did not go" is not flagged.
PAGE_WEAK_VERB_LEMMAS = {"get", "make", "do", "go", "seem", "take", "put", "give"}


def is_page_weak_verb(t):
    return t.pos_ == "VERB" and t.lemma_.lower() in PAGE_WEAK_VERB_LEMMAS


def _round(x, nd=2):
    return None if x is None else round(float(x), nd)


def _token_marks(t, zombie_ids):
    """Annotation classes for one word, as drawn on the page."""
    marks = []
    if is_page_weak_verb(t):
        marks.append("weak")
    if t.pos_ == "ADV" and t.lower_.endswith("ly"):
        marks.append("ly")
    if t.i in zombie_ids:
        marks.append("zombie")
    if t.lower_ in FILLER_WORDS:
        marks.append("filler")
    return marks


def to_json(stats):
    doc, words, sentences = stats["doc"], stats["words"], stats["sentences"]
    r, d, sh = stats["ratios"], stats["diet"], stats["shares"]
    lengths = stats["sent_lengths"]

    zombie_set = set(stats["zombie_hits"])
    zombie_ids = {t.i for t in words if t.pos_ == "NOUN" and t.lower_ in zombie_set}

    clause_by_sent = Counter()
    for t in doc:
        if t.dep_ in CLAUSE_DEPS and t.pos_ in ("VERB", "AUX"):
            clause_by_sent[t.sent.start] += 1

    sent_out = []
    for i, s in enumerate(sentences):
        position, connection, _, n = classify_sentence(s)
        marks = []
        for t in s:
            if not is_word(t):
                continue
            m = _token_marks(t, zombie_ids)
            if m:
                marks.append([t.idx - s.start_char, len(t.text), m])
        sent_out.append({
            "text": s.text,
            "start": s.start_char,
            "words": n,
            "clauses": clause_by_sent[s.start],
            "position": position,
            "connection": connection,
            "marks": marks,
        })

    longest = max(range(len(sent_out)), key=lambda i: sent_out[i]["clauses"], default=None)
    openers = Counter(
        (s["text"].split() or [""])[0].strip("\"“”‘’'(").lower() for s in sent_out
    )

    return {
        "text": doc.text,
        "summary": {
            "words": stats["word_count"],
            "sentences": stats["sent_count"],
            "reading_time_min": _round(stats["reading_time_min"]),
            "lexical_density": _round(stats["lexical_density"], 1),
            "flesch_ease": _round(stats["flesch_ease"], 1),
            "flesch_grade": _round(stats["flesch_grade"], 1),
        },
        "ratios": {
            "verb_noun": _round(r["v_n_ratio"]),
            "verb_manner_adverb": _round(r["v_adv_ratio"]),
            "noun_adjective": _round(r["n_adj_ratio"]),
        },
        "shares": {
            "be_pct": _round(d["be_pct"], 1),
            "prep_pct": _round(d["prep_pct"], 1),
            "zombie_pct": _round(d["zombie_pct"], 1),
            "ly_pct": _round(sh["ly_pct"], 1),
        },
        "rhythm": {
            "mean": _round(np.mean(lengths) if lengths else 0, 1),
            "median": _round(stats["median_len"], 1),
            "sd": _round(stats["std_len"], 1),
            "lengths": lengths,
        },
        "tactical": {
            "weak_verbs": dict(Counter(
                t.lower_ for t in words if is_page_weak_verb(t)).most_common()),
            "repeats": [list(x) for x in stats["repeats"]],
            "openers": dict(openers.most_common(5)),
            "filler": dict(Counter(
                t.lower_ for t in words if t.lower_ in FILLER_WORDS).most_common()),
            "zombies": dict(stats["zombie_hits"].most_common()),
            "ly_words": dict(stats["ly_words"].most_common()),
            "clauses": {
                "total": stats["clause_count"],
                "per_sentence": _round(stats["clauses_per_sentence"], 1),
                "max": None if longest is None else
                       {"sentence": longest + 1, "clauses": sent_out[longest]["clauses"]},
            },
            "position": dict(stats["position_counts"]),
            "connection": dict(stats["connection_counts"]),
            "root_ratio_mean": _round(stats["root_ratio_mean"]),
            "parallels": [[a, b, _round(s)] for a, b, s in stats["parallels"]],
            "abstract_pronouns": dict(stats["abstract_counts"]),
        },
        "sentences": sent_out,
    }


def analyze(raw_text):
    return to_json(compute_stats(raw_text))
