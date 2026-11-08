# ao3-wayback

Survey what the Wayback Machine has archived for an Archive of Our Own tag, collection, user or bookmarks page, and produce a spreadsheet of every work found with direct links to the archived copies and the original story links (for when AO3 is back up).

Single file, Python 3.8+, standard library only, no install step.

**Non-technical users:** see `INSTALL-GUIDE-WINDOWS.md`, `INSTALL-GUIDE-MAC.md` or `INSTALL-GUIDE-LINUX.md` for step-by-step setup, `QUICK_COMMANDS.md` for commands to copy, and `SPREADSHEET_CHEATSHEET.md` for reading the results. This file is the technical reference.

---

## Contents

- [What it does](#what-it-does)
- [What you will actually recover](#what-you-will-actually-recover)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Sources](#sources)
- [Full option reference](#full-option-reference)
- [Common invocations](#common-invocations)
- [Output](#output)
- [How it works](#how-it-works)
- [Rate limiting and resumption](#rate-limiting-and-resumption)
- [Diagnostics](#diagnostics)
- [Known constraints](#known-constraints)
- [Etiquette](#etiquette)
- [Contributing](#contributing)
- [License](#license)

---

## What it does

Given an AO3 listing page, the script:

1. Queries the Wayback **CDX Server API** for every archived capture of that listing.
2. Fetches those captures and parses each work blurb for metadata: title, author, summary, fandoms, rating, archive warnings, categories, relationships, characters, freeform tags, word count, chapter count, last updated.
3. Looks up what is archived for each work under `/downloads/` and `/works/`.
4. Classifies each capture, and writes `NAME_works.csv`, `NAME_captures.csv` and `NAME_report.md`.

### Why CDX rather than archive.org search

Searching for a way to query the Wayback Machine leads to [archive.org's advanced search guide](https://help.archive.org/help/search-building-powerful-complex-queries/). That indexes archive.org's **own item collection** - uploaded books, audio, software, scanned texts. It does not index Wayback captures. You can search the captures off the main page but it only gives you one page at a time. I wanted a way to grab all the pages archived under AO3 collections, bookmarks or tags in one go without negatively impacting the Internet archive.

Wayback captures are served by the [CDX Server API](https://github.com/internetarchive/wayback/blob/master/wayback-cdx-server/README.md), which supports prefix matching, field selection, filtering, collapsing and result limits:

```
https://web.archive.org/cdx/search/cdx?url=archiveofourown.org/works/10726146*&matchType=prefix&output=json
```

---

## What you will actually recover

**Archived download files are overwhelmingly not files.**

AO3 serves `/downloads/<id>/Title.epub` with `Content-Disposition: attachment`. Crawlers do not follow attachment links, but they do request the URL and receive AO3's HTML error or login page, which Wayback then stores under the `.epub` address. The capture has a real work ID, a real filename and a real timestamp, and contains a few hundred bytes of HTML.

Measured across one real bookmarks page: **487 of 488 download captures were under 5 KB**, median 640 bytes, `Content-Type: text/html`.

The script classifies these. `archived_downloads` counts plausible files only; `stub_downloads` counts the rest; `captures.csv` marks every download row `yes` or `stub`.

**The recoverable content is `?view_full_work=true`** - AO3's single-page full-text view. It is ordinary HTML, crawlers follow it, and it contains the complete work. From the same page: 775 full-work captures across 56 works, median 96 KB, largest 909 KB.

**Coverage is uneven and often partial.** From a 367-work tag: 74 works had any archived copy, and only 25 of those were complete. The other 49 had a single page or chapter - 1.25 million words of fiction behind fragment captures. The `coverage` column reports this per work.

AO3 has also been blocked from the Wayback Machine wholesale more than once (https://morgandawn.livejournal.com/1598392.html), so coverage varies sharply between tags and eras.

---

## Requirements

| | |
|---|---|
| Python | 3.8 or newer |
| Dependencies | None. `urllib`, `csv`, `re`, `json`, `gzip`, `signal` |
| Network | Outbound HTTPS to `web.archive.org` |
| Optional | [pandoc](https://pandoc.org/) or [Calibre](https://calibre-ebook.com/) for HTML to EPUB conversion |

Runs unchanged on Windows, macOS and Linux. All paths use `os.path.join`; there are no shell-outs or platform-specific calls beyond `os.replace` and `signal.SIGINT`.

**macOS:** a python.org build does not use the system certificate store, and every request fails with `CERTIFICATE_VERIFY_FAILED` until you run `/Applications/Python 3.x/Install Certificates.command` once. Homebrew and pyenv builds are unaffected.

**CSV encoding:** output is `utf-8-sig` so Excel renders non-ASCII titles correctly on a double-click. Read programmatically with `encoding="utf-8-sig"` or the first column name arrives as `﻿source`.

---

## Quick start

```bash
python3 ao3_wayback.py --tag "Steve Rogers/Bucky Barnes" --project bucky
```

```bash
python3 ao3_wayback.py --tag-url "https://archiveofourown.org/users/someone/bookmarks" --project someone --include-chapters
```

Windows: `python .\ao3_wayback.py`.

Output lands in `./ao3_wayback_out/`. If `--project` is omitted and stdin and stdout are both TTYs, you are prompted for a name with the source slug as default; otherwise the default is used silently.

---

## Sources

All AO3 tag types - Fandom, Character, Relationship, Additional Tags, Archive Warning, Category, Rating - resolve to the same `/tags/<tag>/works` path. There is no per-type endpoint; the tag you name determines the type.

| Flag | Resolves to |
|---|---|
| `--tag NAME` | `tags/<encoded>/works` |
| `--tag-url URL` | Path extracted from the URL, encoding preserved |
| `--collection NAME` | `collections/<name>/works` |
| `--user NAME` | `users/<name>/works` |
| `--user NAME --pseud P` | `users/<name>/pseuds/<p>/works` |
| `--listing bookmarks` | Swaps `/works` for `/bookmarks` on any of the above |
| `--tags-file FILE` | One name or URL per line; `#` comments ignored |
| `--work-ids IDS` | Skips discovery entirely |

Source flags are repeatable and combinable in a single run. Multi-source runs write per-source subfolders plus combined `NAME_all_works.csv` and `NAME_all_captures.csv`.

`--tag-url` accepts a plain AO3 address or a `web.archive.org` wrapper; the wrapper is stripped and the underlying path queried. You do not need to locate a Wayback link first.

### Tag name encoding

AO3 substitutes certain characters with asterisk codes before percent-encoding. `ao3_tag_to_path()` applies `TAG_ESCAPES`:

| Character | Code | Verified |
|---|---|---|
| `/` | `*s*` | Yes, against a live relationship tag URL |
| `&` | `*a*` | No |
| `.` | `*d*` | No |
| `?` | `*q*` | No |
| `#` | `*h*` | No |

The unverified entries are the most likely failure point for an exotic tag. If a tag containing one returns nothing, use `--tag-url` to bypass encoding, and please open an issue with a working URL.

### Discovery outcomes

`find_listing_captures()` returns one of three states, and the script reports them distinctly:

- **captures found** - proceeds
- **none** - the index answered and has nothing; the script then queries the parent path and reports what *is* archived there
- **failed** - every query failed, so archival status is unknown. Deliberately not reported as "never archived"

---

## Full option reference

### Sources

| Flag | Argument | Description |
|---|---|---|
| `--tag` | NAME | Tag by name; special characters encoded automatically. Repeatable. |
| `--tag-url` | URL | AO3 or web.archive.org URL; encoding preserved. Repeatable. |
| `--tags-file` | FILE | File of tag names and/or URLs, one per line. |
| `--collection` | NAME | AO3 collection name. Repeatable. |
| `--user` | NAME | AO3 username. Repeatable. |
| `--pseud` | NAME | AO3 pseud; requires `--user`. |
| `--work-ids` | IDS | Comma-separated work IDs; skips listing discovery. |
| `--probe` | URL | Diagnostic. Fetches one URL and dumps status, final redirect target, headers and body. Nothing else runs. |

### Output control

| Flag | Default | Description |
|---|---|---|
| `--project` | prompted | Prefix for output filenames: `NAME_works.csv`, `NAME_captures.csv`, `NAME_report.md`, `NAME_progress.json`. Slugified. |
| `--out` | `./ao3_wayback_out` | Output directory. |
| `--listing` | `works` | `works` or `bookmarks`. |
| `--include-unarchived` | off | Write works with nothing archived. Off by default. |

### Run control

| Flag | Default | Description |
|---|---|---|
| `--resume` | off | Continue from the checkpoint. Re-queues rows marked `failed`/`suspect`. |
| `--clean` | off | Delete this project's prior output before starting. Mutually exclusive with `--resume`. |
| `--sleep` | `2.0` | Base delay in seconds between requests. |
| `--skip-meta` | off | Do not fetch individual work pages to fill metadata gaps. |

### Lookup tuning

| Flag | Default | Description |
|---|---|---|
| `--include-chapters` | off | Also collect `/chapters/<n>` captures. Larger responses, better coverage of long works. |
| `--per-work` | off | One CDX query per work instead of grouped prefix queries. Much slower. |
| `--no-page-filter` | off | Omit the server-side page filter. Larger responses. |
| `--deep-replay` | off | Try all four replay-URL spellings on a capture that will not load. |
| `--headers` | `minimal` | `minimal` (User-Agent + Accept-Encoding) or `browser` (adds Accept headers). |
| `--user-agent` | | Override the User-Agent string. |

### Diagnostics

| Flag | Description |
|---|---|
| `--save-listing DIR` | Write each fetched listing page to DIR exactly as the parser receives it. |
| `--verbose` | Also echo the run log's detail to the console. The log is written either way. |
| `--version` | Print version and exit. |

---

## Common invocations

```bash
# Standard run
python3 ao3_wayback.py --tag-url "URL" --project NAME --include-chapters --verbose

# Resume after an interruption or rate limiting
python3 ao3_wayback.py --tag-url "URL" --project NAME --include-chapters --resume --verbose

# Resume gently after being throttled
python3 ao3_wayback.py --tag-url "URL" --project NAME --resume --sleep 10 --verbose

# Discard prior output and start over
python3 ao3_wayback.py --tag-url "URL" --project NAME --clean --verbose

# Full catalogue including works with nothing archived
python3 ao3_wayback.py --tag-url "URL" --project NAME --include-unarchived --resume

# Several tags into one folder
python3 ao3_wayback.py --tags-file tags.txt --out ./results --project batch

# Background run with a log (Linux/macOS)
nohup python3 ao3_wayback.py --tag-url "URL" --project NAME --verbose > run.log 2>&1 &

# Background run with a log (PowerShell) - note --project is required here
python .\ao3_wayback.py --tag-url "URL" --project NAME --verbose *> run.log
```

`--project` is mandatory for any run whose stdout is redirected: the prompt would otherwise be written to the log where it cannot be seen, and the process would appear to hang.

---

## Output

```
ao3_wayback_out/
├── NAME_works.csv        one row per work
├── NAME_captures.csv     one row per archived capture
├── NAME_report.md        human-readable summary
├── NAME_progress.json    checkpoint
└── NAME_run.log          full detail of every run, appended
```

**Logging is automatic.** Per-request detail always goes to `NAME_run.log`;
the console gets progress lines only, unless `--verbose` echoes the detail
there as well. This matters for long runs: a terminal retains all scrollback in
memory, and a multi-hour run that writes every request to the console can grow
the terminal until it dies and takes the run with it. Shell redirection is
therefore unnecessary - `--verbose` is now safe at any run length.

Filenames are project-prefixed so multiple projects can share a directory. An unattended run that would overwrite an existing `NAME_works.csv` writes `NAME_2_works.csv` and logs the substitution. `--resume` always reuses the same name.

If an output file is locked (open in Excel), the write falls back to `NAME_works_1.csv` rather than raising. The checkpoint is written before the spreadsheets, so a locked file never costs a completed run.

### `NAME_works.csv`

By default, only works with something archived are written. Works whose status is `failed`, `suspect` or `not queried` are always written regardless, because their blank columns mean *unknown*, not *nothing*.

| Col | Field | Notes |
|---|---|---|
| A | `source` | Source label |
| B | `work_id` | AO3 numeric ID |
| C | `title` | |
| D | `author` | Pipe-joined for co-authors; `Anonymous` where applicable |
| E | `summary` | Tags stripped, entities unescaped, newlines collapsed |
| F | `ao3_url` | `https://archiveofourown.org/works/<id>` |
| G | `fandoms` | Pipe-joined |
| H | `rating` | |
| I | `warnings` | Archive warnings; distinct from tags |
| J | `categories` | F/F, F/M, Gen, M/M, Multi, Other |
| K | `relationships` | Pipe-joined |
| L | `characters` | Pipe-joined |
| M | `freeform_tags` | AO3 "Additional Tags" |
| N | `words` | |
| O | `chapters` | |
| P | `updated` | |
| Q | `archived_downloads` | Count of plausible download files |
| R | `stub_downloads` | Count of download URLs archived as error pages |
| S | `archived_pages` | Count of story-page captures |
| T | `download_bytes` | Integer, or blank if CDX reported nothing usable |
| U | `download_size` | Human-readable |
| V | `full_work_bytes` | Size of the full-work capture |
| W | `read_url` | Best available link: full-work view, else work page, else real download |
| X | `coverage` | `complete`, `partial`, or blank |
| Y | `chapters_archived` | Distinct chapter captures |
| Z | `best_download_url` | Newest plausible download |
| AA | `best_full_work_url` | Newest true `?view_full_work` capture |
| AB | `other_page_urls` | Up to 8 more captures, pipe-separated |
| AC | `status` | `ok`, `failed`, `suspect`, `not queried` |
| AD | `metadata_source` | `listing` or `work page` |

**`coverage`** distinguishes a whole work from a fragment. `complete` means a full-work capture or a real download file exists. `partial` means only a single page or chapter survived - for a multi-chapter work, one chapter.

**`status`** determines whether a zero is meaningful:

| Value | Meaning |
|---|---|
| `ok` | Lookup succeeded; counts are reliable |
| `failed` | A query did not answer; counts prove nothing |
| `suspect` | Queries returned empty while rate-limited; counts unreliable |
| `not queried` | Metadata only; lookup pending |

### `NAME_captures.csv`

| Col | Field | Notes |
|---|---|---|
| A-E | `source`, `work_id`, `title`, `author`, `ao3_url` | Repeated so the file stands alone |
| F | `kind` | `download` or `page` |
| G | `looks_real` | `yes` or `stub` on download rows; blank on page rows |
| H | `timestamp` | Wayback 14-digit timestamp |
| I | `mimetype` | As reported by CDX |
| J | `bytes` | Blank if CDX reported an implausible value |
| K | `original_url` | The AO3 URL as crawled |
| L | `wayback_url` | Replay URL with `id_` |

### Replay URLs

All Wayback URLs use the `id_` modifier (`/web/<timestamp>id_/<url>`), which serves the original bytes without the Wayback toolbar injected. Strip `id_` to browse with the toolbar.

**Inner URLs must be double-encoded.** `/web/<ts>/https://.../tags/A%20B/works` returns `400 Bad request`; `A%2520B` returns `200`. Confirmed empirically; not documented upstream as far as I can tell. `wayback_inner()` normalises any input spelling and double-encodes it. Some captures additionally refuse `id_`, so `fetch_capture()` falls back to the toolbar form and parses that.

---

## How it works

### Bulk lookup

Large pulls are SLOW. A large category pull WILL take MULTIPLE HOURS. This is on purpose so we don't take Wayback down. DO NOT MODIFY THE CODE TO SET SLEEP TO 0. A naive implementation issues two CDX queries per work - 734 for a 367-work tag, which is reliably rate-limited into failure. Instead, work IDs are grouped by leading digits (`BULK_GROUP_LEN = 2`) and one prefix query is issued per group, with results matched locally.

On a real 367-work tag this reduced ~734 requests to ~98, and raised the success rate from roughly 2-in-9 to 348-of-349 in a single pass.

Two properties follow:

- A response at `BULK_LIMIT` (150,000 rows) is treated as **truncated** and the group is split, up to `MAX_SUBDIVIDE` times. A truncated response otherwise looks like success and would convert missing captures into confident zeros.
- When a bulk query **succeeds**, a work ID absent from the results genuinely has nothing archived. This is a stronger guarantee than per-work lookup provides.

Groups that fail or cannot be split further fall back to individual lookups.

### Capture classification

Two filters decide what is recorded, both applied locally:

**`is_story_page()`** whitelists readable work pages against `STORY_PAGE_RE`:

```
https?://[^/]+/works/\d+(?:/chapters/\d+)?/?(?:\?[^#]*)?(?:#.*)?
```

This accepts the work page, `?view_full_work=true`, `?view_adult=true`, trailing slashes and `#fragments`; it rejects `/comments`, `/kudos`, `/bookmarks`, `/collections`, `/navigate` and `/hit_count.json`. URLs carrying Cloudflare challenge tokens (`__cf_chl`) are rejected as interstitials.

The server-side `PAGE_FILTER` sent with each query is a bandwidth optimisation only: **CDX applies filter regexes as partial matches**, so shape is not guaranteed by the query. On one real page this local filter removed 26% of page captures.

**`is_real_download()`** accepts an ebook mimetype at face value, otherwise requires size above `STUB_MAX_BYTES` (5120). CDX occasionally returns implausible lengths (one observed at -10,593,495,131), which `size_of()` treats as unknown.

### Parsing

Metadata is extracted with regex against archived HTML. AO3's blurb template is stable enough to make this practical. Two properties of real archived pages are handled explicitly:

- **Mixed quote styles.** AO3 emits `<li class='freeforms'>` alongside `<a class="tag">` in the same document. All class matching is quote-agnostic via `cls()`. Requiring double quotes silently loses relationships, characters and freeform tags.
- **Toolbar rewriting.** A capture fetched without `id_` has its hrefs rewritten to absolute `web.archive.org` URLs, and its quotes normalised. Href matching is therefore prefix-agnostic. A page fetched without `id_` can parse while the raw original does not, which makes a parser bug look like an archive problem.

Blurb slicing matches `blurb` alone rather than `work blurb`, so bookmarks (`bookmark blurb group`) and series listings parse with the same code. Entries without a `/works/<id>` link - bookmarked series, external works - are skipped rather than mis-parsed.

---

## Rate limiting and resumption

More info about the intentional script throttling and how I handled it so we don't lose much progress if something goes sideways: The Internet Archive throttles aggressively on sustained use, and does so in three ways that must all be treated as pushback:

| Signal | Handling |
|---|---|
| HTTP 429/5xx | Honour `Retry-After`; exponential backoff with jitter |
| Connection errors | Treated as pushback, not transport noise |
| HTTP 200 with an empty body | Treated as failure, not success |

That last case matters: an empty 200 arriving as success previously reset the failure streak, which prevented the cooldown from ever firing.

| Constant | Value | Effect |
|---|---|---|
| `DEFAULT_SLEEP` | 2.0 s | Base inter-request delay |
| `MAX_EXTRA` | 30.0 s | Ceiling on the adaptive delay |
| `COOLDOWN_AFTER` | 6 | Consecutive failures before a long pause |
| `COOLDOWN_SECS` | 90.0 s | Length of that pause |
| `RETRY_PASSES` | 2 | Sweeps over unresolved works, at 2x and 4x sleep |
| `GIVE_UP_AFTER` | 12 | Consecutive failed works before aborting the run |

A global adaptive delay rises on pushback and decays on success, so a long run slows under pressure and recovers.

**Checkpointing** writes `NAME_progress.json` atomically every 5 works. `--resume` re-queues anything marked `failed` or `suspect`, so a throttled run's false zeros are retried rather than kept.

**SIGINT:** the first `Ctrl-C` sets a stop flag - the current item finishes, the checkpoint saves, spreadsheets are written from what is in hand, and the exact resume command is printed. A second `Ctrl-C` aborts immediately, leaving the last checkpoint intact.

---

## Diagnostics

```bash
# What did the server actually return for this URL?
python3 ao3_wayback.py --probe "https://web.archive.org/web/20260831035107id_/https://archiveofourown.org/works/123"

# What exactly is the parser receiving?
python3 ao3_wayback.py --tag-url "URL" --save-listing ./dump --verbose
```

`--probe` prints status, final URL after redirects, headers and body. `--save-listing` writes each fetched page byte-for-byte as the parser sees it - attach one of these to any parsing bug report.

---

## Known constraints

- **Four `TAG_ESCAPES` entries are unverified.** See [Tag name encoding](#tag-name-encoding).
- **CDX percent-encoding behaviour is inconsistent.** `find_listing_captures()` tries three encodings of each path and keeps whichever returns rows. This is empirical, not documented.
- **Parsing is regex against HTML.** A truncated capture yields a work ID with empty metadata rather than a crash. Rows with a `work_id` and no `title` are that case. If AO3 changes templates, `parse_listing()` and `parse_work_page()` are the places to look.
- **Coverage reflects the crawler, not the tag.** Works posted after the last capture, restricted works, and anything removed from Wayback are absent. A listing capture is a point-in-time snapshot; multiple captures are merged newest-first, but this is never a complete census.
- **Multi-page listings depend on `?page=N` having been crawled.** Prefix matching picks them up when they exist.
- **Bookmarked series and external works are skipped** - no `/works/<id>` link to key on.

---

## Etiquette

These are fanworks and they belong to the people who wrote them. This tool surfaces links to pages the Internet Archive has already made public. It does not scrape AO3, bypass access controls, or republish anything.

Some authors do not want their work preserved outside AO3, and some have asked the Internet Archive to remove it. Keep what you save for your own reading, do not redistribute it, and do not use this to reconstruct works an author deliberately took down.

The default pacing is deliberate. Again DO NOT SET `--sleep 0`. If the Archive starts refusing requests, waiting is the correct response - rotating IPs to evade a block tends to get the new address blocked too, sometimes affecting other users of that network.

---

## Contributing

I have a full time job so I am not babysitting this, but I am open to helping out with useful issues to make the script better.

Useful issues:

- Corrections to `TAG_ESCAPES`, with a real AO3 URL demonstrating the substitution
- AO3 template changes that break parsing - attach a `--save-listing` dump
- CDX behaviour that defeats the encoding variants, the bulk grouping, or the truncation guard

---

## License

MIT. And it harm none, do as you will.
