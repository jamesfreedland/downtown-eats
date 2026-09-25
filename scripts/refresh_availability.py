#!/usr/bin/env python3
"""Refresh tonight's table availability for every bookable spot in data/restaurants.js.

Queries Resy's public widget API (and best-effort OpenTable) for a party of 2
today, and writes data/availability.js for the dashboard to read.

Polite by design: venue IDs are cached in data/.resy_ids.json so repeat runs make
one request per venue, requests are spaced ~1s apart, and a venue that errors
keeps its value from the previous run (stale beats empty).

Usage: python3 scripts/refresh_availability.py [--party 2] [--days 1]
No dependencies beyond the standard library.
"""
import json, re, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import date, timedelta, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ID_CACHE = ROOT / "data" / ".resy_ids.json"
RESY_KEY = "VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"  # Resy's public widget API key
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

def fetch(url, headers=None, timeout=15, retries=1):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < retries:
                time.sleep(8)  # back off once if throttled
                continue
            raise

def load_restaurants():
    raw = (ROOT / "data" / "restaurants.js").read_text()
    m = re.search(r"window\.RESTAURANTS\s*=\s*(\[.*\]);?\s*$", raw, re.S)
    return json.loads(m.group(1))

def load_previous():
    try:
        raw = (ROOT / "data" / "availability.js").read_text()
        m = re.search(r"window\.AVAILABILITY\s*=\s*(\{.*\});?\s*$", raw, re.S)
        return json.loads(m.group(1)) if m else None
    except Exception:
        return None

# ---------------- Resy ----------------
def load_id_cache():
    try:
        return json.loads(ID_CACHE.read_text())
    except Exception:
        return {}

_resy_ids = load_id_cache()

def resy_venue_id(slug):
    if slug in _resy_ids:
        return _resy_ids[slug]
    url = ("https://api.resy.com/3/venue?" +
           urllib.parse.urlencode({"url_slug": slug, "location": "new-york-ny"}))
    body = fetch(url, {"Authorization": f'ResyAPI api_key="{RESY_KEY}"',
                       "Accept": "application/json",
                       "X-Origin": "https://resy.com"})
    vid = json.loads(body).get("id", {}).get("resy")
    if vid:
        _resy_ids[slug] = vid
        ID_CACHE.write_text(json.dumps(_resy_ids, indent=1))
    time.sleep(1.0)
    return vid

def resy_slots(slug, day, party):
    vid = resy_venue_id(slug)
    if not vid:
        return None
    url = ("https://api.resy.com/4/find?" + urllib.parse.urlencode({
        "lat": "0", "long": "0", "day": day, "party_size": party, "venue_id": vid}))
    body = fetch(url, {"Authorization": f'ResyAPI api_key="{RESY_KEY}"',
                       "Accept": "application/json",
                       "X-Origin": "https://resy.com"})
    venues = json.loads(body).get("results", {}).get("venues", [])
    if not venues:
        return []
    times = []
    for s in venues[0].get("slots", []):
        start = s.get("date", {}).get("start", "")  # "2026-07-19 19:30:00"
        if " " in start:
            times.append(start.split(" ")[1][:5])
    return sorted(set(times))

# ---------------- OpenTable (best effort) ----------------
def opentable_rid(url):
    if url in _resy_ids:  # shared cache file, keyed by full URL for OT
        return _resy_ids[url]
    rid = None
    m = re.search(r"[?&]rid=(\d+)", url)
    if m:
        rid = m.group(1)
    else:
        try:
            page = fetch(url, retries=0)
            m = (re.search(r'"restaurantId"\s*:\s*(\d+)', page) or
                 re.search(r'"rid"\s*:\s*(\d+)', page))
            if m:
                rid = m.group(1)
        except Exception:
            pass
    if rid:
        _resy_ids[url] = rid
        ID_CACHE.write_text(json.dumps(_resy_ids, indent=1))
    return rid

def opentable_slots(url, day, party):
    rid = opentable_rid(url)
    if not rid:
        return None
    api = ("https://www.opentable.com/restref/api/availability?" +
           urllib.parse.urlencode({
               "rid": rid, "partysize": party, "datetime": f"{day}T19:00",
               "enableFutureAvailability": "false"}))
    try:
        data = json.loads(fetch(api, {"Accept": "application/json"}, retries=0))
    except Exception:
        return None
    times = []
    for t in (data.get("availability", {}) or {}).get("timeSlots", []) or []:
        dt = t.get("dateTime") or t.get("time") or ""
        m = re.search(r"T(\d{2}:\d{2})", dt) or re.match(r"^(\d{2}:\d{2})", dt)
        if m:
            times.append(m.group(1))
    return sorted(set(times))

# ---------------- SevenRooms ----------------
def sevenrooms_slots(url, day, party):
    m = re.search(r"/explore/([^/]+)/", url)
    if not m:
        return None
    api = ("https://www.sevenrooms.com/api-yoa/availability/widget/range?" +
           urllib.parse.urlencode({
               "venue": m.group(1), "time_slot": "19:00", "party_size": party,
               "start_date": day, "num_days": 1, "channel": "SEVENROOMS_WIDGET"}))
    data = json.loads(fetch(api))
    shifts = (data.get("data", {}).get("availability", {}) or {}).get(day, [])
    times = []
    for sh in shifts:
        for t in sh.get("times", []):
            if t.get("type") == "book" and t.get("time_iso"):
                times.append(t["time_iso"].split(" ")[1][:5])
    return sorted(set(times))

# ---------------- main ----------------
def main():
    party = 2
    ndays = 3
    args = sys.argv[1:]
    if "--party" in args:
        party = int(args[args.index("--party") + 1])
    if "--days" in args:
        ndays = int(args[args.index("--days") + 1])

    restaurants = load_restaurants()
    prev = load_previous() or {}
    prev_days = prev.get("days", {})

    days = {}
    errors = 0
    for offset in range(ndays):
        day = (date.today() + timedelta(days=offset)).isoformat()
        out = {}
        # venues with no data yet go first, so rate-limited runs fill gaps
        ordered = sorted(restaurants, key=lambda r: r["name"] in prev_days.get(day, {}))
        for r in ordered:
            name, plat = r["name"], r.get("platform")
            if not ((plat == "resy" and r.get("resy_slug")) or
                    (plat in ("opentable", "sevenrooms") and r.get("book_url"))):
                continue  # walk-in / other: skip
            slots = None
            try:
                if plat == "resy":
                    slots = resy_slots(r["resy_slug"], day, party)
                elif plat == "sevenrooms":
                    slots = sevenrooms_slots(r["book_url"], day, party)
                else:
                    slots = opentable_slots(r["book_url"], day, party)
            except urllib.error.HTTPError as e:
                print(f"  ! {name}: HTTP {e.code}", file=sys.stderr)
            except Exception as e:
                print(f"  ! {name}: {e}", file=sys.stderr)
            if slots is None:
                # keep the previous run's value rather than dropping the venue
                if day in prev_days and name in prev_days[day]:
                    out[name] = prev_days[day][name]
                errors += 1
            else:
                out[name] = slots
                print(f"  {name}: {len(slots)} slot(s)")
            time.sleep(1.0)
        days[day] = out

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "party_size": party,
        "days": days,
    }
    dest = ROOT / "data" / "availability.js"
    dest.write_text("window.AVAILABILITY = " + json.dumps(payload, ensure_ascii=False, indent=1) + ";\n")
    checked = sum(len(v) for v in days.values())
    print(f"Wrote {dest} — {checked} venues, {errors} error(s), party of {party}.")

if __name__ == "__main__":
    main()
