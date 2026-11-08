# Things You Can Type

This is a list of commands you can copy. Each one says what it does in plain
words.

If you have not set the program up yet, start with the guide for your computer:
**GUIDE-WINDOWS.md**, **GUIDE-MAC.md** or **GUIDE-LINUX.md**.

Once your results arrive, **SPREADSHEET_CHEATSHEET.md** explains what they mean.

---

## Before you start

Every command below begins the same way:

**On Windows**, it starts with `python .\ao3_wayback.py`

**On a Mac or Linux**, it starts with `python3 ./ao3_wayback.py`

The examples use the Windows version. If you have a Mac, just change that first
bit and leave the rest alone.

Wherever you see **YOUR ADDRESS**, put in the web address of the AO3 page you
want. Keep the quote marks around it.

Wherever you see **NAME**, pick a short nickname for this batch of results, like
`myfics`. Your files get named after it.

---

## The main one

```
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --project NAME --include-chapters
```

This is the one you will use nearly every time. It looks up the page, finds
every saved copy of every story on it, and makes you a spreadsheet.

The `--include-chapters` part tells it to also look for individual chapters.
Leave it in. Long stories often only survived one chapter at a time.

---

## How to force stop the program

You can perform a forced stop of activity using `Ctrl-C` on your keyboard once or twice. The first `Ctrl-C` sets a stop flag - the current item finishes, the checkpoint saves, spreadsheets are written from what is in hand, and the exact resume command is printed. A second `Ctrl-C` aborts immediately, leaving the last checkpoint intact.

---

## Picking what to look up

Replace the middle part of the command depending on what you want.

**A tag, by its name:**
```
--tag "Hurt/Comfort"
```

**A tag, by its web address:**
```
--tag-url "https://archiveofourown.org/tags/Hurt%20Comfort/works"
```
Use this one if the tag name has unusual symbols in it.

**Somebody's public bookmarks:**
```
--tag-url "https://archiveofourown.org/users/THEIRNAME/bookmarks"
```

**Everything by one writer:**
```
--user "THEIRNAME"
```

**A collection:**
```
--collection "Yuletide2025"
```

You can paste the normal AO3 address. The program checks the archive for you and
tells you plainly if there is no saved copy.

---

## If it stops partway

Sometimes the archive gets busy and asks the program to slow down. If it stops,
nothing is lost.

**Carry on from where it stopped:**
```
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --project NAME --include-chapters --resume
```

**Carry on, but much more slowly** (use this if it keeps getting interrupted):
```
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --project NAME --resume --sleep 10
```

**Throw it all away and start over:**
```
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --project NAME --include-chapters --clean
```

---

## Stopping it on purpose

Hold **Ctrl** and press **C** once.

It finishes what it is doing, saves everything, makes your spreadsheet from what
it found so far, and shows you the command to carry on later. Nothing is lost.

If you press **Ctrl** and **C** twice, it stops right that second. You might
lose the last few stories it was working on, but everything before that is
still saved.

---

## Other useful bits

Add any of these to the end of a command.

| Add this | What it does |
|---|---|
| `--verbose` | Shows you what it is doing while it works. Nice for watching. |
| `--include-chapters` | Also looks for individual chapters. Recommended. |
| `--include-unarchived` | Also lists stories where nothing at all was saved. |
| `--sleep 10` | Goes slower and gentler. Use if the archive keeps saying no. |
| `--version` | Tells you which version you have. |

---

## Where your results go

Look in the folder called **ao3_wayback_out**, inside the folder you ran the
command from.

You will find:

- **NAME_works.csv** - the spreadsheet. This is the one you want.
- **NAME_captures.csv** - every single saved file, in detail.
- **NAME_report.md** - the same information written out as a document.

Double-click the spreadsheet to open it in Excel or a similar program.

**SPREADSHEET_CHEATSHEET.md** explains what the columns mean.

---

## Getting a story onto an e-reader

Open the spreadsheet, find a story, and click the link in the **read_url**
column. It opens in your web browser.

Then use your browser's **Save Page As** to keep a copy on your computer.

If you want it as a proper e-book, a free program called **Calibre**
(calibre-ebook.com) will turn that saved page into one.

---

## Two things to please avoid

The Internet Archive is a charity. They pay for all of this and let anyone use
it for free.

**Do not try to make the program go faster.** It waits between requests on
purpose. If it gets told to stop, waiting a few hours is the right answer.

**Do not share what you save.** These are other people's stories.
