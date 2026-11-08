"""HTTP wrapper around analyzer.py.

Privacy rules (see plan.md in the blog repo): the text arrives in the POST body,
is never logged, cached or stored, and errors are logged without it.
"""
import logging
import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analyzer import analyze

MAX_WORDS = 2000
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS", "https://laureny.org"
).split(",")

log = logging.getLogger("analyzer")
logging.basicConfig(level=logging.INFO)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


class Payload(BaseModel):
    text: str


@app.get("/")
def health():
    return {"ok": True}


@app.post("/analyze")
def analyze_endpoint(payload: Payload):
    n = len(re.findall(r"\S+", payload.text))
    if n == 0:
        raise HTTPException(400, "Paste some text first.")
    if n > MAX_WORDS:
        raise HTTPException(413, f"Please keep it under {MAX_WORDS:,} words.")
    try:
        result = analyze(payload.text)
    except Exception:
        # No exc_info: a traceback could carry the text into the logs.
        log.error("analysis failed (%d words)", n)
        raise HTTPException(500, "Something went wrong analyzing this text.")
    log.info("analyzed %d words", n)
    return result
