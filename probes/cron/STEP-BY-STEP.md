# Running the probe: step by step

For Rich. Nothing here can break `railcrossing.uk` — the probe only *reads* from the rail
API. It never writes anything, never touches the level-crossing service, and never restarts
anything. The worst it can do is fail and tell you so.

You will be typing into a black terminal window. That is normal and fine.

---

## Before you start

You need the command you normally use to connect to the Oracle server — the same one you use
when working on `rail-crossing`. Something like `ssh ubuntu@130.162.167.237`, possibly with
a `-i` and a key file.

That's it. Everything else is already on the server.

---

## Part 1 — Get onto the server

Open Terminal on your machine and connect the way you normally do.

You know it worked when the prompt changes to something like `ubuntu@rail-crossing:~$`.

**Sanity check** — copy and paste this, press Enter:

```sh
ls ~/rail-crossing/backend/.env
```

You want it to print the path back at you. If it says "No such file or directory", stop —
the key isn't where I think it is, and nothing below will work. Tell me what `ls ~` shows.

---

## Part 2 — Put the probe on the server

Three commands. Paste one at a time.

```sh
cd ~
git clone https://github.com/richbroad29/train-loader.git
```

If it complains that the folder already exists, you've cloned it before — update it instead:

```sh
cd ~/train-loader && git pull
```

Then make sure the script is runnable:

```sh
chmod +x ~/train-loader/probes/cron/run-probe.sh
```

Nothing visible happens. That's correct.

---

## Part 3 — The test run (do this tonight)

**This is the important step, and you do not need to wait for the morning.**

```sh
~/train-loader/probes/cron/run-probe.sh once
```

It takes a few seconds. You should see, roughly in this order:

```
=== once run, started ...
key loaded (36 chars, not printed)
[20260916T213000] sample 1/1: 24 services so far, 12 with per-coach loading
```

...then a report, then a line starting `OK`.

**The number that matters is the second one on that sample line** — "N with per-coach
loading". If that number is above zero, the data exists and this project is alive. If it's
zero, it doesn't, and we've saved ourselves weeks.

A single evening run can't tell us how often 8-car trains run, or what the peak looks like.
But it answers the big question tonight rather than tomorrow.

### If the last line says FAIL

Don't try to fix it. Copy the whole output and send it to me. The three likely causes are a
wrong path, a key the subscription doesn't cover, or no `python3` — all quick to sort, and
all of them look the same from the outside, which is why I'd rather read the actual text.

---

## Part 4 — Send me the result

```sh
cat ~/probe-runs/once-*/ldbsv-coverage-*.md
```

Copy everything it prints and paste it into our chat. That's the whole handover — it's a
short markdown report, and it settles four open questions at once.

---

## Part 5 — The schedule (only if you want repeat runs)

Skip this for now if you like. One morning run by hand tells us most of what we need; the
schedule earns its place if you want several days, which is the only way to learn how often
8-car trains turn up.

**Do not use `crontab -e`** unless you're comfortable in a terminal editor — it can drop you
into `vim`, which is genuinely hard to get out of. Paste this instead. It adds the schedule
without opening any editor:

```sh
(crontab -l 2>/dev/null; cat <<'CRON'
CRON_TZ=Europe/London
0  7 * * 1-5 /usr/bin/flock -n /tmp/probe.lock /home/ubuntu/train-loader/probes/cron/run-probe.sh morning
15 16 * * 1-5 /usr/bin/flock -n /tmp/probe.lock /home/ubuntu/train-loader/probes/cron/run-probe.sh evening
CRON
) | crontab -
```

If your username on the server isn't `ubuntu`, change both `/home/ubuntu/` paths to match
(run `echo $HOME` to see).

Check it took:

```sh
crontab -l
```

You should see your lines. From then on it runs at 07:00 and 16:15 on weekdays, London time,
and samples for two hours each time.

**To check on it later:**

```sh
cat ~/probe-runs/last-run.txt
```

One line: `OK` or `FAIL`, with a path to the log.

**To stop it:**

```sh
crontab -r
```

That removes *all* your scheduled jobs. If you have others on that box, edit instead of
removing — ask me and I'll write the exact command.

---

## If you get stuck

Copy the text on screen and send it. Every failure mode here prints something specific, and
guessing from a description wastes both our time.
