# Writing Analyzer API

The API behind [Prose Analyzer](https://laureny.org/side-builds/writing-analyzer/). Send a passage. The response describes it sentence by sentence: counts, ratios, and the words the page highlights. The server reads the text, answers, and discards it.

The measures come from five sources on how sentences work, plus two published formulas. The numbers describe the passage.

## Measures

The JSON follows the sections of the page.

**Summary.** Word count, sentence count, and reading time at 250 words a minute. Lexical density is the share of words that are nouns, proper nouns, verbs, adjectives, or adverbs (Jean Ure). Flesch Reading Ease is the 1948 formula. The grade beside it is Flesch–Kincaid.

**Ratios.** Lexical verbs per common noun, lexical verbs per manner adverb, and common nouns per adjective. Auxiliaries are left out of the verb count. When *be* is a copula, a progressive, or a passive, spaCy tags it as an auxiliary, so a *be*-heavy passage would otherwise disappear. Those uses are counted on their own and returned as a share of the text.

**Shares.** How much of the passage is a form of *be*, a preposition, a zombie noun, or an *-ly* adverb.

**Rhythm.** The length of every sentence, with the mean, the median, and the standard deviation. This is Lanham’s sentence-length rhythm.

**Tactical.** Weak verbs, filler words, zombie nouns, *-ly* adverbs, nouns and verbs repeated within twenty words, and the first word of each sentence. Clause counts. Parallel syntax, when two neighboring sentences of at least five words have a similar part-of-speech sequence. Each sentence is also typed two ways. By the position of its main verb it is cumulative, balanced, or periodic. By how its clauses join it is simple, paratactic, or hypotactic.

**Sentences.** The sentence text, and character offsets for the highlighted words. A mark is `weak`, `ly`, `zombie`, or `filler`.

Weak verbs, when they are the main verb, are *get, make, do, go, seem, take, put,* and *give*. A zombie noun is a common noun of six or more letters ending in *-tion, -sion, -ment, -ence, -ance, -ity, -ness, -ship, -ancy, -ency, -ism,* or *-ure*, excluding ordinary words such as *city, moment,* and *nature*.

## Inspirations and references

The notes below follow the list at the top of the [Prose Analyzer](https://laureny.org/side-builds/writing-analyzer/) page.

- **Sarah Kaufman, *Verb Your Enthusiasm*.** The case for strong, precise verbs. Shapes Word choice and the weak-verb boxes.
- **Claire Kehrwald Cook, *Line by Line: How to Edit Your Own Writing*.** Sentence-level editing: cutting wordiness, prepositional chains, and nominalizations, and keeping parallel structures parallel. Shapes Word choice and Tactical.
- **Richard A. Lanham, *Analyzing Prose*.** Style as a set of choices: noun style against verb style, running against periodic sentences, coordination against subordination, and the rhythm of sentence length. Shapes Sentence rhythm, Word choice, and the clause-linkage counts in Tactical.
- **Virginia Tufte, *Artful Sentences: Syntax as Style*.** A catalogue of sentence structures, shown through published prose: openings, appositives, parallelism, cumulative sentences. Shapes Tactical: openers, typology, and parallel syntax. Published by Graphics Press, her son Edward Tufte’s imprint.
- **Helen Sword, “Zombie Nouns,” *The New York Times*, 2012.** Nouns built from verbs and adjectives that drain the life from a sentence. The source of the term, and of the zombie-noun shading in Word choice.

Formulas, and the design of the page that calls this API:

- Rudolf Flesch, “A New Readability Yardstick,” *Journal of Applied Psychology*, 1948. Flesch Reading Ease, in Summary.
- Jean Ure, “Lexical density and register differentiation,” 1971. Lexical density, in Summary.
- Edward Tufte, *The Visual Display of Quantitative Information*. The page’s look: sidenotes, small multiples, the sentence portrait. That design is on the site. This API returns the numbers.

## Privacy

The text arrives in the POST body. It is not logged, cached, or stored. A finished request is logged as a word count. A failed one is logged as a word count, without a traceback, because a traceback can carry the text. The container runs uvicorn with `--no-access-log`, so request lines stay out of the logs. The response includes the sentences, so the page can draw them, and the server keeps nothing.

OpenAPI, Swagger, and ReDoc are off.

## API

`GET /` returns `{"ok": true}`.

`POST /analyze` takes JSON:

```json
{"text": "She crossed the room. The decision was a disappointment."}
```

An empty text returns 400. More than 2,000 whitespace-separated tokens returns 413. The page is built for passages of about 100 to 2,000 words. For a longer piece, send one scene at a time.

This is the response for that passage, from `en_core_web_sm`. *Decision* ends in *-sion* and *disappointment* in *-ment*, so both are marked as zombie nouns.

```json
{
  "text": "She crossed the room. The decision was a disappointment.",
  "summary": {
    "words": 9,
    "sentences": 2,
    "reading_time_min": 0.04,
    "lexical_density": 44.4,
    "flesch_ease": 70.7,
    "flesch_grade": 4.5
  },
  "ratios": {
    "verb_noun": 0.33,
    "verb_manner_adverb": null,
    "noun_adjective": null
  },
  "shares": {
    "be_pct": 11.1,
    "prep_pct": 0.0,
    "zombie_pct": 22.2,
    "ly_pct": 0.0
  },
  "rhythm": {
    "mean": 4.5,
    "median": 4.5,
    "sd": 0.5,
    "lengths": [4, 5]
  },
  "tactical": {
    "weak_verbs": {},
    "repeats": [],
    "openers": {"she": 1, "the": 1},
    "filler": {},
    "zombies": {"decision": 1, "disappointment": 1},
    "ly_words": {},
    "clauses": {
      "total": 2,
      "per_sentence": 1.0,
      "max": {"sentence": 1, "clauses": 1}
    },
    "position": {"Cumulative": 1, "Balanced": 1},
    "connection": {"Simple": 2},
    "root_ratio_mean": 0.33,
    "parallels": [],
    "abstract_pronouns": {}
  },
  "sentences": [
    {
      "text": "She crossed the room.",
      "start": 0,
      "words": 4,
      "clauses": 1,
      "position": "Cumulative",
      "connection": "Simple",
      "marks": []
    },
    {
      "text": "The decision was a disappointment.",
      "start": 22,
      "words": 5,
      "clauses": 1,
      "position": "Balanced",
      "connection": "Simple",
      "marks": [[4, 8, ["zombie"]], [19, 14, ["zombie"]]]
    }
  ]
}
```

A ratio is `null` when its denominator is zero. An absent category stays null. A mark is `[offset, length, labels]`, with the offset counted from the start of that sentence.

Browsers may call the API only from origins in `ALLOWED_ORIGINS`, a comma-separated list of scheme and host, with no path. The default is `https://laureny.org`. Set the variable to override it. `www.laureny.org` redirects to that host, so one origin is enough.

```bash
curl -s localhost:8080/analyze \
  -H 'content-type: application/json' \
  -d '{"text":"She crossed the room. The decision was a disappointment."}'
```

## Run it locally

Python 3.12. The pinned spaCy model, `en_core_web_sm` 3.8.0, is what makes the install slow.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

## How a word is counted

Every ratio uses one base. A word is a token that is not punctuation, not whitespace, and not a possessive clitic, so a form like *writer's* counts as one word. The 2,000-word cap is a coarser count. It splits on whitespace, and it runs before parsing.

Syllables are an approximation. Only the Flesch formulas use them.

Parsing is spaCy’s `en_core_web_sm`. The tags from that model decide what counts as a verb, a noun, or an adverb.

## Deploy

The `Dockerfile` is for Cloud Run. Cloud Run sets `PORT`. The process listens on `0.0.0.0` and that port, with access logs off. Set `ALLOWED_ORIGINS` on the service when the calling site is not the default.
