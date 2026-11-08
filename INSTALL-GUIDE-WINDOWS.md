# The Windows Guide

A guide for people who have never typed a command into a computer before. You
do not need to know anything about programming. Follow the steps in order and
it will work.

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

Python is the language this program is written in. Your computer almost
certainly does not have it yet.

1. Go to **python.org/downloads**
2. Click the big yellow **Download Python** button
3. When it finishes downloading, double-click the file to open it

**Now stop and read this next bit carefully. It is the most important step in
this whole guide.**

At the bottom of the window that opens, there is a small square checkbox next to
the words **"Add python.exe to PATH"**. It is empty.

**Click it so it has a tick in it.**

If you skip this, nothing else in this guide will work, and the error message
will not tell you why.

4. Now click **Install Now**
5. Wait for it to finish, then click **Close**

## Step 2: Open the typing window

Windows has a window where you type instructions instead of clicking things. It
is called PowerShell.

1. Click the **Start** button
2. Type the word `powershell`
3. Click **Windows PowerShell** when it appears in the list

A window opens with a dark background and some text. This is where you will type
things.

## Step 3: Check Python arrived

Type this exactly, then press the **Enter** key:

```
python --version
```

**If it prints something like `Python 3.13.1`** - lovely. Move on to Step 4. The
numbers do not matter.

**If a shop window opens instead** (the Microsoft Store) - close it. Type this
instead and press Enter:

```
python3 --version
```

If that works, then everywhere in this guide you see the word `python`, you
should type `python3` instead. Write that on a sticky note.

**If it says "not recognized"** - the tick box from Step 1 got missed. Go back
and install Python again, making sure to tick it this time. You do not need to
uninstall anything first.

## Step 4: Make a folder

1. Open **File Explorer** (the yellow folder icon on your taskbar)
2. Click **Desktop** on the left-hand side
3. Right-click on the empty white space
4. Choose **New**, then **Folder**
5. Call it `ao3tool` and press Enter

## Step 5: Put the program in the folder

Save the file **ao3_wayback.py** into that `ao3tool` folder.

**Then check its name.** Windows sometimes adds `.txt` to the end of files
without telling you, which breaks things.

1. In File Explorer, click **View** at the top
2. Make sure **File name extensions** has a tick next to it
3. Look at your file. It must be called exactly `ao3_wayback.py`
4. If it says `ao3_wayback.py.txt`, rename it and delete the `.txt` part

## Step 6: Stop the window freezing

This is a strange one, but it will save you a lot of confusion.

By default, if you click inside the PowerShell window while something is
running, Windows **pauses the program** until you press a key. People lose hours
to this, thinking it has crashed.

1. Open PowerShell if it is not already open
2. Right-click on the **title bar** at the very top of the window
3. Click **Defaults**
4. Click the **Options** tab
5. Find **QuickEdit Mode** and click it so the tick goes away
6. Click **OK**
7. Close PowerShell

**That is the setup finished.** You never have to do Part 1 again.

---

# Part 2: Using it

## Step 1: Find the address of what you want

You need the web address of the AO3 page you are interested in.

**If you have an old link** saved in your bookmarks, in a message to a friend,
or in your browsing history, use that. It looks something like:

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

## Step 2: Open the typing window in your folder

1. Open **File Explorer** and go to your `ao3tool` folder on the Desktop
2. Hold down the **Shift** key and **right-click** on the empty white space
   inside the folder
3. Choose **Open PowerShell window here**

   (On newer Windows it might say **Open in Terminal**. That is the same thing.)

A window opens, already pointing at the right folder. You can tell because the
text at the start of the line ends with `\ao3tool`.

## Step 3: Type the command

Type this, but put your own address between the quote marks:

```
python .\ao3_wayback.py --tag-url "PUT YOUR ADDRESS HERE" --include-chapters --verbose
```

**To paste something into PowerShell, right-click.** That is it. The usual
Ctrl+V often does not work.

**Keep the quote marks.** AO3 addresses have spaces and odd symbols in them, and
without the quotes the computer reads it wrong.

Press **Enter**.

## Step 4: Give it a name

It will ask you:

```
Project name for the output files [something]:
```

Type a short nickname for this batch, like `myfics`, and press Enter. Or just
press Enter to accept what it suggests.

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

**You can stop it any time.** Hold **Ctrl** and press **C** once. It finishes
what it is doing, saves everything, makes your spreadsheet from what it has, and
shows you how to carry on later. Nothing is lost.

## Step 6: Open your results

In your `ao3tool` folder there is now a folder called **ao3_wayback_out**.

Inside it, double-click the file ending in **_works.csv**. It opens in Excel.

Each row is a story. Look at the **read_url** column - that is a link, and
clicking it opens the story in your web browser.

**SPREADSHEET_CHEATSHEET.md explains the rest of the columns.**

---

# Part 3: TROUBLESHOOTING - When something goes wrong

## "python is not recognized"

The tick box got missed when installing. Go back to Part 1, Step 1 and install
Python again, ticking **"Add python.exe to PATH"**.

## The Microsoft Store keeps opening

Type `python3` instead of `python` in every command.

## "No such file or directory"

You are in the wrong folder. Close the window, go to your `ao3tool` folder in
File Explorer, hold Shift, right-click the empty space, and choose **Open
PowerShell window here**.

Or the file got named `ao3_wayback.py.txt`. See Part 1, Step 5.

## Lots of red text saying HTTP 503

Perfectly normal on a big tag. It slows itself down and keeps going.

If it carries on and nothing is getting through, the archive has temporarily
stopped answering you. **Stop it (Ctrl and C) and come back in a few hours.**
Then run the same command with two extra bits on the end:

```
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --resume --sleep 10
```

`--resume` carries on from where it stopped. `--sleep 10` makes it much gentler.

Trying again straight away makes things worse, not better.

## It stopped and said the Internet Archive is refusing requests

That is it working properly. It noticed nothing was getting through and stopped
rather than wasting your evening. Everything it found is saved. Come back in a
few hours and use `--resume`.

## The window froze and nothing is happening

You clicked inside it. Press **Enter** and it will carry on.

To stop this happening again, do Part 1, Step 6.

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
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --include-chapters --verbose
```

**Carry on after stopping:**
```
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --include-chapters --resume --verbose
```

**Carry on gently, after being told to slow down:**
```
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --resume --sleep 10 --verbose
```

**Start over from scratch:**
```
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --include-chapters --clean --verbose
```

**Choose the name yourself instead of being asked:**
```
python .\ao3_wayback.py --tag-url "YOUR ADDRESS" --project myfics --include-chapters
```

---

# A note about being polite

The Internet Archive is a charity. They save the web and let anyone look at it
for free, paid for by donations.

This program waits between requests on purpose. Please do not try to speed it
up. If it gets blocked, waiting is the right answer.

These are also other people's stories. Keep what you save for your own reading,
and when AO3 comes back, use its own download buttons.
