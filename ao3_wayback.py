#!/usr/bin/env python3
"""
ao3_wayback.py -- survey what the Wayback Machine has archived for AO3 listings.

Point it at one or more AO3 tags (or collections, or users) and it will:
  1. Ask the Wayback CDX API for every archived capture of that listing.
  2. Fetch those captures and scrape work IDs plus metadata
     (title, author, summary, fandoms, word count, chapters, last updated).
  3. For each work, ask CDX what exists under /downloads/ (epub/pdf/mobi/azw3)
     and under /works/ (HTML reading pages, including ?view_full_work=true).
  4. Write works.csv, captures.csv and report.md.

Stdlib only. Python 3.8+. No install step.

Quick start:
  python3 ao3_wayback.py --tag-url "https://archiveofourown.org/tags/Some%20Tag/works"
  python3 ao3_wayback.py --tag "Steve Rogers/Bucky Barnes" --tag "Iron Lung"
  python3 ao3_wayback.py --tags-file my_tags.txt --out ./results --verbose

See README.md for the full rundown.
"""

import argparse
import csv
import datetime
import gzip
import html as htmlmod
import json
import os
import random
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

__version__ = "1.20.0"

CDX = "https://web.archive.org/cdx/search/cdx"
WB = "https://web.archive.org/web"
AO3 = "https://archiveofourown.org"
UA = f"ao3-wayback-survey/{__version__} (personal archival research)"

DOWNLOAD_EXTS = ("epub", "pdf", "mobi", "azw3", "html")
DEFAULT_SLEEP = 2.0   # base seconds between requests
MAX_EXTRA = 30.0      # ceiling on adaptive throttle added on top of base
RETRY_CODES = (429, 500, 502, 503, 504, 520, 522, 524)
COOLDOWN_AFTER = 6    # consecutive failed requests before a long pause
COOLDOWN_SECS = 90.0  # length of that pause
RETRY_PASSES = 2      # extra sweeps over works that failed or look suspect
GIVE_UP_AFTER = 12    # consecutive failed works before abandoning the run

META_FIELDS = ("title", "author", "summary", "fandoms", "rating", "warnings",
               "categories", "relationships", "characters", "freeform_tags",
               "words", "chapters", "updated", "meta_source")

# --------------------------------------------------------------------------
# AO3 TAG ESCAPING
# --------------------------------------------------------------------------
# AO3 does NOT percent-encode certain characters in tag URLs. It swaps them for
# asterisk-delimited codes FIRST, then percent-encodes the result. So the tag
#     Steve Rogers/Bucky Barnes
# becomes the path segment
#     Steve%20Rogers*s*Bucky%20Barnes
# with the literal asterisks usually themselves encoded as %2A.
#
# CONFIDENCE NOTE -- please read before trusting this table:
#   "/" -> "*s*"  CONFIRMED against a real AO3 relationship-tag URL.
#   The rest are reported widely but were NOT verified against AO3's source
#   (otwarchive, app/models/tag.rb) when this script was written. They are the
#   most likely failure point for an exotic tag.
#
# If a tag with one of these characters returns zero captures, that is the first
# thing to suspect. Use --tag-url instead (paste the URL straight from AO3 or
# the Wayback Machine) to bypass this table entirely, and please open an issue
# so the table can be corrected.
TAG_ESCAPES = {
    "/": "*s*",   # confirmed
    "&": "*a*",   # unverified
    ".": "*d*",   # unverified
    "?": "*q*",   # unverified
    "#": "*h*",   # unverified
}


def ao3_tag_to_path(tag_name):
    """
    Convert a human-readable tag into AO3's URL path segment.

    'Steve Rogers/Bucky Barnes' -> 'Steve%20Rogers%2As%2ABucky%20Barnes'

    Note what is NOT substituted: '|' (used in 'Character | Alias' tags),
    parentheses, apostrophes and colons are ordinary percent-encoded characters.
    """
    s = tag_name.strip()
    for raw, code in TAG_ESCAPES.items():
        s = s.replace(raw, code)
    # safe="" so that '*' and '/' both get percent-encoded, matching AO3.
    return urllib.parse.quote(s, safe="")


def slugify(s, maxlen=60):
    """Filesystem-safe name for per-source output folders."""
    s = urllib.parse.unquote(s)
    s = re.sub(r"[^\w\s-]", "_", s)
    s = re.sub(r"[\s_]+", "_", s).strip("_")
    return (s[:maxlen] or "listing").lower()


# --------------------------------------------------------------------------
# Source definitions -- what kind of AO3 listing to pull from
# --------------------------------------------------------------------------
# Every AO3 tag type (Fandom, Character, Relationship, Additional Tags,
# Archive Warning, Category, Rating) lives under the SAME /tags/<tag>/works
# path. There is no per-type URL. So "which category" is answered by which tag
# you name, not by a different endpoint. What genuinely differs is the listing
# container below.
SOURCE_TEMPLATES = {
    "tag":        "tags/{ident}/{listing}",
    "collection": "collections/{ident}/{listing}",
    "user":       "users/{ident}/{listing}",
    "pseud":      "users/{owner}/pseuds/{ident}/{listing}",
}

LISTINGS = ("works", "bookmarks")


class Source:
    """One AO3 listing to survey."""

    def __init__(self, path, label, kind="tag"):
        self.path = path.strip("/")
        self.label = label
        self.kind = kind
        self.slug = slugify(label)

    def __repr__(self):
        return f"<Source {self.kind} {self.label!r} -> {self.path}>"


def source_from_name(ident, kind="tag", listing="works", owner=None):
    if kind == "pseud" and not owner:
        raise ValueError("--pseud requires --user to name the account owner")
    enc = ao3_tag_to_path(ident) if kind == "tag" else urllib.parse.quote(ident, safe="")
    path = SOURCE_TEMPLATES[kind].format(
        ident=enc, listing=listing,
        owner=urllib.parse.quote(owner or "", safe=""))
    return Source(path, ident, kind)


def source_from_url(raw_url, listing="works"):
    """
    Accept a plain AO3 URL or a web.archive.org URL wrapping one, and keep its
    encoding byte-for-byte. This is the reliable path -- no escape-table guessing.
    """
    u = raw_url.strip()
    m = re.search(r"/web/\d{4,14}(?:id_|if_|im_|cs_|js_)?/(https?://.+)$", u)
    if m:
        u = m.group(1)
    m = re.search(r"archiveofourown\.org/((?:tags|collections|users)/.+?)(?:\?|$)", u)
    if not m:
        raise ValueError(f"No /tags/, /collections/ or /users/ path found in: {raw_url}")
    path = m.group(1).rstrip("/")
    if not path.rsplit("/", 1)[-1] in LISTINGS:
        path += "/" + listing
    kind = path.split("/", 1)[0].rstrip("s")
    label = urllib.parse.unquote(path.split("/")[1])
    return Source(path, label, kind)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

SLEEP = DEFAULT_SLEEP


# --------------------------------------------------------------------------
# Run log
# --------------------------------------------------------------------------
# Long runs used to need the caller to redirect output to a file by hand. That
# is easy to forget, and forgetting it is costly: a console keeps every line it
# has ever shown in memory, so a multi-hour run with detailed output can grow
# the terminal until it dies and takes the run with it.
#
# So the script keeps its own log instead. Detail always goes to the file;
# the console gets the progress lines and nothing else unless --verbose is
# given. Nobody has to remember anything, and the console stays small however
# long the run lasts.

class _Tee:
    """Write to a console stream, a log file, or both."""

    def __init__(self, console, logfile, to_console=True):
        self.console = console
        self.logfile = logfile
        self.to_console = to_console

    def write(self, text):
        if self.to_console and self.console is not None:
            try:
                self.console.write(text)
            except Exception:
                pass
        if self.logfile is not None:
            try:
                self.logfile.write(text)
            except Exception:
                pass
        return len(text)

    def flush(self):
        for s in (self.console if self.to_console else None, self.logfile):
            try:
                if s is not None:
                    s.flush()
            except Exception:
                pass

    def isatty(self):
        return bool(self.console is not None and self.console.isatty())


_LOG = {"file": None, "path": None}


def start_run_log(outdir, project, verbose=False):
    """
    Begin logging to <outdir>/<project>_run.log.

    stdout (progress) goes to both console and log. stderr (per-request
    detail) goes to the log always, and to the console only with --verbose.
    """
    try:
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, out_name(project, "run.log"))
        f = open(path, "a", encoding="utf-8", buffering=1)
    except OSError as e:
        sys.stderr.write(f"Could not open a run log ({e}); carrying on without one.\n")
        return None

    _LOG["file"], _LOG["path"] = f, path
    f.write(f"\n{'=' * 60}\n{datetime.datetime.now():%Y-%m-%d %H:%M:%S} "
            f"{' '.join(sys.argv)}\n{'=' * 60}\n")
    sys.stdout = _Tee(sys.__stdout__, f, to_console=True)
    sys.stderr = _Tee(sys.__stderr__, f, to_console=verbose)
    return path


def stop_run_log():
    if _LOG["file"] is not None:
        try:
            _LOG["file"].flush()
            _LOG["file"].close()
        except Exception:
            pass
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__


class EncodingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    Percent-encode redirect targets before following them.

    Wayback answers a replay request with a 302 to the canonical capture, and its
    Location header can carry the URL with raw '|', spaces or '*' in it. urllib
    follows redirects verbatim, so that malformed target goes straight back out
    as the next request line and the server rejects it with 400 -- which looks
    like "the capture is unavailable" when really it is our own second request
    that is broken. A browser encodes the Location before following; so do we.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            cleaned = urllib.parse.quote(newurl, safe=URL_SAFE)
        except Exception:
            cleaned = newurl
        return super().redirect_request(req, fp, code, msg, headers, cleaned)


_OPENER = urllib.request.build_opener(EncodingRedirectHandler)

# Header set to send. 'minimal' is what shipped in the first working version and
# is the default for a reason: adding 'Connection: keep-alive' broke every
# replay fetch with nginx's "Your browser sent an invalid request" 400, because
# urllib's http.client does not actually do keep-alive -- it closes the
# connection regardless, so the header asserts a capability the request does not
# honour. Do not add it back. 'browser' exists only as an escape hatch if
# web.archive.org ever starts refusing plain clients.
HEADER_STYLE = {"mode": "minimal"}


def request_headers():
    if HEADER_STYLE["mode"] == "browser":
        return {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
        }
    return {"User-Agent": UA, "Accept-Encoding": "gzip"}


# Adaptive throttle. The Internet Archive rate-limits aggressively on long runs:
# a few hundred CDX queries in a row will start returning 503. Rather than
# retrying at a fixed interval and getting throttled again, we raise a global
# delay whenever the server pushes back, and let it decay as requests succeed.
# This makes a long run slower at first and then self-correcting, instead of
# failing steadily.
_THROTTLE = {"extra": 0.0, "hits": 0, "streak": 0}

# Graceful stop. First Ctrl-C sets a flag: the current work finishes, results are
# checkpointed, spreadsheets are written from whatever is in hand, and the run
# exits cleanly so --resume can pick it up. Second Ctrl-C aborts immediately.
_STOP = {"requested": False, "count": 0}


def _sigint(signum, frame):
    _STOP["count"] += 1
    if _STOP["count"] >= 2:
        sys.stderr.write("\n[stop] Second interrupt -- aborting now.\n")
        raise KeyboardInterrupt
    _STOP["requested"] = True
    sys.stderr.write(
        "\n[stop] Finishing the current item, then saving what we have.\n"
        "       Press Ctrl-C again to abort immediately.\n")


def install_stop_handler():
    try:
        signal.signal(signal.SIGINT, _sigint)
    except (ValueError, OSError, AttributeError):
        pass  # not on the main thread, or unsupported -- fall back to hard exit


def stopping():
    return _STOP["requested"]


def pace():
    """Wait between requests: base delay plus whatever the throttle has learned."""
    if stopping():
        return  # don't idle once a stop is pending
    time.sleep(SLEEP + _THROTTLE["extra"])


def _penalize(verbose=False):
    _THROTTLE["hits"] += 1
    _THROTTLE["streak"] += 1
    _THROTTLE["extra"] = min(MAX_EXTRA, max(1.0, _THROTTLE["extra"] * 2))
    if verbose:
        sys.stderr.write(f"  [throttle] backing off to +{_THROTTLE['extra']:.1f}s\n")
    # A long unbroken run of failures means the per-request backoff isn't enough;
    # stop hammering entirely and let the rate limiter forget about us.
    if _THROTTLE["streak"] >= COOLDOWN_AFTER and not stopping():
        sys.stderr.write(f"  [cooldown] {_THROTTLE['streak']} failures in a row -- "
                         f"pausing {COOLDOWN_SECS:.0f}s to clear the rate limit\n")
        waited = 0.0
        while waited < COOLDOWN_SECS and not stopping():
            time.sleep(1.0)
            waited += 1.0
        _THROTTLE["streak"] = 0


def _relax():
    _THROTTLE["streak"] = 0
    if _THROTTLE["extra"]:
        _THROTTLE["extra"] *= 0.8
        if _THROTTLE["extra"] < 0.25:
            _THROTTLE["extra"] = 0.0


def _retry_after(e):
    """Honor a Retry-After header if the server sent one."""
    try:
        v = e.headers.get("Retry-After") if e.headers else None
        return min(120.0, float(v)) if v else None
    except (TypeError, ValueError):
        return None


def fetch(url, tries=6, timeout=90, verbose=False):
    """GET with adaptive backoff. Returns bytes, or None on persistent failure."""
    for attempt in range(tries):
        req = urllib.request.Request(url, headers=request_headers())
        try:
            with _OPENER.open(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                # Only an answer with content counts as a success. An empty 200
                # is the rate limiter, and relaxing on it resets the failure
                # streak -- which silently prevents the cooldown below from ever
                # firing, because the streak keeps getting cleared by failures
                # dressed up as successes.
                if raw:
                    _relax()
                return raw
        except urllib.error.HTTPError as e:
            # 4xx (other than 429) are permanent: the request itself is wrong, so
            # repeating it verbatim can only fail the same way. Retrying a 400
            # five times just burns five rounds of backoff.
            if 400 <= e.code < 500 and e.code != 429:
                if e.code != 404:
                    sys.stderr.write(f"  HTTP {e.code} (permanent, not retrying)\n"
                                     f"    {url}\n")
                    # The server usually explains itself in the body. Showing it
                    # beats guessing at the cause from the status code alone.
                    try:
                        body = e.read(600).decode("utf-8", "replace")
                        body = WS_RE.sub(" ", TAG_RE.sub(" ", body)).strip()
                        if body:
                            sys.stderr.write(f"    server said: {body[:300]}\n")
                        final = e.geturl()
                        if final and final != url:
                            sys.stderr.write(f"    after redirect to: {final}\n")
                    except Exception:
                        pass
                return None
            if e.code in RETRY_CODES:
                _penalize(verbose)
            if attempt == tries - 1:
                sys.stderr.write(f"  GAVE UP (HTTP {e.code}) {url[:80]}...\n")
                return None
            # Jitter prevents a stalled batch from retrying in lockstep.
            wait = _retry_after(e) or min(
                120.0, (2 ** attempt) * SLEEP + random.uniform(0, 3))
            sys.stderr.write(f"  HTTP {e.code} -- retry {attempt + 1}/{tries - 1} "
                             f"in {wait:.0f}s\n")
            time.sleep(wait)
        except Exception as e:
            # Connection-level failures (URLError, resets, timeouts) are how a
            # rate limiter looks when it stops answering rather than replying
            # 503. Treat them as pushback too, or the adaptive delay never rises
            # and we keep hammering a server that is already refusing us.
            _penalize(verbose)
            if attempt == tries - 1:
                sys.stderr.write(f"  GAVE UP ({type(e).__name__}) {url[:80]}...\n")
                return None
            wait = min(120.0, (2 ** attempt) * SLEEP + random.uniform(0, 3))
            sys.stderr.write(f"  {type(e).__name__} -- retry {attempt + 1}/{tries - 1} "
                             f"in {wait:.0f}s\n")
            time.sleep(wait)
    return None


def cdx_query(url_pattern, match_type="prefix", extra=None, limit=20000,
              verbose=False):
    """
    Query the Wayback CDX index -- the real search endpoint for Wayback captures.

    Note: archive.org's "advanced search" page indexes archive.org's OWN uploaded
    items (books, audio, software). It does not index Wayback captures at all.
    CDX is the only way to search what the crawler saved.
    """
    params = {
        "url": url_pattern,
        "matchType": match_type,
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,length,digest",
        "collapse": "digest",
        "limit": str(limit),
        "gzip": "false",
    }
    if extra:
        params.update(extra)
    # doseq=True so a list value emits the param repeatedly (filter=a&filter=b),
    # which is how CDX takes multiple filters. Without it the list would be
    # stringified into one nonsense value.
    q = CDX + "?" + urllib.parse.urlencode(params, safe="*", doseq=True)
    raw = fetch(q, verbose=verbose)
    pace()

    # CRITICAL: None means "the query failed", [] means "no captures exist".
    # Collapsing these loses the difference between a work with nothing archived
    # and a work we simply never managed to ask about -- and the second kind
    # must be retried, not recorded as empty.
    if raw is None:
        return None
    body = raw.decode("utf-8", "replace").strip()
    if not body:
        # Under load the CDX server sometimes answers 200 with an empty body.
        # That is a failure wearing a success costume -- and because it arrives
        # as a success, _relax() has just LOWERED our delay. Penalise it.
        _penalize(verbose)
        return None
    try:
        rows = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not rows:
        return None          # valid JSON but no header row: malformed, not empty
    if len(rows) < 2:
        return []            # header only: genuinely zero captures
    header, data = rows[0], rows[1:]
    return [dict(zip(header, r)) for r in data]


# --------------------------------------------------------------------------
# HTML helpers
# --------------------------------------------------------------------------

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def cls(name):
    """
    Match a class attribute containing `name`, in either quote style.

    AO3's templates mix them within a single page:
        <li class='freeforms'><a class="tag" href="...">Slow Burn</a></li>
    Requiring double quotes silently loses the relationship, character and
    freeform tags, because those particular elements are single-quoted.
    Wayback's toolbar rewriting normalises quotes, so a page fetched without
    the 'id_' modifier parses while the raw original does not -- which makes
    this look like an archive problem rather than a parser bug.
    """
    return rf"""class=["'][^"']*\b{name}\b[^"']*["']"""


def text(fragment):
    """Strip tags, unescape entities, collapse whitespace to a single line."""
    if not fragment:
        return ""
    s = re.sub(r"<br\s*/?>", " ", fragment, flags=re.I)
    s = re.sub(r"</p\s*>", " ", s, flags=re.I)
    s = TAG_RE.sub("", s)
    return WS_RE.sub(" ", htmlmod.unescape(s)).strip()


def anchors(fragment):
    if not fragment:
        return []
    return [text(m.group(1))
            for m in re.finditer(r"<a\b[^>]*>(.*?)</a>", fragment, re.S | re.I)]


def grab(pattern, s, flags=re.S | re.I):
    m = re.search(pattern, s, flags)
    return m.group(1) if m else ""


def tags_by_class(chunk, name):
    """
    Collect tag names from every <li class="...<cls>..."> in a blurb's tag list.
    AO3 emits one <li> per tag, all sharing a class:
        <li class="relationships"><a class="tag">A/B</a></li>
        <li class="relationships"><a class="tag">C/D</a></li>
    """
    out = []
    for m in re.finditer(rf"<li[^>]*\b{cls(name)}[^>]*>(.*?)</li>",
                         chunk, re.S | re.I):
        out.extend(anchors(m.group(1)))
    return [t for t in out if t]


def required_tag(chunk, name):
    """
    Pull a value from AO3's <ul class="required-tags"> icon row, where rating,
    warnings and category appear as spans like
        <span class="rating-teen rating" title="Teen And Up Audiences">
    """
    val = grab(rf"""<span[^>]*\b{cls(name)}[^>]*title=["']([^"']*)["']""", chunk)
    if val:
        return text(val)
    # Some skins put the label in a nested <span class="text"> instead.
    frag = grab(rf"<span[^>]*\b{cls(name)}[^>]*>(.*?)</span>", chunk)
    return text(frag)


def joined(items):
    return " | ".join(items)


# --------------------------------------------------------------------------
# AO3 blurb extraction
# --------------------------------------------------------------------------
# AO3's work-blurb template is stable across tag, collection, user and bookmark
# listings, so slicing on <li class="work blurb group"> and matching inside each
# chunk is reliable. It is still regex-against-HTML: a truncated capture yields a
# work ID with empty metadata rather than a crash.

# Listings wrap each entry in a blurb <li>, but the leading word varies by
# page: "work blurb" on a tag or user works listing, "bookmark blurb" on a
# bookmarks page, "series blurb" in a series index. Matching on "blurb" alone
# covers all of them; the work ID is then taken from the entry's own /works/
# link, so an entry without one (a bookmarked series, or an external work) is
# skipped rather than mis-parsed.
BLURB_START = re.compile(
    r"""<li[^>]*\bclass=["'][^"']*\bblurb\b[^"']*["']""", re.I)


def parse_listing(page_html):
    """Parse an AO3 works/bookmarks listing page into {work_id: metadata}."""
    out = {}
    starts = [m.start() for m in BLURB_START.finditer(page_html)]
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(page_html)
        chunk = page_html[s:e]

        # Match hrefs whether or not Wayback has rewritten them. Without the
        # 'id_' modifier the replay page carries the Wayback toolbar, and part
        # of that injection rewrites href="/works/123" into a full
        # web.archive.org URL -- so anchoring on a leading "/works/" silently
        # loses every title on exactly those captures.
        wid = grab(r'id="work_(\d+)"', chunk) or grab(r'href="[^"]*/works/(\d+)', chunk)
        if not wid:
            continue

        heading = grab(rf"<h4[^>]*{cls('heading')}[^>]*>(.*?)</h4>", chunk)
        title = text(grab(r'<a[^>]*href="[^"]*/works/\d+[^"]*"[^>]*>(.*?)</a>', heading))

        authors = [text(m.group(1)) for m in re.finditer(
            r'<a\b[^>]*\brel="author"[^>]*>(.*?)</a>', heading, re.S | re.I)]
        if not authors:
            authors = ["Anonymous"] if "anonymous" in heading.lower() else []

        # Warnings appear as detailed <li class="warnings"> entries; if the blurb
        # only carries the icon-row summary, fall back to that.
        warnings = tags_by_class(chunk, "warnings")
        if not warnings:
            w = required_tag(chunk, "warnings")
            warnings = [w] if w else []

        out[wid] = {
            "title": title,
            "author": " | ".join(a for a in authors if a),
            "summary": text(grab(
                rf"<blockquote[^>]*{cls('summary')}[^>]*>(.*?)</blockquote>",
                chunk)),
            "fandoms": " | ".join(anchors(grab(
                rf"<h5[^>]*{cls('fandoms')}[^>]*>(.*?)</h5>", chunk))),
            "rating": required_tag(chunk, "rating"),
            "warnings": joined(warnings),
            "categories": required_tag(chunk, "category"),
            "relationships": joined(tags_by_class(chunk, "relationships")),
            "characters": joined(tags_by_class(chunk, "characters")),
            "freeform_tags": joined(tags_by_class(chunk, "freeforms")),
            "words": text(grab(rf"<dd[^>]*{cls('words')}[^>]*>(.*?)</dd>", chunk)),
            "chapters": text(grab(rf"<dd[^>]*{cls('chapters')}[^>]*>(.*?)</dd>", chunk)),
            "updated": text(grab(rf"<p[^>]*{cls('datetime')}[^>]*>(.*?)</p>", chunk)),
            "meta_source": "listing",
        }
    return out


def parse_work_page(page_html):
    """Fallback: pull metadata from an archived individual work page."""
    byline = grab(rf"<h3[^>]*{cls('byline')}[^>]*>(.*?)</h3>", page_html)
    authors = [text(m.group(1)) for m in re.finditer(
        r'<a\b[^>]*\brel="author"[^>]*>(.*?)</a>', byline, re.S | re.I)]
    if not authors and byline:
        authors = [text(byline)]

    return {
        "title": text(grab(
            rf"<h2[^>]*{cls('title')}[^>]*>(.*?)</h2>", page_html)),
        "author": " | ".join(a for a in authors if a),
        "summary": text(grab(
            rf"<div[^>]*{cls('summary')}[^>]*>.*?"
            rf"<blockquote[^>]*{cls('userstuff')}[^>]*>(.*?)</blockquote>",
            page_html)),
        "fandoms": joined(anchors(grab(
            rf"<dd[^>]*{cls('fandom')}[^>]*>(.*?)</dd>", page_html))),
        # On a work page the tag groups are <dd class="<name> tags"> blocks.
        "rating": joined(anchors(grab(
            rf"<dd[^>]*{cls('rating')}[^>]*>(.*?)</dd>", page_html))),
        "warnings": joined(anchors(grab(
            rf"<dd[^>]*{cls('warning')}[^>]*>(.*?)</dd>", page_html))),
        "categories": joined(anchors(grab(
            rf"<dd[^>]*{cls('category')}[^>]*>(.*?)</dd>", page_html))),
        "relationships": joined(anchors(grab(
            rf"<dd[^>]*{cls('relationship')}[^>]*>(.*?)</dd>", page_html))),
        "characters": joined(anchors(grab(
            rf"<dd[^>]*{cls('character')}[^>]*>(.*?)</dd>", page_html))),
        "freeform_tags": joined(anchors(grab(
            rf"<dd[^>]*{cls('freeform')}[^>]*>(.*?)</dd>", page_html))),
        "words": text(grab(rf"<dd[^>]*{cls('words')}[^>]*>(.*?)</dd>", page_html)),
        "chapters": text(grab(rf"<dd[^>]*{cls('chapters')}[^>]*>(.*?)</dd>", page_html)),
        "updated": text(grab(rf"<dd[^>]*{cls('status')}[^>]*>(.*?)</dd>", page_html)),
        "meta_source": "work page",
    }


def blank_meta():
    return {k: "" for k in META_FIELDS}


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------

def find_listing_captures(source, verbose=False):
    """
    Look for archived captures of this listing.

    Returns (rows, status) where status is one of:
      "ok"     -- captures found
      "none"   -- the index answered, and has nothing for this page
      "failed" -- every query failed, so we do not know either way

    That last distinction matters: a throttled CDX query returns nothing, and
    reporting it as "this page was never archived" would be a confident lie
    about the archive's contents.
    """
    variants = [
        ("as-given", source.path),
        ("double-encoded", urllib.parse.quote(source.path, safe="/")),
        ("decoded", urllib.parse.unquote(source.path)),
    ]
    seen, answered = set(), False
    for label, variant in variants:
        if variant in seen:
            continue
        seen.add(variant)
        pattern = f"archiveofourown.org/{variant}"
        if verbose:
            sys.stderr.write(f"[cdx] trying {label}: {pattern[:110]}\n")
        rows = cdx_query(pattern, match_type="prefix",
                         extra={"filter": "statuscode:200"})
        if rows is not None:
            answered = True
        if rows:
            if verbose:
                sys.stderr.write(f"[cdx] {label} -> {len(rows)} capture(s)\n")
            return rows, "ok"
    return [], ("none" if answered else "failed")


def archive_context(source, verbose=False):
    """
    When a listing has no captures, work out whether anything nearby does.

    Knowing that the account exists in the archive but its bookmarks page was
    never crawled is a different answer from the archive having never seen this
    corner of AO3 at all, and it tells the person what to try next. One extra
    query, only on the path that already came up empty.
    """
    parent = source.path.rsplit("/", 1)[0]
    if not parent or parent == source.path:
        return None
    rows = cdx_query(f"archiveofourown.org/{parent}", match_type="prefix",
                     extra={"filter": "statuscode:200"}, limit=200,
                     verbose=verbose)
    if not rows:
        return None
    pages = sorted({r["original"].split("?")[0] for r in rows})
    return parent, len(rows), pages[:6]


def replay_variants(ts, original):
    """
    Yield (label, url) spellings of a Wayback replay URL, best guess first.

    The first spelling is the one confirmed to work (see wayback_inner). The
    rest are fallbacks in case Wayback's handling differs for some captures.
    """
    double = wayback_inner(original)
    single = urllib.parse.quote(original, safe=URL_SAFE)

    for label, body, raw in (
        ("double-encoded", double, True),
        ("double, no-id_", double, False),
        ("single-encoded", single, True),
        ("single, no-id_", single, False),
    ):
        yield label, f"{WB}/{ts}{'id_' if raw else ''}/{body}"


def fetch_capture(ts, original, verbose=False, deep=False):
    """
    Fetch an archived capture, trying replay-URL spellings until one works.

    A 400 here is permanent for that spelling but says nothing about the others,
    so each variant costs exactly one request. The winning style is remembered
    and tried first from then on. Pass deep=True to try every spelling.
    """
    variants = list(replay_variants(ts, original))

    # Deliberately NOT memoising a winning style. One capture failing on the
    # preferred spelling says nothing about the next one, and locking onto a
    # fallback degrades every later fetch -- the no-id_ form in particular
    # returns the page wrapped in Wayback's toolbar, with its links rewritten.
    # Preferring the clean form each time costs one extra request only on the
    # captures that actually fail.

    # Some captures are simply broken on Wayback's side: every spelling returns
    # nginx's "invalid request" 400. Walking all seven costs seven requests to
    # learn nothing, and on a tag with a run of bad captures that is the
    # difference between a short pause and a run that looks dead. Try a couple,
    # then accept the capture is unavailable and move to the next one.
    if not deep:
        variants = variants[:2]

    for n, (label, url) in enumerate(variants):
        if stopping():
            return None
        body = fetch(url, verbose=verbose)
        pace()
        if body:
            if n > 0 and verbose:
                sys.stderr.write(f"  [replay] capture {ts} served via '{label}'\n")
            return body
        if verbose:
            sys.stderr.write(f"  [replay] '{label}' refused, trying next spelling\n")

    print(f"  Capture {ts} is unavailable on Wayback - skipping it.")
    return None


def scrape_listing(ts, original, verbose=False, deep=False, save_dir=None):
    """Fetch one archived listing capture and parse its work blurbs."""
    body = fetch_capture(ts, original, verbose, deep=deep)
    if not body:
        return {}

    # --save-listing: write the exact bytes the parser is about to read, so a
    # parsing problem can be diagnosed from real markup instead of guesswork.
    if save_dir:
        try:
            os.makedirs(save_dir, exist_ok=True)
            dest = os.path.join(save_dir, f"listing_{ts}.html")
            with open(dest, "wb") as f:
                f.write(body)
            print(f"  [saved] {dest} ({len(body):,} bytes)")
        except OSError as e:
            sys.stderr.write(f"  [saved] could not write listing dump: {e}\n")
    page = body.decode("utf-8", "replace")
    meta = parse_listing(page)
    if not meta:  # template miss -- at least recover bare IDs
        meta = {m.group(1): blank_meta() for m in re.finditer(r"/works/(\d+)", page)}
    if verbose:
        named = sum(1 for v in meta.values() if v.get("title"))
        sys.stderr.write(f"[listing] {ts} -> {len(meta)} work(s), {named} with titles\n")
    return meta


def fetch_work_meta(wid, pages, verbose=False):
    """Fallback metadata from the newest archived work page."""
    if not pages:
        return blank_meta()
    newest = sorted(pages, key=lambda r: r["timestamp"])[-1]
    body = fetch_capture(newest["timestamp"], newest["original"], verbose)
    if not body:
        return blank_meta()
    meta = parse_work_page(body.decode("utf-8", "replace"))
    if verbose:
        sys.stderr.write(f"[work {wid}] work-page metadata: {meta.get('title') or '(none)'}\n")
    return meta


# Exactly the files this script creates. --clean removes these by name and
# nothing else, so pointing --out at a folder holding other work can never cost
# you anything that wasn't ours to begin with.
DEFAULT_PROJECT = "ao3"

# Output filenames are prefixed with the project name so several tags can share
# one output folder without overwriting each other. The checkpoint is prefixed
# too -- otherwise resuming project B would load project A's progress.
LEGACY_NAMES = (
    ".progress.json", ".progress.json.tmp",
    "works.csv", "captures.csv", "report.md",
    "all_works.csv", "all_captures.csv",
)


def out_name(project, name):
    return f"{project}_{name}" if project else name


def artifact_names(project):
    """Every file this project writes, for --clean to remove by name."""
    names = [out_name(project, n) for n in
             ("progress.json", "progress.json.tmp", "works.csv", "captures.csv",
              "report.md", "all_works.csv", "all_captures.csv")]
    # Also clear files from before project naming existed, so --clean still
    # does what it says for anyone upgrading mid-task.
    return tuple(names) + LEGACY_NAMES


def interactive():
    """True when a person is at the terminal to see prompts and overwrites."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def unique_project(outdir, project, resuming):
    """
    Keep an unattended run from silently overwriting a previous one's output.

    If NAME_works.csv already exists, this returns NAME_2, NAME_3 and so on.
    Two cases are deliberately exempt: an attended run, where someone is there
    to notice the overwrite, and --resume, which must keep the same name or it
    would not be continuing anything.
    """
    if resuming or interactive():
        return project

    def taken(p):
        return any(os.path.exists(os.path.join(outdir, out_name(p, n)))
                   for n in ("works.csv", "captures.csv"))

    if not taken(project):
        return project
    for n in range(2, 1000):
        candidate = f"{project}_{n}"
        if not taken(candidate):
            print(f"  {out_name(project, 'works.csv')} already exists; "
                  f"writing this run as {candidate}_works.csv")
            return candidate
    return project


def ask_project(default):
    """
    Ask what to call this project's output files.

    Only prompts when a person is actually present: with stdin or stdout
    redirected (a scheduled run, nohup, or `*> run.log`) the prompt would be
    invisible and the script would look frozen, so the default is used instead.
    Pass --project to skip this entirely.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return default
    try:
        raw = input(f"\nProject name for the output files [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return slugify(raw) if raw else default


def _refuse_dangerous(outdir):
    """Guard against --out pointing somewhere a delete sweep shouldn't run."""
    real = os.path.realpath(outdir)
    if os.path.dirname(real) == real:          # filesystem or drive root
        raise ValueError(f"refusing to clean a drive root: {real}")
    if real == os.path.realpath(os.path.expanduser("~")):
        raise ValueError(f"refusing to clean your home directory: {real}")
    return real


def clean_run(outdir, project, verbose=False):
    """
    Delete artifacts from a previous run: checkpoint, spreadsheets and reports,
    at the top level and inside per-source subfolders. Subfolders are removed
    only if emptied, so anything else in them survives.
    """
    _refuse_dangerous(outdir)
    if not os.path.isdir(outdir):
        return 0

    removed = 0

    def drop(d):
        nonlocal removed
        for name in artifact_names(project):
            f = os.path.join(d, name)
            if os.path.isfile(f):
                try:
                    os.remove(f)
                    removed += 1
                    if verbose:
                        sys.stderr.write(f"  [clean] removed {f}\n")
                except OSError as e:
                    sys.stderr.write(f"  [clean] could not remove {f}: {e}\n")

    drop(outdir)
    for entry in sorted(os.listdir(outdir)):
        sub = os.path.join(outdir, entry)
        if os.path.isdir(sub):
            drop(sub)
            try:
                os.rmdir(sub)          # only succeeds if we emptied it
                if verbose:
                    sys.stderr.write(f"  [clean] removed empty folder {sub}\n")
            except OSError:
                pass                   # still has files that aren't ours

    return removed


def progress_path(outdir, project):
    return os.path.join(outdir, out_name(project, "progress.json"))


def load_progress(outdir, project, verbose=False):
    """Return (results, meta) from a previous interrupted run, or empty dicts."""
    p = progress_path(outdir, project)
    if not os.path.exists(p):
        return {}, {}, set()
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        results, meta = d.get("results", {}), d.get("meta", {})
        scraped = set(d.get("scraped_captures", []))

        # Migrate checkpoints written before status tracking existed. Back then a
        # failed query was indistinguishable from a real zero, so any entry with
        # nothing in it is re-queued rather than trusted.
        migrated = 0
        for wid, entry in results.items():
            if "status" not in entry:
                empty = not entry.get("downloads") and not entry.get("pages")
                entry["status"] = "suspect" if empty else "ok"
                migrated += empty
        if migrated:
            sys.stderr.write(
                f"[resume] {migrated} empty row(s) from an older run will be "
                f"re-queried (they may have been failed lookups)\n")
        if verbose:
            sys.stderr.write(f"[resume] {len(results)} work(s) already recorded, "
                             f"{len(scraped)} listing capture(s) already read\n")
        return results, meta, scraped
    except (json.JSONDecodeError, OSError) as e:
        sys.stderr.write(f"[resume] could not read checkpoint ({e}); starting fresh\n")
        return {}, {}, set()


def save_progress(outdir, project, results, meta, scraped=None):
    """Write atomically so an interrupt can't leave a half-written checkpoint."""
    os.makedirs(outdir, exist_ok=True)
    p = progress_path(outdir, project)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": __version__, "results": results,
                       "meta": meta,
                       "scraped_captures": sorted(scraped or ())}, f)
        os.replace(tmp, p)
    except OSError as e:
        sys.stderr.write(f"[checkpoint] save failed: {e}\n")


# --------------------------------------------------------------------------
# Bulk capture lookup
# --------------------------------------------------------------------------
# Querying CDX once per work means 2 requests x N works -- 734 for a 367-work
# tag, which is enough to get rate-limited into the ground. But CDX supports
# prefix matching, so one query for 'archiveofourown.org/downloads/82' returns
# every archived download whose work ID starts with 82. Grouping the IDs we
# want by shared prefix turns hundreds of requests into a handful, and the
# matching is then done locally.
#
# A second benefit, less obvious but worth more: when a bulk query SUCCEEDS,
# any work ID missing from its results genuinely has nothing archived. That is
# a real zero, not the "we could not find out" zero that a failed per-work
# lookup produces.

WORK_ID_IN_URL = {
    "downloads": re.compile(r"/downloads/(\d+)"),
    "works": re.compile(r"/works/(\d+)"),
}

BULK_LIMIT = 150000       # CDX's own server-side cap
BULK_GROUP_LEN = 2        # leading digits of the work ID to group on
MAX_SUBDIVIDE = 4         # how many times to split a group that fails or truncates
MIN_GROUP_WORKS = 12      # below this, an individual lookup beats a prefix query
TRUNCATE_RETRIES = 1      # splits allowed after a truncation before giving up on bulk

# A prefix query for /works/ returns everything AO3 hangs off a work URL:
# chapters, comments, kudos, bookmarks, collections, share pages. For a 3-digit
# prefix that is ~16,000 captures, almost none of them readable story pages.
# This filter asks CDX to return only the work page itself (with or without a
# query string) and drop the sub-paths, which cuts the response by roughly an
# order of magnitude and lets the groups stay wide.
#
#   matches:  /works/123            /works/123?view_full_work=true
#   rejects:  /works/123/chapters/4 /works/123/comments  /works/123/kudos
#
# Local matching by work ID still runs afterwards, so if a server treats this
# as a substring match rather than a full match the only cost is a larger
# response -- never a wrong result. The one real risk is a filter so strict it
# returns nothing, so the run warns if that happens everywhere.
PAGE_FILTER = r"original:https?://[^/]+/works/[0-9]+/?(\?.*)?"

# With --include-chapters, also keep /works/<id>/chapters/<n>. For a long work
# whose individual chapters were crawled but whose main page was not, these are
# the only readable copy there is. Off by default because chapters are the
# bulkiest category of work sub-URLs.
PAGE_FILTER_CHAPTERS = (
    r"original:https?://[^/]+/works/[0-9]+(/chapters/[0-9]+)?/?(\?.*)?")

_FILTER_STATS = {"rows": 0, "queries": 0}


def group_by_prefix(ids, length):
    groups = {}
    for wid in ids:
        groups.setdefault(wid[:length], []).append(wid)
    return groups


def _collect(kind, prefix, wanted, verbose=False, page_filter=True,
             include_chapters=False):
    """
    One prefix query.

    Returns (found, truncated), or None if the query failed outright.
    'truncated' means the response hit CDX's row cap, so captures are missing
    and the group must be split -- a truncated response looks like a success,
    which would otherwise turn missing data into confident zeros.
    """
    extra = None
    if kind == "works":
        # CDX ANDs multiple filters, which is what we want: HTTP 200 AND a
        # URL shaped like a readable work page.
        extra = {"filter": ["statuscode:200"]}
        if page_filter:
            extra["filter"].append(
                PAGE_FILTER_CHAPTERS if include_chapters else PAGE_FILTER)

    rows = cdx_query(f"archiveofourown.org/{kind}/{prefix}", match_type="prefix",
                     extra=extra, limit=BULK_LIMIT, verbose=verbose)
    if rows is None:
        return None

    if kind == "works" and page_filter:
        _FILTER_STATS["queries"] += 1
        _FILTER_STATS["rows"] += len(rows)

    pattern = WORK_ID_IN_URL[kind]
    found = {}
    for r in rows:
        m = pattern.search(r.get("original", ""))
        if not m:
            continue
        wid = m.group(1)
        if wid in wanted:
            found.setdefault(wid, []).append(r)

    truncated = len(rows) >= BULK_LIMIT
    if verbose:
        sys.stderr.write(f"  [bulk] {kind}/{prefix}* -> {len(rows)} capture(s), "
                         f"{len(found)} of our work(s)"
                         f"{' TRUNCATED' if truncated else ''}\n")
    return found, truncated


def bulk_captures(kind, ids, verbose=False, group_len=BULK_GROUP_LEN,
                  page_filter=True, include_chapters=False, on_group=None):
    """
    Fetch captures for many works in a few prefix queries.

    Returns (found, unresolved):
      found      -- {work_id: [rows]} for every ID whose group was queried OK
      unresolved -- set of IDs whose group failed and needs a per-work lookup
    """
    wanted = set(ids)
    found = {}
    unresolved = set()

    queue = [(p, m, 0) for p, m in
             sorted(group_by_prefix(sorted(ids, key=int), group_len).items())]
    total = len(queue)
    done = 0

    while queue:
        if stopping():
            unresolved.update(w for _, members, _ in queue for w in members)
            break
        prefix, members, depth = queue.pop(0)
        done += 1

        # A prefix query returns every capture in that ID range, not just the
        # works we want. That is a win when our works are clustered -- a recent
        # tag whose IDs sit close together -- and a heavy loss when they are
        # scattered across the archive's whole history, where a group may cover
        # 10,000 possible works to find a dozen of ours. Below a threshold, an
        # individual lookup per work is both cheaper and immune to truncation.
        if len(members) < MIN_GROUP_WORKS:
            unresolved.update(members)
            continue
        # A tag with thousands of works produces thousands of groups. Printing
        # every one fills the console's scrollback, which on Windows can grow
        # until the terminal itself runs out of memory and takes the run with
        # it. Past a certain size, report periodically instead.
        if total <= 40 or done % 25 == 0 or done == total:
            print(f"  [bulk {kind}] {done}/{total} querying {prefix}* "
                  f"({len(members)} work(s))")

        got = _collect(kind, prefix, wanted, verbose, page_filter,
                       include_chapters)
        if got is not None and not got[1]:
            found.update(got[0])
            # Hand partial results to the caller so a long phase can be
            # checkpointed. Without this a multi-hour bulk lookup writes
            # nothing to disk until it finishes, and a crash loses all of it.
            if on_group:
                on_group(found, unresolved)
            continue
        # The query failed or was truncated. A narrower prefix returns less
        # data and is more likely to come back whole, so split the group and
        # retry the pieces -- but only when splitting actually produces more
        # than one group. Narrowing the prefix on a single work just repeats
        # the same query.
        capped = got is not None
        # Splitting a truncated group costs another full-size query per child,
        # and on a widely spread tag the children truncate too. Allow one split
        # after a truncation, then hand the works to individual lookups rather
        # than paying for the same discovery over and over.
        budget = TRUNCATE_RETRIES if capped else MAX_SUBDIVIDE
        subgroups = group_by_prefix(members, len(prefix) + 1) if len(members) > 1 else {}
        if depth < budget and len(subgroups) > 1:
            why = "hit the row cap" if capped else "failed"
            print(f"    {prefix}* {why} - splitting into {len(subgroups)} "
                  f"smaller group(s) and retrying")
            for sp, sm in sorted(subgroups.items()):
                queue.append((sp, sm, depth + 1))
                total += 1
            continue
        if capped and len(members) == 1:
            # One work in a capped group cannot be narrowed any further here;
            # the individual lookup below queries its exact ID, which is the
            # narrowest query there is.
            print(f"    {prefix}* hit the row cap - using an individual lookup")
        unresolved.update(members)

    return found, unresolved


def assemble_from_bulk(wid, dl_rows, pg_rows, failed, include_chapters=True):
    """Build a per-work result from bulk query output."""
    out = {"downloads": [], "pages": [], "status": "failed" if failed else "ok"}
    for r in dl_rows or []:
        ext = r.get("original", "").rsplit(".", 1)[-1].split("?")[0].lower()
        if ext in DOWNLOAD_EXTS or r.get("mimetype", "").startswith("application/"):
            out["downloads"].append(r)
    out["pages"] = [r for r in (pg_rows or [])
                    if is_story_page(r, include_chapters)]
    return out


def captures_for_work(wid, verbose=False, include_chapters=True,
                      skip_downloads=False):
    """
    Everything archived for one work: download files and HTML reading pages.

    Returns a dict with a 'status' of:
      ok      -- both queries answered; counts are trustworthy
      failed  -- at least one query never answered; MUST be retried
      suspect -- queries answered empty, but we were being throttled at the
                 time, so the emptiness may be an artifact. Retried too.
    """
    hits_before = _THROTTLE["hits"]
    out = {"downloads": [], "pages": [], "status": "ok"}

    # Download captures are almost always AO3's error page rather than a file
    # (measured: 487 of 488 on one real page). On a large tag this query is
    # half the total work for almost no yield, so it can be skipped.
    dl = [] if skip_downloads else cdx_query(
        f"archiveofourown.org/downloads/{wid}", match_type="prefix",
        verbose=verbose)
    pg = cdx_query(f"archiveofourown.org/works/{wid}", match_type="prefix",
                   extra={"filter": "statuscode:200"}, verbose=verbose)

    for r in (dl or []):
        # .get(): a malformed CDX row shouldn't crash a 367-work run.
        ext = r.get("original", "").rsplit(".", 1)[-1].split("?")[0].lower()
        if ext in DOWNLOAD_EXTS or r.get("mimetype", "").startswith("application/"):
            out["downloads"].append(r)
    out["pages"] = [r for r in (pg or [])
                    if is_story_page(r, include_chapters)]

    throttled = _THROTTLE["hits"] > hits_before
    if dl is None or pg is None:
        out["status"] = "failed"
    elif throttled and not dl and not pg:
        out["status"] = "suspect"

    if verbose or out["status"] != "ok":
        note = "" if out["status"] == "ok" else f"  [{out['status'].upper()}]"
        sys.stderr.write(f"[work {wid}] {len(out['downloads'])} download(s), "
                         f"{len(out['pages'])} page(s){note}\n")
    return out


def needs_retry(entry):
    return entry.get("status", "ok") in ("failed", "suspect")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

WORKS_HEADER = [
    "source", "work_id", "title", "author", "summary", "ao3_url", "fandoms",
    "rating", "warnings", "categories", "relationships", "characters",
    "freeform_tags", "words", "chapters", "updated",
    "archived_downloads", "stub_downloads", "archived_pages",
    "download_bytes", "download_size", "full_work_bytes",
    "read_url", "coverage", "chapters_archived",
    "best_download_url", "best_full_work_url", "other_page_urls",
    "status", "metadata_source",
]

CAPTURES_HEADER = [
    "source", "work_id", "title", "author", "ao3_url", "kind", "looks_real",
    "timestamp", "mimetype", "bytes", "original_url", "wayback_url",
]


# Characters legal in a URL that must not be escaped. '%' is deliberately NOT
# here: see wayback_inner() below.
URL_SAFE = "%:/?#[]@!$&'()*+,;=~"

# Safe set for the single-encode pass. '%' and '*' are excluded so they become
# %25 and %2A; parentheses stay literal, which is what Wayback accepts.
_ONCE_SAFE = ":/?#[]@!$&'(),;=~"


def wayback_inner(original):
    """
    Encode a captured URL for Wayback's replay endpoint.

    Wayback decodes the inner URL once before looking it up, so the escapes have
    to survive that pass -- meaning they must be escaped twice. A single-encoded
    space arrives at their nginx as a bare space and is rejected with
    "400 Bad request / Your browser sent an invalid request" before any lookup
    happens. Since essentially every AO3 tag contains a space, this breaks every
    tag listing while leaving numeric /works/<id> URLs working, which is exactly
    the behaviour observed.

    Verified against web.archive.org:
        .../tags/A%20B/works      -> 400   (single-encoded: rejected)
        .../tags/The%2520Convict... -> 200 (double-encoded: served)

    Normalising through unquote() first means this produces the same result
    whether CDX handed back the raw form or an already-escaped one.
    """
    plain = urllib.parse.unquote(original)
    once = urllib.parse.quote(plain, safe=_ONCE_SAFE)
    return once.replace("%", "%25")


def wb_link(ts, original, raw=True):
    """Build a Wayback replay URL in the encoding their endpoint accepts."""
    return f"{WB}/{ts}{'id_' if raw else ''}/{wayback_inner(original)}"


def ao3_link(wid):
    return f"{AO3}/works/{wid}"


# A download URL being archived does not mean the FILE was archived. Crawlers
# follow AO3's /downloads/ links and get the HTML error or login page back, and
# Wayback stores that under the .epub URL. The result looks like a hit -- real
# AO3 filename and all -- but is a few hundred bytes of HTML.
#
# Measured over one real tag: 487 of 488 download captures were under 5 KB with
# mimetype text/html, median 640 bytes. A genuine EPUB of a full-length work is
# six figures. So size and mimetype, not the URL, decide what counts.
EBOOK_MIMETYPES = ("application/epub+zip", "application/pdf",
                   "application/x-mobipocket-ebook", "application/vnd.amazon.ebook",
                   "application/octet-stream")
STUB_MAX_BYTES = 5120


def size_of(row):
    """
    Capture size in bytes, or '' when CDX reported nothing usable.

    CDX occasionally returns a nonsense length (negative, or absurdly large),
    so anything implausible is treated as unknown rather than passed through
    into the spreadsheet.
    """
    try:
        v = int(row.get("length", "")) if row else ""
    except (TypeError, ValueError):
        return ""
    if v == "" or not isinstance(v, int):
        return ""
    return v if 0 <= v < 2_000_000_000 else ""


# AO3 hangs a lot off a work URL that is not the story: the hit counter
# (/works/123/hit_count.json), comments, kudos, bookmarks, collections, the
# chapter index, and the edit/delete endpoints. The CDX server applies the
# page filter as a PARTIAL match, so those come back regardless of the regex
# sent with the query -- the filter saves bandwidth, it does not guarantee
# shape. This whitelist is the real gate, applied locally to every row.
#
# Allowed:  /works/123        /works/123?view_full_work=true
#           /works/123/chapters/456    (only with --include-chapters)
# A trailing #fragment is kept: /works/123#main is a capture of the work page,
# just with an anchor, and for some works it is the only capture there is. The
# path still has to be a story path, so /works/123/bookmarks#main is rejected.
STORY_PAGE_RE = re.compile(
    r"^https?://[^/]+/works/\d+(?:/chapters/\d+)?/?(?:\?[^#]*)?(?:#.*)?$", re.I)


# A capture whose URL carries a Cloudflare challenge token is the interstitial
# "checking your browser" page, not the story. Wayback stores it under the work
# URL like any other response.
CHALLENGE_MARKERS = ("__cf_chl", "cf_chl_jschl", "__cf_waf")


def is_story_page(row, include_chapters=True):
    """True when a /works/ capture is readable story content."""
    orig = row.get("original", "")
    if not STORY_PAGE_RE.match(orig):
        return False
    if any(m in orig for m in CHALLENGE_MARKERS):
        return False
    if not include_chapters and "/chapters/" in orig:
        return False
    return True


def coverage_of(data):
    """
    How much of the work the best archived copy actually holds.

    A ?view_full_work capture is the entire story. Anything else is one page:
    for a multi-chapter work that is a single chapter, which is very different
    from having the work, and the difference is invisible unless it is stated.
    """
    if not data["pages"] and not any(
            is_real_download(r) for r in data["downloads"]):
        return ""
    if strict_full_work(data["pages"]):
        return "complete"
    if any(is_real_download(r) for r in data["downloads"]):
        return "complete"
    return "partial"


def chapters_archived(data):
    """Distinct chapter captures, so a partial copy's extent is visible."""
    seen = {r.get("original", "").split("?")[0].split("#")[0]
            for r in data["pages"] if "/chapters/" in r.get("original", "")}
    return len(seen)


def is_real_download(row):
    """
    True when a /downloads/ capture plausibly holds the actual file.

    An ebook mimetype is taken at face value. Otherwise the capture has to be
    bigger than an error page -- an HTML response of a few hundred bytes at a
    .epub URL is AO3's error page, not a book.
    """
    mt = (row.get("mimetype") or "").lower()
    if any(mt.startswith(m) for m in EBOOK_MIMETYPES):
        return True
    size = size_of(row)
    if size == "":
        return False
    return size > STUB_MAX_BYTES


def human_size(n):
    if not isinstance(n, int):
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def best(rows, prefer_substr=None):
    """Newest capture, optionally preferring URLs containing a substring."""
    if not rows:
        return None
    pool = [r for r in rows if prefer_substr and prefer_substr in r["original"]] or rows
    return sorted(pool, key=lambda r: r["timestamp"])[-1]


def strict_full_work(rows):
    """Newest true ?view_full_work capture, or None. No falling back."""
    pool = [r for r in rows or [] if "view_full_work" in r.get("original", "")]
    return sorted(pool, key=lambda r: r["timestamp"])[-1] if pool else None


def page_links(rows, limit=4, skip=None):
    """
    Up to `limit` distinct archived page links, newest first.

    Deduplicated by the underlying AO3 URL so repeated crawls of the same page
    do not crowd out a chapter or a full-work view that is actually different.
    """
    out, seen = [], set()
    for r in sorted(rows or [], key=lambda r: r["timestamp"], reverse=True):
        orig = r.get("original", "")
        # Dedupe on the page itself: /works/1, /works/1?x=y and /works/1#main
        # are all the same page, so only the newest of them is worth listing.
        key = orig.split("?")[0].split("#")[0]
        if key in seen or (skip and orig == skip.get("original")):
            continue
        seen.add(key)
        out.append(wb_link(r["timestamp"], orig))
        if len(out) >= limit:
            break
    return out


def pick_read_url(data):
    """
    The single link worth clicking for this work, in order of usefulness:
    the whole story on one page, then any archived work page, then the
    download file if that is all there is.
    """
    full = strict_full_work(data["pages"])
    if full:
        return wb_link(full["timestamp"], full["original"]), "full work"
    page = best(data["pages"])
    if page:
        return wb_link(page["timestamp"], page["original"]), "page"
    dl = best([r for r in data["downloads"] if is_real_download(r)])
    if dl:
        return wb_link(dl["timestamp"], dl["original"]), "download"
    return "", ""


def all_work_ids(results, meta):
    """
    Every work we know about, whether or not its capture lookup has run.

    The listing scrape yields full metadata for the whole tag long before the
    per-work lookups finish, so reporting only on `results` would throw most of
    a tag away -- and that metadata is the part that already succeeded.
    """
    return sorted(set(results) | set(meta), key=int)


NOT_QUERIED = {"downloads": [], "pages": [], "status": "not queried"}


def has_anything_archived(data):
    """
    True when this work has something to show: a story page, or a real
    download file. A work with only stub downloads has nothing readable.
    """
    return bool(data["pages"]) or any(
        is_real_download(r) for r in data["downloads"])


def work_rows(label, results, meta, include_unarchived=False):
    """
    One row per work.

    By default only works with an archived copy are written, since a row whose
    every link column is blank is noise when you are looking for something to
    read. Works whose lookup has not run or did not land are always kept -
    their blank columns mean "unknown", not "nothing", and dropping them would
    hide work still to do. --include-unarchived writes the full catalogue,
    which stays useful as a reading list for when AO3 returns.
    """
    for wid in all_work_ids(results, meta):
        data = results.get(wid, NOT_QUERIED)
        m = meta.get(wid, blank_meta())
        if (not include_unarchived
                and data.get("status") == "ok"
                and not has_anything_archived(data)):
            continue
        real_dls = [r for r in data["downloads"] if is_real_download(r)]
        stub_dls = len(data["downloads"]) - len(real_dls)
        bd = best(real_dls)
        bf = strict_full_work(data["pages"])
        read, _kind = pick_read_url(data)
        others = page_links(data["pages"], limit=8, skip=bf)
        yield [
            label, wid, m["title"], m["author"], m["summary"], ao3_link(wid),
            m["fandoms"], m["rating"], m["warnings"], m["categories"],
            m["relationships"], m["characters"], m["freeform_tags"],
            m["words"], m["chapters"], m["updated"],
            len(real_dls), stub_dls, len(data["pages"]),
            size_of(bd), human_size(size_of(bd)), size_of(bf),
            read, coverage_of(data), chapters_archived(data) or "",
            wb_link(bd["timestamp"], bd["original"]) if bd else "",
            wb_link(bf["timestamp"], bf["original"]) if bf else "",
            " | ".join(others),
            data.get("status", "ok"),
            m["meta_source"],
        ]


def capture_rows(label, results, meta):
    for wid, data in sorted(results.items(), key=lambda kv: int(kv[0])):
        m = meta.get(wid, blank_meta())
        for kind in ("downloads", "pages"):
            for r in data[kind]:
                real = ("yes" if is_real_download(r) else "stub") \
                    if kind == "downloads" else ""
                yield [label, wid, m["title"], m["author"], ao3_link(wid),
                       kind[:-1], real, r["timestamp"], r.get("mimetype", ""),
                       size_of(r), r["original"],
                       wb_link(r["timestamp"], r["original"])]


def write_csv(path, header, rows):
    """
    Write a CSV, falling back to a numbered filename if the target is locked.

    Having the spreadsheet open in Excel or LibreOffice locks it on Windows,
    and an hours-long run should not end in a traceback because of that. The
    data is already checkpointed either way, but writing it somewhere is far
    friendlier than refusing to.
    """
    # utf-8-sig so Excel opens non-ASCII titles correctly on a double-click.
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        return path
    except PermissionError:
        pass

    base, ext = os.path.splitext(path)
    for n in range(1, 100):
        alt = f"{base}_{n}{ext}"
        if os.path.exists(alt):
            continue
        try:
            with open(alt, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(rows)
            print(f"  NOTE: {os.path.basename(path)} is open in another program, "
                  f"so this run was written to {os.path.basename(alt)} instead.")
            return alt
        except PermissionError:
            continue

    sys.stderr.write(f"  Could not write {path} or any fallback name. "
                     f"Close the file and rerun with --resume.\n")
    return None


def write_markdown(path, source, results, meta):
    try:
        return _write_markdown(path, source, results, meta)
    except PermissionError:
        base, ext = os.path.splitext(path)
        for n in range(1, 100):
            alt = f"{base}_{n}{ext}"
            if os.path.exists(alt):
                continue
            try:
                _write_markdown(alt, source, results, meta)
                print(f"  NOTE: {os.path.basename(path)} was locked, wrote "
                      f"{os.path.basename(alt)} instead.")
                return alt
            except PermissionError:
                continue
        sys.stderr.write(f"  Could not write {path}.\n")
        return None


def _write_markdown(path, source, results, meta):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Wayback captures: {source.label}\n\n")
        with_dl = [w for w, d in results.items()
                   if any(is_real_download(r) for r in d["downloads"])]
        every = all_work_ids(results, meta)
        pending_n = len(every) - len(results)
        f.write(f"- Source: `{source.kind}` -- `{source.path}`\n")
        f.write(f"- Works found: **{len(every)}**"
                + (f" ({pending_n} not yet looked up)" if pending_n else "")
                + "\n")
        f.write(f"- Works with an archived download file: **{len(with_dl)}**\n\n")
        f.write("Every link uses Wayback's `id_` modifier, which serves the original "
                "bytes without the Wayback toolbar, so EPUB/PDF files download intact.\n\n")

        for wid in all_work_ids(results, meta):
            data = results.get(wid, NOT_QUERIED)
            m = meta.get(wid, blank_meta())
            f.write(f"## {m['title'] or f'Work {wid}'}\n\n")
            if m["author"]:
                f.write(f"**by {m['author']}**")
                if m["words"]:
                    f.write(f" -- {m['words']} words, {m['chapters']} ch.")
                f.write("\n\n")
            if m["rating"] or m["warnings"]:
                bits = [b for b in (m["rating"], m["categories"]) if b]
                if bits:
                    f.write(f"`{'` · `'.join(bits)}`\n\n")
                if m["warnings"]:
                    f.write(f"**Warnings:** {m['warnings']}\n\n")
            if m["summary"]:
                f.write(f"> {m['summary']}\n\n")
            for lbl, key in (("Relationships", "relationships"),
                             ("Characters", "characters"),
                             ("Tags", "freeform_tags")):
                if m[key]:
                    f.write(f"**{lbl}:** {m[key]}\n\n")
            f.write(f"[AO3 original]({ao3_link(wid)})\n\n")

            real_dls = [r for r in data["downloads"] if is_real_download(r)]
            if real_dls:
                f.write("**Download files:**\n\n")
                for r in real_dls:
                    f.write(f"- [{r['original'].rsplit('/', 1)[-1]}]"
                            f"({wb_link(r['timestamp'], r['original'])}) "
                            f"-- {r['timestamp']}, {r.get('length', '?')} bytes\n")
                f.write("\n")
            else:
                f.write("_No archived download file._\n\n")

            read, kind = pick_read_url(data)
            if read:
                cov = coverage_of(data)
                note = "" if cov == "complete" else " - this is one page only"
                f.write(f"**Read it:** [{kind}]({read}){note}\n\n")
            extra = page_links(data["pages"], limit=8,
                               skip=strict_full_work(data["pages"]))
            if extra:
                f.write("**Other archived pages:** "
                        + " / ".join(f"[{i+1}]({u})" for i, u in enumerate(extra))
                        + "\n\n")


# --------------------------------------------------------------------------
# Per-source run
# --------------------------------------------------------------------------

def survey(source, outdir, skip_meta=False, verbose=False, resume=False,
           deep=False, bulk=True, page_filter=True, save_listing=None,
           include_chapters=False, project=DEFAULT_PROJECT,
           include_unarchived=False, skip_downloads=False):
    """Run the full pipeline for one source. Returns (results, meta)."""
    print(f"\n=== {source.label} ({source.kind}) ===")
    print(f"Path: {source.path}")

    done_results, done_meta, done_caps = (
        load_progress(outdir, project, verbose) if resume else ({}, {}, set()))
    if done_results:
        print(f"Resuming: {len(done_results)} work(s) already recorded.")

    meta = dict(done_meta)
    caps, cap_status = find_listing_captures(source, verbose)
    if not caps:
        if cap_status == "failed":
            print("\nCould not reach the Wayback index to check this page.")
            print("  This is not the same as the page being unarchived - we")
            print("  simply could not find out. The Internet Archive is likely")
            print("  rate-limiting; try again in a few hours.")
            return {}, {}

        print(f"\nThe Wayback Machine has no archived copy of:")
        print(f"  {AO3}/{source.path}")
        ctx = archive_context(source, verbose)
        if ctx:
            parent, n, examples = ctx
            print(f"\n  It does have {n} capture(s) under {AO3}/{parent}, "
                  f"including:")
            for u in examples:
                print(f"    {u}")
            print("  So the archive knows this account or tag - just not this")
            print("  particular page. One of the above may be worth running.")
        else:
            print("\n  Nothing under that path is archived either.")
        if source.kind == "tag" and any(c in source.label for c in TAG_ESCAPES):
            print("\n  This tag also contains a character AO3 escapes specially.")
            print("  If you believe it was archived, pass the URL copied")
            print("  straight from AO3 or the Wayback Machine with --tag-url.")
        return {}, {}

    print(f"Found {len(caps)} archived listing capture(s). Scraping...")

    # Carried forward from the checkpoint. Defined before the listing scrape so
    # that phase can checkpoint too; the pending list is worked out below once
    # every work ID is known.
    results = dict(done_results)

    # Newest first. Recent captures are the most complete and the most likely to
    # replay cleanly, so this puts the useful data in hand early -- and keeps a
    # run of broken old captures from looking like total failure before the good
    # ones are ever reached. Because the newest capture writes each field first,
    # "don't overwrite what's already set" means newest still wins.
    ok = bad = 0
    scraped = set(done_caps)
    todo = [r for r in sorted(caps, key=lambda r: r["timestamp"], reverse=True)
            if r["timestamp"] not in scraped]
    if len(todo) < len(caps):
        print(f"  {len(caps) - len(todo)} capture(s) already read last time; "
              f"{len(todo)} to go.")
    for r in todo:
        if stopping():
            print("  [stop] halting listing scrape early.")
            break
        found = scrape_listing(r["timestamp"], r["original"], verbose, deep=deep,
                               save_dir=save_listing)
        scraped.add(r["timestamp"])
        if found:
            ok += 1
        else:
            bad += 1
        for wid, m in found.items():
            slot = meta.setdefault(wid, blank_meta())
            for k, v in m.items():
                if v and not slot.get(k):
                    slot[k] = v
        # A popular tag can have thousands of listing captures and take hours
        # here. Checkpoint as we go so a crash costs minutes, not the run.
        if (ok + bad) % 20 == 0:
            save_progress(outdir, project, results, meta, scraped)
            print(f"  ...{ok + bad}/{len(todo)} capture(s) read, "
                  f"{len(meta)} work(s) found so far")

    if bad:
        print(f"  {ok} capture(s) read, {bad} unavailable on Wayback "
              f"(their work IDs may still appear via the others).")

    ids = set(meta)
    if not ids:
        print("Captures existed but no work IDs could be parsed.")
        return {}, {}

    # Anything previously recorded as failed/suspect is re-queued, not skipped.
    pending = [w for w in sorted(ids, key=int)
               if w not in results or needs_retry(results[w])]
    redo = sum(1 for w in pending if w in results)
    print(f"{len(ids)} unique work ID(s); {len(pending)} still to query"
          + (f" ({redo} being retried from the last run)." if redo else "."))

    stopped_early = False

    # --- bulk phase -------------------------------------------------------
    if bulk and pending:
        print(f"\n  Bulk lookup: grouping {len(pending)} work(s) into prefix "
              f"queries instead of {len(pending) * 2} individual ones.")
        # Write partial results after every prefix group. A bulk lookup over
        # a large tag runs for hours; without this nothing reaches disk until
        # the whole phase completes.
        def checkpoint_bulk(found, unresolved, _kind=None):
            partial = dict(results)
            for wid in pending:
                if wid in found or wid in unresolved:
                    partial.setdefault(wid, {"downloads": [], "pages": [],
                                             "status": "suspect"})
            save_progress(outdir, project, partial, meta, scraped)

        if skip_downloads:
            print("  Skipping download lookups (--skip-downloads).")
            dl_found, dl_bad = {}, set()
        else:
            dl_found, dl_bad = bulk_captures("downloads", pending, verbose,
                                             on_group=checkpoint_bulk)
        pg_found, pg_bad = bulk_captures("works", pending, verbose,
                                         page_filter=page_filter,
                                         include_chapters=include_chapters,
                                         on_group=checkpoint_bulk) \
            if not stopping() else ({}, set(pending))

        resolved = 0
        for wid in pending:
            failed = wid in dl_bad or wid in pg_bad
            results[wid] = assemble_from_bulk(
                wid, dl_found.get(wid), pg_found.get(wid), failed,
                include_chapters)
            if not failed:
                resolved += 1
        save_progress(outdir, project, results, meta, scraped)

        # If the page filter matched nothing anywhere, this server probably
        # does not accept the regex. Say so plainly rather than letting the
        # run report a tag full of confident zeros.
        if (page_filter and _FILTER_STATS["queries"] >= 3
                and _FILTER_STATS["rows"] == 0):
            print("\n  WARNING: the work-page filter matched zero captures in "
                  f"{_FILTER_STATS['queries']} queries.")
            print("  This server may not support it. The page counts below are "
                  "probably wrong.")
            print("  Rerun with --no-page-filter --resume to check.\n")

        still = [w for w in pending if needs_retry(results[w])]
        print(f"  Bulk lookup resolved {resolved}/{len(pending)} work(s).")
        if still:
            print(f"  {len(still)} work(s) need an individual lookup.")
        pending = still

        # Fill in metadata for anything the listings missed.
        if not skip_meta:
            for wid in sorted(results, key=int):
                if stopping():
                    break
                if not meta.get(wid, {}).get("title") and results[wid]["pages"]:
                    meta[wid] = fetch_work_meta(wid, results[wid]["pages"], verbose)
            save_progress(outdir, project, results, meta, scraped)

    # --- per-work phase (fallback, or the whole job with --per-work) ------
    consecutive_failures = 0
    for n, wid in enumerate(pending, 1):
        m = meta.get(wid, blank_meta())
        label = f" -- {m['title']}" if m.get("title") else ""
        extra = f"  (+{_THROTTLE['extra']:.0f}s)" if _THROTTLE["extra"] else ""
        print(f"  [{n}/{len(pending)}] work {wid}{label}{extra}")
        results[wid] = captures_for_work(wid, verbose, include_chapters,
                                         skip_downloads)
        if not skip_meta and not m.get("title"):
            meta[wid] = fetch_work_meta(wid, results[wid]["pages"], verbose)
        if n % 5 == 0:  # checkpoint regularly so a crash costs ~5 works
            save_progress(outdir, project, results, meta, scraped)

        # If nothing is getting through, stop. Grinding on against a rate
        # limiter wastes hours, produces a spreadsheet full of unusable zeros,
        # and only deepens the block. Everything so far is checkpointed, so
        # coming back later with --resume costs nothing.
        consecutive_failures = 0 if not needs_retry(results[wid]) else consecutive_failures + 1
        if consecutive_failures >= GIVE_UP_AFTER:
            print(f"\n  {consecutive_failures} work(s) failed in a row - the "
                  f"Internet Archive is refusing requests.")
            print("  Stopping here. Everything collected is saved; come back in "
                  "a few hours and rerun with --resume.")
            stopped_early = True
            break

        if stopping():
            remaining = len(pending) - n
            print(f"  [stop] stopped after {n} work(s); {remaining} left to do.")
            stopped_early = True
            break

    save_progress(outdir, project, results, meta, scraped)

    # --- retry sweeps -----------------------------------------------------
    # Works whose queries failed, or came back empty while we were throttled,
    # get another chance at a slower pace. This is where the "0 downloads,
    # 0 pages" rows from a throttled run actually get resolved.
    global SLEEP
    base_sleep = SLEEP
    for sweep in range(1, RETRY_PASSES + 1):
        if stopped_early or stopping():
            break
        unresolved = [w for w in sorted(results, key=int) if needs_retry(results[w])]
        if not unresolved:
            break
        SLEEP = base_sleep * (2 ** sweep)
        print(f"\n  Retry pass {sweep}/{RETRY_PASSES}: {len(unresolved)} unresolved "
              f"work(s), slowing to {SLEEP:.0f}s between requests...")
        _THROTTLE["extra"] = 0.0
        for n, wid in enumerate(unresolved, 1):
            print(f"    [{n}/{len(unresolved)}] retrying work {wid}")
            fresh = captures_for_work(wid, verbose, include_chapters,
                                      skip_downloads)
            # Only overwrite if this attempt went better than the last one.
            if not needs_retry(fresh) or fresh["downloads"] or fresh["pages"]:
                results[wid] = fresh
                if not skip_meta and not meta.get(wid, {}).get("title"):
                    meta[wid] = fetch_work_meta(wid, fresh["pages"], verbose)
            if n % 5 == 0:
                save_progress(outdir, project, results, meta, scraped)
            if stopping():
                print("    [stop] halting retry sweep.")
                stopped_early = True
                break
        save_progress(outdir, project, results, meta, scraped)
    SLEEP = base_sleep

    still_bad = [w for w in results if needs_retry(results[w])]
    if still_bad:
        print(f"\n  {len(still_bad)} work(s) still unresolved after retries; "
              f"marked in the 'status' column. Rerun with --resume to try again.")

    if stopped_early:
        print("  Writing spreadsheets with what has been collected so far...")
    os.makedirs(outdir, exist_ok=True)
    write_csv(os.path.join(outdir, out_name(project, "works.csv")), WORKS_HEADER,
              work_rows(source.label, results, meta, include_unarchived))
    write_csv(os.path.join(outdir, out_name(project, "captures.csv")), CAPTURES_HEADER,
              capture_rows(source.label, results, meta))
    write_markdown(os.path.join(outdir, out_name(project, "report.md")),
                   source, results, meta)

    archived = sum(1 for d in results.values() if has_anything_archived(d))
    hidden = len(results) - archived
    if hidden and not include_unarchived:
        print(f"  {hidden} work(s) have nothing archived and were left out of "
              f"the spreadsheet (--include-unarchived keeps them).")
    dl = sum(1 for d in results.values()
             for r in d["downloads"] if is_real_download(r))
    stubs = sum(len(d["downloads"]) for d in results.values()) - dl
    print(f"  -> {len(results)} work(s), {dl} real download file(s)"
          + (f", {stubs} stub(s) ignored" if stubs else ""))
    return results, meta


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def resume_command():
    """Reproduce this invocation with --resume appended, quoted for the shell."""
    parts = [os.path.basename(sys.executable) or "python",
             os.path.basename(sys.argv[0])]
    for a in sys.argv[1:]:
        if a == "--clean":
            continue          # --clean and --resume are mutually exclusive
        parts.append(f'"{a}"' if (" " in a or "|" in a) else a)
    if "--resume" not in sys.argv[1:]:
        parts.append("--resume")
    return " ".join(parts)


def probe(url):
    """
    Fetch one URL and report exactly what came back: status, final URL after any
    redirect, key headers and the start of the body. Use this to find out what
    Wayback actually objects to instead of inferring it from a status code.
    """
    print(f"Probing: {url}\n")
    hdrs = request_headers()
    print(f"  sending     : {', '.join(f'{k}: {v[:40]}' for k, v in hdrs.items())}\n")
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with _OPENER.open(req, timeout=60) as r:
            body = r.read(1200)
            print(f"  status      : {r.status}")
            print(f"  final URL   : {r.geturl()}")
            for h in ("Content-Type", "Content-Length", "X-Archive-Src",
                      "Location", "Server"):
                if r.headers.get(h):
                    print(f"  {h:<12}: {r.headers.get(h)}")
            text_body = body.decode("utf-8", "replace")
            print(f"  body starts : {text_body[:400]!r}")
            print(f"\n  Looks like a usable capture: "
                  f"{'yes' if b'work' in body or r.status == 200 else 'unclear'}")
    except urllib.error.HTTPError as e:
        print(f"  status      : {e.code} {e.reason}")
        print(f"  final URL   : {e.geturl()}")
        for h in ("Content-Type", "Location", "Server"):
            if e.headers and e.headers.get(h):
                print(f"  {h:<12}: {e.headers.get(h)}")
        raw = e.read(1200).decode("utf-8", "replace")
        print(f"  raw body    : {raw[:500]!r}")
        stripped = WS_RE.sub(" ", TAG_RE.sub(" ", raw)).strip()
        print(f"  body text   : {stripped[:400]}")
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")
    return 0


def build_sources(args):
    sources = []
    for url in args.tag_url or []:
        sources.append(source_from_url(url, args.listing))
    for name in args.tag or []:
        sources.append(source_from_name(name, "tag", args.listing))
    for name in args.collection or []:
        sources.append(source_from_name(name, "collection", args.listing))
    for name in args.user or []:
        sources.append(source_from_name(name, "user", args.listing))
    for name in args.pseud or []:
        owner = (args.user or [None])[0]
        sources.append(source_from_name(name, "pseud", args.listing, owner=owner))

    if args.tags_file:
        with open(args.tags_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("http"):
                    sources.append(source_from_url(line, args.listing))
                else:
                    sources.append(source_from_name(line, "tag", args.listing))
    return sources


def main():
    global SLEEP, UA

    ap = argparse.ArgumentParser(
        prog="ao3_wayback.py",
        description="Survey Wayback Machine captures for AO3 tags, collections or users.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # By URL -- most reliable, no tag-encoding guesswork
  %(prog)s --tag-url "https://archiveofourown.org/tags/Some%%20Tag/works"

  # By name -- several at once, any tag type (fandom, relationship, character,
  # additional tag, archive warning, category, rating)
  %(prog)s --tag "Steve Rogers/Bucky Barnes" --tag "Hurt/Comfort" --tag "Mass Effect"

  # Batch from a file, one tag or URL per line, '#' for comments
  %(prog)s --tags-file tags.txt --out ./results

  # Other listing containers
  %(prog)s --collection "Yuletide2025"
  %(prog)s --user "someauthor" --listing works
  %(prog)s --tag "Some Tag" --listing bookmarks

  # Known work IDs, skip discovery entirely
  %(prog)s --work-ids 10726146,1160745
""")

    src = ap.add_argument_group("sources (repeatable, combinable)")
    src.add_argument("--tag", action="append", metavar="NAME",
                     help="AO3 tag by name; special characters are encoded for you")
    src.add_argument("--tag-url", action="append", metavar="URL",
                     help="AO3 or web.archive.org URL; encoding preserved as-is")
    src.add_argument("--tags-file", metavar="FILE",
                     help="File of tag names and/or URLs, one per line")
    src.add_argument("--collection", action="append", metavar="NAME",
                     help="AO3 collection name")
    src.add_argument("--user", action="append", metavar="NAME",
                     help="AO3 username")
    src.add_argument("--pseud", action="append", metavar="NAME",
                     help="AO3 pseud (requires --user for the owning account)")
    src.add_argument("--work-ids", metavar="IDS",
                     help="Comma-separated work IDs; skips listing discovery")
    src.add_argument("--probe", metavar="URL",
                     help="Diagnostic: fetch one URL and dump the status, final "
                          "redirect target, headers and body. Nothing else runs")

    opt = ap.add_argument_group("options")
    opt.add_argument("--project", metavar="NAME",
                     help="Name for this project's output files, giving "
                          "NAME_works.csv and NAME_captures.csv. Prompted for "
                          "if omitted and someone is at the terminal")
    opt.add_argument("--listing", choices=LISTINGS, default="works",
                     help="Which listing to read (default: works)")
    opt.add_argument("--out", default="./ao3_wayback_out", metavar="DIR",
                     help="Output directory (default: ./ao3_wayback_out)")
    opt.add_argument("--sleep", type=float, default=DEFAULT_SLEEP, metavar="SEC",
                     help=f"Delay between requests (default: {DEFAULT_SLEEP})")
    opt.add_argument("--resume", action="store_true",
                     help="Continue an interrupted run from its checkpoint")
    opt.add_argument("--skip-downloads", action="store_true",
                     help="Do not look for archived download files. Halves the "
                          "work on a large tag; those captures are almost "
                          "always AO3 error pages rather than real files")
    opt.add_argument("--include-unarchived", action="store_true",
                     help="Also write works with nothing archived. Off by "
                          "default; their metadata is still a usable reading "
                          "list for when AO3 returns")
    opt.add_argument("--include-chapters", action="store_true",
                     help="Also collect archived chapter pages. Useful for long "
                          "works whose chapters were crawled but whose main "
                          "page was not; makes the lookup larger")
    opt.add_argument("--save-listing", metavar="DIR",
                     help="Diagnostic: save each archived listing page to DIR "
                          "exactly as the parser receives it")
    opt.add_argument("--no-page-filter", action="store_true",
                     help="Ask CDX for every /works/ capture instead of just "
                          "readable work pages. Slower and much larger; use if "
                          "the filtered lookup returns nothing")
    opt.add_argument("--per-work", action="store_true",
                     help="Query CDX once per work instead of in bulk. Much "
                          "slower; use only if bulk lookup misbehaves")
    opt.add_argument("--deep-replay", action="store_true",
                     help="Try every replay-URL spelling on a capture that will "
                          "not load (slower; most such captures are simply "
                          "broken on Wayback's side)")
    opt.add_argument("--headers", choices=("minimal", "browser"), default="minimal",
                     help="Request header set. 'minimal' (default) is what "
                          "works; 'browser' adds Accept headers if Wayback ever "
                          "starts refusing plain clients")
    opt.add_argument("--user-agent", metavar="STRING",
                     help="Override the User-Agent. Use a browser's string if "
                          "web.archive.org refuses the default with 400/403")
    opt.add_argument("--clean", action="store_true",
                     help="Delete the previous run's checkpoint, spreadsheets "
                          "and reports before starting. Cannot be combined "
                          "with --resume")
    opt.add_argument("--skip-meta", action="store_true",
                     help="Don't fetch work pages to fill in missing metadata")
    opt.add_argument("--verbose", action="store_true")
    opt.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = ap.parse_args()
    SLEEP = max(0.0, args.sleep)
    HEADER_STYLE["mode"] = args.headers
    if args.user_agent:
        UA = args.user_agent
        print(f"Using custom User-Agent: {UA[:70]}")
    install_stop_handler()

    if args.probe:
        return probe(args.probe)

    if args.clean and args.resume:
        ap.error("--clean and --resume are opposites: one discards the previous "
                 "run, the other continues it. Pick one.")

    # Sources are built before anything touches disk, so the project name can
    # default to the tag being surveyed and --clean knows which files are ours.
    sources = []
    if not args.work_ids:
        try:
            sources = build_sources(args)
        except (ValueError, OSError) as e:
            ap.error(str(e))
        if not sources:
            ap.error("no sources given -- use --tag, --tag-url, --tags-file, "
                     "--collection, --user or --work-ids (see --help)")

    suggested = slugify(sources[0].label) if sources else DEFAULT_PROJECT
    project = slugify(args.project) if args.project else ask_project(suggested)
    project = unique_project(args.out, project, args.resume)
    log_path = start_run_log(args.out, project, args.verbose)
    print(f"Project: {project}  ->  {project}_works.csv, {project}_captures.csv")
    if log_path:
        print(f"Full detail is being written to {log_path}")
        if not args.verbose:
            print("  (watch it live in another window, or add --verbose to see "
                  "it here too)")

    if args.clean:
        try:
            n = clean_run(args.out, project, args.verbose)
        except ValueError as e:
            ap.error(str(e))
        print(f"Clean start: removed {n} file(s) from {os.path.abspath(args.out)}"
              if n else
              f"Clean start: nothing to remove in {os.path.abspath(args.out)}")

    # --- work-ids mode: no listing discovery at all
    if args.work_ids:
        ids = {i.strip() for i in args.work_ids.split(",") if i.strip()}
        if not ids:
            ap.error("--work-ids was empty")
        done_results, done_meta, _caps = (
            load_progress(args.out, project, args.verbose)
            if args.resume else ({}, {}, set()))
        results, meta = dict(done_results), dict(done_meta)
        pending = [w for w in sorted(ids, key=int)
                   if w not in results or needs_retry(results[w])]
        print(f"{len(ids)} work ID(s) supplied; {len(pending)} still to query...")
        for n, wid in enumerate(pending, 1):
            extra = f"  (+{_THROTTLE['extra']:.0f}s)" if _THROTTLE["extra"] else ""
            print(f"  [{n}/{len(pending)}] work {wid}{extra}")
            results[wid] = captures_for_work(wid, args.verbose)
            meta[wid] = (blank_meta() if args.skip_meta
                         else fetch_work_meta(wid, results[wid]["pages"], args.verbose))
            if n % 5 == 0:
                save_progress(args.out, project, results, meta)
            if stopping():
                print(f"  [stop] stopped after {n}; {len(pending) - n} left.")
                break
        unresolved = [w for w in results if needs_retry(results[w])]
        if unresolved and not stopping():
            print(f"  Retrying {len(unresolved)} unresolved work(s) more slowly...")
            SLEEP = SLEEP * 2
            for wid in sorted(unresolved, key=int):
                fresh = captures_for_work(wid, args.verbose)
                if not needs_retry(fresh) or fresh["downloads"] or fresh["pages"]:
                    results[wid] = fresh
                if stopping():
                    break
        save_progress(args.out, project, results, meta)
        os.makedirs(args.out, exist_ok=True)
        write_csv(os.path.join(args.out, out_name(project, "works.csv")), WORKS_HEADER,
                  work_rows("(work-ids)", results, meta, args.include_unarchived))
        write_csv(os.path.join(args.out, out_name(project, "captures.csv")), CAPTURES_HEADER,
                  capture_rows("(work-ids)", results, meta))
        write_markdown(os.path.join(args.out, out_name(project, "report.md")),
                       Source("(work-ids)", "(work-ids)", "manual"), results, meta)
        print(f"\nWrote {os.path.abspath(args.out)}")
        return 0

    print(f"{len(sources)} source(s) queued. Output -> {os.path.abspath(args.out)}")

    all_works, all_caps = [], []
    totals = {"works": 0, "downloads": 0, "empty": 0, "unresolved": 0}

    for source in sources:
        if stopping():
            print(f"\n[stop] Skipping remaining source: {source.label}")
            continue
        subdir = (os.path.join(args.out, source.slug) if len(sources) > 1 else args.out)
        results, meta = survey(source, subdir, args.skip_meta, args.verbose,
                               resume=args.resume, deep=args.deep_replay, project=project,
                               bulk=not args.per_work,
                               include_unarchived=args.include_unarchived,
                               skip_downloads=args.skip_downloads,
                               page_filter=not args.no_page_filter,
                               save_listing=args.save_listing,
                               include_chapters=args.include_chapters)
        if not results:
            totals["empty"] += 1
            continue
        all_works.extend(work_rows(source.label, results, meta,
                                   args.include_unarchived))
        all_caps.extend(capture_rows(source.label, results, meta))
        totals["works"] += len(results)
        totals["downloads"] += sum(1 for d in results.values()
                                   for r in d["downloads"] if is_real_download(r))
        totals["unresolved"] += sum(1 for d in results.values() if needs_retry(d))

    # Combined spreadsheets across every source, with a 'source' column
    if len(sources) > 1 and all_works:
        os.makedirs(args.out, exist_ok=True)
        write_csv(os.path.join(args.out, out_name(project, "all_works.csv")),
                  WORKS_HEADER, all_works)
        write_csv(os.path.join(args.out, out_name(project, "all_captures.csv")),
                  CAPTURES_HEADER, all_caps)

    print(f"\n{'=' * 52}")
    print(f"Done. {totals['works']} work(s) across {len(sources)} source(s); "
          f"{totals['downloads']} real download file(s).")
    if _THROTTLE["hits"]:
        print(f"Hit Internet Archive rate limits {_THROTTLE['hits']} time(s); "
              f"backed off automatically.")
    if totals["unresolved"]:
        print(f"\n{totals['unresolved']} work(s) could not be resolved "
              f"(status column = failed/suspect).")
        print("Their zero counts are NOT reliable. Rerun with --resume to retry "
              "just those:")
        print(f"  {resume_command()}")
    if stopping():
        print("\nStopped early -- spreadsheets written with what was collected.")
        print("Resume with the same command plus --resume:")
        print(f"  {resume_command()}")
    if totals["empty"]:
        print(f"{totals['empty']} source(s) returned nothing.")
    print(f"Output: {os.path.abspath(args.out)}")
    if totals["downloads"] == 0 and totals["works"]:
        print("\nNo download files archived -- this is the normal result. Use the "
              "best_full_work_url column and convert with pandoc. See README.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted.\n")
        sys.exit(130)
    finally:
        stop_run_log()
