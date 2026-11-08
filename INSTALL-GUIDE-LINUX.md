# The Linux Guide

A guide for people who have never typed a command into a computer before. You
do not need to know anything about programming. Follow the steps in order and
it will work.

**Good news:** Linux needs the least setting up of any system. Python is almost
certainly already there.

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

**How long it takes:** about five minutes to set up, then a couple of minutes to
start a search. The search itself can run for an hour or more while you do
something else.

---

# Part 1: Setting up

You only do this part once, ever.

## Step 1: Open the typing window

Hold **Ctrl** and **Alt** and press **T**.

A window opens. This is where you type instructions instead of clicking things.

If nothing happens, look for **Terminal** or **Console** in your applications
menu.

## Step 2: Check you have Python

Type this exactly and press **Enter**:

```
python3 --version
```

**If it prints something like `Python 3.13.1`** - you are done with this step.
Skip to Step 3. The numbers do not matter.

**If it says "command not found"**, you need to install it. Type whichever of
these matches your system. If you are not sure which, try them in order - the
wrong one will just say it does not recognise the command.

**Ubuntu, Linux Mint, Debian, Pop!_OS, Raspberry Pi:**
```
sudo apt update && sudo apt install python3
```

**Fedora, Red Hat, CentOS, Rocky:**
```
sudo dnf install python3
```

**Arch, Manjaro, EndeavourOS:**
```
sudo pacman -S python
```

**openSUSE:**
```
sudo zypper install python3
```

It will ask for your password. **Nothing will appear as you type it** - no dots,
no stars, nothing at all. That is normal and deliberate. Type it and press
Enter.

Then check again with `python3 --version`.

## Step 3: Make a folder

Type these two lines, pressing Enter after each:

```
mkdir -p ~/ao3tool
cd ~/ao3tool
```

The first makes a folder called `ao3tool` in your home area. The second moves
you into it.

## Step 4: Put the program in the folder

Save the file **ao3_wayback.py** into that `ao3tool` folder. You can drag it
there in your file manager.

If your browser put it in Downloads, this moves it:

```
mv ~/Downloads/ao3_wayback.py ~/ao3tool/
```

Check it arrived:

```
ls ~/ao3tool
```

You should see `ao3_wayback.py` listed.

**That is the setup finished.** No tick boxes, no certificate fiddling. Linux
makes this part easy.

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

## Step 2: Get into your folder

Open a terminal and type:

```
cd ~/ao3tool
```

Most file managers also let you right-click inside a folder and choose **Open in
Terminal**, which does the same thing.

## Step 3: Type the command

Type this, but put your own address between the quote marks:

```
python3 ./ao3_wayback.py --tag-url "PUT YOUR ADDRESS HERE" --include-chapters --verbose
```

**To paste into most Linux terminals**, hold **Ctrl** and **Shift** and press
**V**. The usual Ctrl+V often does not work. Clicking the middle mouse button
also pastes.

**Keep the quote marks.** AO3 addresses contain spaces and a `|` symbol, and
that symbol means something special to the terminal. Without quotes your command
will behave very strangely.

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

Inside it, open the file ending in **_works.csv**. It opens in LibreOffice Calc.

From the terminal, this opens it for you:

```
xdg-open ~/ao3tool/ao3_wayback_out/*_works.csv
```

Each row is a story. Look at the **read_url** column - that is a link, and
clicking it opens the story in your web browser.

**SPREADSHEET_CHEATSHEET.md explains the rest of the columns.**

---

# Part 3: Leaving it running

Because a big search takes hours, you may not want to sit with a terminal window
open - and if you are connected to another machine remotely, closing the window
stops the search.

This starts it in the background and writes everything to a file. Note the
`--project` part, which is needed here:

```
cd ~/ao3tool
nohup python3 ./ao3_wayback.py --tag-url "YOUR ADDRESS" --project myfics --include-chapters --verbose > run.log 2>&1 &
```

To watch how it is getting on:

```
tail -f ~/ao3tool/run.log
```

Press Ctrl and C to stop watching. That does **not** stop the search itself.

To actually stop the search:

```
pkill -f ao3_wayback.py
```

---

# Part 4: TROUBLESHOOTING - When something goes wrong

## "python3: command not found"

Python is not installed. See Part 1, Step 2.

## "python: command not found"

You typed `python`. On most Linux systems it needs to be `python3`.

## "No such file or directory"

You are in the wrong folder, or the file is not there. Try:

```
cd ~/ao3tool
ls
```

If `ao3_wayback.py` is not in that list, it did not get saved there. See Part 1,
Step 4.

## "Permission denied"

Put `python3` in front of the command, as this guide does. Or make the file
runnable once:

```
chmod +x ~/ao3tool/ao3_wayback.py
```

## Lots of red text saying HTTP 503

Perfectly normal on a big tag. It slows itself down and keeps going.

If it carries on and nothing is getting through, the archive has temporarily
stopped answering you. **Stop it (Ctrl and C) and come back in a few hours.**
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

## I want to start completely fresh

Add `--clean` to the end of your command. It throws the old results away first.

## The spreadsheet has far fewer stories than the tag does

That is expected. Only some stories were ever saved. A tag with 300 stories
turning up 70 is a normal result, not a failure.

## The spreadsheet looks odd when I read it with a script

The files start with a hidden marker so they open correctly in Excel. If you are
reading them with Python, use `encoding="utf-8-sig"`. Or strip it:

```
sed -i '1s/^\xEF\xBB\xBF//' *_works.csv
```

---

# Part 5: The commands, all together

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
