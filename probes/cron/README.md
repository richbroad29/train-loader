# Scheduling the probe on the VPS

The probe has to run on the Oracle box: that is where the RDM key lives and where
`api1.raildata.org.uk` is reachable. Claude Code's container is blocked from that host by
the organisation's egress policy, so nothing scheduled there can do this job.

`run-probe.sh` is the wrapper that makes it safe to run unattended. Everything in it exists
because cron gets one of three things wrong by default.

## Install

```sh
# 1. Get the repo onto the box (once)
cd ~ && git clone https://github.com/richbroad29/train-loader.git
# later: cd ~/train-loader && git pull

# 2. Check it works before trusting a schedule to it
~/train-loader/probes/cron/run-probe.sh once
cat ~/probe-runs/last-run.txt        # should say OK
```

If that says `FAIL`, fix it now — a schedule built on a broken run just fails quietly at
07:00 every day instead of once in front of you.

## The crontab

```sh
crontab -e
```

```cron
# The probe's schedule. CRON_TZ is load-bearing — see below.
CRON_TZ=Europe/London

0  7 * * 1-5  /usr/bin/flock -n /tmp/probe.lock ~/train-loader/probes/cron/run-probe.sh morning
15 16 * * 1-5 /usr/bin/flock -n /tmp/probe.lock ~/train-loader/probes/cron/run-probe.sh evening
```

Morning peak from 07:00, evening from 16:15, weekdays only. Each run samples every ten
minutes for two hours, so they finish at 09:00 and 18:15 and never overlap.

## The three traps

**1. Timezone.** Cron uses the system clock, and a cloud VPS is almost always **UTC**. Without
`CRON_TZ`, `0 7 * * 1-5` fires at 08:00 London time through British Summer Time — you would
miss the first hour of the peak — and then silently shifts to 07:00 when the clocks change in
October. `CRON_TZ=Europe/London` makes the schedule mean what it says all year. (Ubuntu's cron
supports it; `systemd` timers with `OnCalendar` handle DST too, and would be the more idiomatic
choice on a box that already runs `rail-crossing.service` under systemd. Cron is fine here.)

**2. Cron has no environment.** No `RDM_API_KEY`, no profile, a minimal `PATH`. The wrapper
sources `~/rail-crossing/backend/.env` explicitly and uses absolute paths. It never prints the
key — only its length, so you can tell it loaded.

**3. Silence looks like success.** This one bit during testing: with the API unreachable, every
request failed, the probe still exited 0, and the wrapper wrote `OK`. A cron job reporting
success while learning nothing is worse than no cron job. The probe now **exits non-zero when
no services come back at all**, and the wrapper writes `FAIL` with the log path.

## Checking on it

```sh
cat ~/probe-runs/last-run.txt              # OK or FAIL, with the log path
ls ~/probe-runs/                           # one directory per run
cat ~/probe-runs/morning-*/ldbsv-coverage-*.md | less
```

Runs and logs older than 21 days are deleted automatically (`KEEP_DAYS` to change it). Raw
payloads are kept for the first sample of each run — worth reading by eye the first time.

## One-off instead

For a single measurement you may as well watch it happen:

```sh
cd ~/rail-crossing && set -a && . backend/.env && set +a
python3 ~/train-loader/probes/ldbsv_probe.py --samples 12 --interval 600
```

Cron earns its place if you want several days of it — which, given that the 8-vs-12 formation
question is about *how often*, is worth doing.
