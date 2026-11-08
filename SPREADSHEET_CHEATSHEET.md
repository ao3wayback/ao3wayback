# Understanding Your Spreadsheets

You ran the program and it made you a spreadsheet. This explains what is in it.

You do not need to understand everything here. The short version is at the top.

---

## The short version on output files

Open the file ending in **_works.csv** by double-clicking it.

Each row is one story.

**Look at two columns:**

1. **read_url** - this is a link. Click it and the story opens in your web browser.
2. **coverage** - this tells you how much of the story was saved.

That is really all you have to have, the rest is to give you additional context on what you got.

---

## The coverage column

This is the most important column, so it is worth understanding properly.

| It says | What that means |
|---|---|
| **complete** | The whole story was saved. You can read it start to finish. |
| **partial** | Only part was saved - usually one chapter, or just the first page. |

A long story marked **partial** might be 200 pages long with only 10 pages
saved. The link still works, but you will not get the whole thing.

The column next to it, **chapters_archived**, tells you how many chapters
survived for those partial ones.

---

## Why some stories are missing

The spreadsheet only lists stories that have a saved copy somewhere.

If a tag had 367 stories and your spreadsheet has 74 rows, that means 74 of them
were saved and the rest were not. That is normal. Nobody saved everything.

Think of it like a library that burned down, and someone happened to photocopy a
few books beforehand. You get the photocopies. The rest are gone.

If you want to see the full list anyway, including the ones with nothing saved,
add `--include-unarchived` to your command. Their titles and descriptions are
still there, which is handy as a reading list for when AO3 comes back.

---

## All the columns, briefly

You can ignore most of these. They are here if you get curious.

### About the story itself

| Column | What it is |
|---|---|
| title | The story's name |
| author | Who wrote it |
| summary | The description the author wrote |
| fandoms | What it is based on |
| rating | General, Teen, Mature or Explicit |
| warnings | AO3's content warnings |
| categories | F/F, M/M, Gen and so on |
| relationships | Which characters are paired up |
| characters | Who is in it |
| freeform_tags | The extra tags authors add themselves |
| words | How long it is |
| chapters | How many chapters |
| updated | When the author last touched it |
| ao3_url | The normal AO3 link. Dead while AO3 is down, works again afterwards. |

### About the saved copies

| Column | What it is |
|---|---|
| **read_url** | **The link to click.** |
| **coverage** | **complete or partial. See above.** |
| chapters_archived | How many chapters survived |
| archived_pages | How many saved copies exist |
| other_page_urls | More links for the same story, if there are any |
| best_full_work_url | A link to the whole story on one page, if one was saved |

### The technical ones

| Column | What it is |
|---|---|
| work_id | AO3's internal number for the story |
| source | Which tag or page this came from |
| status | Should say **ok**. See the next section. |
| archived_downloads | Real downloadable files found. Usually 0. |
| stub_downloads | Fake download links. See below. |
| best_download_url | A link to a real file, if one exists |
| download_bytes, download_size, full_work_bytes | File sizes |
| metadata_source | Where the story's details came from |

---

## The status column

This should say **ok** on every row. That means the program checked properly
and you can trust what it found.

If it says **failed** or **suspect**, the archive was too busy to answer
properly for that story. The row might say "nothing saved" when actually
something was. Run the command again with `--resume` on the end and it will
have another go at just those.

If it says **not queried**, the program ran out of time before reaching that
one. Same fix: `--resume`.

---

## Why most download links are empty

This surprises people, so it is worth explaining.

AO3 lets you download stories as e-book files. You would think those got saved.
Mostly they did not.

When the archive's robot visited those download addresses, AO3 gave it an error
message instead of the actual file. The robot saved the error message. So there
is something sitting at the address where the book should be, but it is not the
book - it is a few lines of "sorry, something went wrong".

In one real test, 487 out of 488 download links turned out to be these empty
shells.

The program checks the size of each one and sorts them out for you.
**archived_downloads** counts the real files. **stub_downloads** counts the
fakes.

**This is why you should use the read_url column instead.** Those are saved web
pages, and they are real.

---

## Finding things in the spreadsheet

Most spreadsheet programs let you sort and filter. In Excel, click a column
heading, then **Data** then **Filter**.

Some useful things to do:

- **Filter coverage to "complete"** to see only the stories you can read in full.
- **Sort by words** to put the longest stories first.
- **Filter freeform_tags** to find a theme you like.
- **Filter rating** to leave out anything you would rather not see.
- **Filter warnings** to check for content you want to avoid.

---

## The other file

There is a second spreadsheet ending in **_captures.csv**. You probably do not
need it.

It lists every single saved copy individually, so one story might take up
twenty rows. It is there for digging into a particular story when the main
spreadsheet is not enough.

If you do open it, the **looks_real** column marks each download link as either
**yes** (a real file) or **stub** (one of the empty shells described above).

---

## If something looks wrong

Check the **status** column first. Anything other than **ok** means that row is
not reliable, and running your command again with `--resume` on the end will
retry it.

If whole columns are empty on every row, something went wrong with the run
itself. The install guide file for your computer operating system has a troubleshooting section near the end.
