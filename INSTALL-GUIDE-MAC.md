# The Mac Guide

A guide for people who have never typed a command into a computer before. You
do not need to know anything about programming. Follow the steps in order and
it will work.

**One warning before you start:** there is an extra step on a Mac (Part 1,
Step 3) that is very easy to skip, and skipping it makes everything fail with a
confusing message. It takes two clicks. Please do not skip it.

---

## What is this?

Archive of Our Own (AO3) is down. A charity called the Internet Archive had
already saved copies of some AO3 pages before that happened, the way you might
photocopy a page from a library book.

This program digs through those saved copies, finds the stories from a tag or a
bookmarks page, and makes you a spreadsheet with links to read them.

**What you get:** a spreadsheet of stories with titles, authors, descriptions,
tags, and a link to read each one.

**What you will not get:** everything. Only some stories were saved. It is
normal for a tag with 300 stories to turn up 70.

**How long it takes:** about fifteen minutes to set up the first time, then a
couple of minutes to start a search. The search itself can run for an hour or
more while you do something else.

---

# Part 1: Setting up

You only do this part once, ever.

## Step 1: Install Python

Python is the language this program is written in. Older Macs came with a very
old version and newer ones have none at all, so you need a current one either
way.

1. Go to **python.org/downloads**
2. Click the big yellow **Download Python** button
3. When it finishes downloading, double-click the file that was downloaded
4. Click **Continue**, **Continue**, **Agree**, then **Install**
5. Type your Mac password when it asks
6. **Leave the window that appears at the end open.** You need it for Step 3.

## Step 2: Open the typing window

Your Mac has a window where you type instructions instead of clicking things. It
is called Terminal.

1. Hold **Command** and press the **space bar**
2. Type `terminal`
3. Press **Return**

A plain window opens. This is where you will type things.

Now type this exactly and press **Return**:

```
python3 --version
```

It should print something like `Python 3.13.1`. The numbers do not matter.

**Notice the number 3 on the end of the word python.** On a Mac it is always
`python3`, never just `python`. Every command in this guide uses it.

## Step 3: The step everyone misses

Python on a Mac does not know how to check that websites are genuine until you
run a small file that came with it. Until you do, **every single thing this
program tries will fail** with a message about certificates.

1. Open **Finder**
2. Click **Applications** in the sidebar on the left
3. Find the folder called **Python 3.13** (or whatever version you installed)
4. Open it
5. Double-click the file called **Install Certificates.command**
6. A window opens, some text scrolls past, and it says something like
   `process completed`
7. Close that window

That is it. Two clicks, and it saves you an evening of confusion.

## Step 4: Make a folder

1. Open **Finder**
2. Click **Desktop** in the sidebar
3. Right-click (or hold Control and click) on the empty space
4. Choose **New Folder**
5. Call it `ao3tool` and press Return

## Step 5: Put the program in the folder

Save the file **ao3_wayback.py** into that `ao3tool` folder.

**Then check its name.** Safari sometimes adds `.txt` to the end of downloads.
In Finder, the file must be called exactly `ao3_wayback.py`.

If it says `ao3_wayback.py.txt`, click the name once, wait a moment, click it
again to rename it, and remove the `.txt`. If your Mac warns you about changing
the ending, click **Use .py**.

**That is the setup finished.** You never have to do Part 1 again.

---

# Part 2: Using it

## Step 1: Find the address of what you want

You need the web address of the AO3 page you are interested in.

**If you have an old link** saved in your bookmarks, in a message to a friend,
or in your history, use that. It looks something like:

```
https://archiveofourown.org/tags/Some%20Tag%20Name/works
```

or

```
https://archiveofourown.org/users/someone/bookmarks
```

**If you do not have one:**

1. Go to **web.archive.org**
2. In the search box, type `archiveofourown.org/tags`
3. Look through what it has until you find the tag you want
4. Copy the whole address from the top of your browser

Either kind of address works. The program sorts it out.

## Step 2: Point Terminal at your folder

This is the fiddliest bit, but there is a trick that makes it easy.

1. Open Terminal (Command and space, type `terminal`, press Return)
2. Type `cd ` - that is the two letters c and d, **then a space**. Do not press
   Return yet.
3. Open **Finder** and find your `ao3tool` folder on the Desktop
4. **Drag the folder out of Finder and drop it onto the Terminal window**

   Terminal fills in where the folder lives, so you do not have to type it.
5. Now press **Return**

To check it worked, type `ls` and press Return. You should see
`ao3_wayback.py` listed.

## Step 3: Type the command

Type this, but put your own address between the quote marks:

```
python3 ./ao3_wayback.py --tag-url "PUT YOUR ADDRESS HERE" --include-chapters --verbose
```

**To paste into Terminal**, Command and V works normally.

**Keep the quote marks.** AO3 addresses have spaces and odd symbols in them, and
without the quotes the computer reads it wrong.

Press **Return**.

## Step 4: Give it a name

It will ask you:

```
Project name for the output files [something]:
```

Type a short nickname for this batch, like `myfics`, and press Return. Or just
press Return to accept what it suggests.

Your spreadsheet will be named after this, so `myfics` gives you
`myfics_works.csv`.

## Step 5: Wait

Text scrolls past. That is normal and means it is working. Here is what you are
looking at:

| If you see | It means |
|---|---|
| `20 work(s), 20 with titles` | Good. It is reading a saved page. |
| `367 unique work ID(s)` | Good. It found 367 stories to check. |
| `[1/367] work 79145276 -- full of stars` | Good. Working through them. |
| `HTTP 503 -- retry 1/5 in 8s` | Normal. The archive asked it to slow down. It waits and tries again by itself. |
| `(+4s)` next to the numbers | Normal. It is being extra polite. |
| `Capture 2026... is unavailable` | Normal. One saved page is broken. It skips it. |

**This takes a while.** For a big tag, an hour or more. That is on purpose. The
Internet Archive is a charity, and rushing them gets you blocked. Start it and
go and do something else.

**Do not close your laptop lid.** That puts the Mac to sleep and stops the
program. Leave it open, or change the sleep setting in System Settings.

**You can stop it any time.** Hold **Control** and press **C** once - that is
Control, not Command. It finishes what it is doing, saves everything, makes your
spreadsheet from what it has, and shows you how to carry on later. Nothing is
lost.

## Step 6: Open your results

In your `ao3tool` folder there is now a folder called **ao3_wayback_out**.

Inside it, double-click the file ending in **_works.csv**. It opens in Numbers
or Excel.

Each row is a story. Look at the **read_url** column - that is a link, and
clicking it opens the story in your web browser.

**SPREADSHEET_CHEATSHEET.md explains the rest of the columns.**

---

# Part 3: TROUBLESHOOTING - When something goes wrong

## Anything mentioning certificates or SSL

You skipped Part 1, Step 3. Go and do it now: Applications, your Python folder,
double-click **Install Certificates.command**.

This is far and away the most common problem on a Mac.

## "command not found: python3"

Python did not install properly. Install it again from Part 1, Step 1, then
**quit Terminal completely** (Command and Q) and open it fresh.

## "python: command not found"

You typed `python`. On a Mac it has to be `python3`.

## "No such file or directory"

Terminal is pointing at the wrong folder. Do Part 2, Step 2 again - type `cd `
with a space, drag your folder onto the window, press Return.

Or the file got named `ao3_wayback.py.txt`. See Part 1, Step 5.

## Lots of red text saying HTTP 503

Perfectly normal on a big tag. It slows itself down and keeps going.

If it carries on and nothing is getting through, the archive has temporarily
stopped answering you. **Stop it (Control and C) and come back in a few hours.**
Then run the same command with two extra bits on the end:

```
python3 ./ao3_wayback.py --tag-url "YOUR ADDRESS" --resume --sleep 10
```

`--resume` carries on from where it stopped. `--sleep 10` makes it much gentler.

Trying again straight away makes things worse, not better.

## It stopped and said the Internet Archive is refusing requests

That is it working properly. It noticed nothing was getting through and stopped
rather than wasting your evening. Everything it found is saved. Come back in a
few hours and use `--resume`.

## It stopped when I closed my laptop

Yes, that happens. Leave the lid open next time, and use `--resume` to carry on.

## I want to start completely fresh

Add `--clean` to the end of your command. It throws the old results away first.

## The spreadsheet has far fewer stories than the tag does

That is expected. Only some stories were ever saved. A tag with 300 stories
turning up 70 is a normal result, not a failure.

---

# Part 4: The commands, all together

Put your own address in place of **YOUR ADDRESS**, keeping the quote marks.

**Normal run:**
```
python3 ./ao3_wayback.py --tag-url "YOUR ADDRESS" --include-chapters --verbose
```

**Carry on after stopping:**
```
python3 ./ao3_wayback.py --tag-url "YOUR ADDRESS" --include-chapters --resume --verbose
```

**Carry on gently, after being told to slow down:**
```
python3 ./ao3_wayback.py --tag-url "YOUR ADDRESS" --resume --sleep 10 --verbose
```

**Start over from scratch:**
```
python3 ./ao3_wayback.py --tag-url "YOUR ADDRESS" --include-chapters --clean --verbose
```

**Choose the name yourself instead of being asked:**
```
python3 ./ao3_wayback.py --tag-url "YOUR ADDRESS" --project myfics --include-chapters
```

---

# A note about being polite

The Internet Archive is a charity. They save the web and let anyone look at it
for free, paid for by donations.

This program waits between requests on purpose. Please do not try to speed it
up. If it gets blocked, waiting is the right answer.

These are also other people's stories. Keep what you save for your own reading,
and when AO3 comes back, use its own download buttons.
