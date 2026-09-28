#!/usr/bin/env python3
"""Table watcher: checks watched venues for newly open slots and sends a Telegram DM.

Watches live in data/watches.json (gitignored - this repo is public):
  [{"venue": "Rezdôra", "party": 2, "days": ["2026-09-27"], "from": "18:30", "to": "21:00"}]
"days" may also be "next3" / "next7" for a rolling horizon. Each (venue, date, party,
slot) alerts only once, tracked in data/.watch_state.json. Runs quietly: no matching
watches or no new slots means no message. Designed for launchd every ~20 min; zero
Claude tokens. Credentials: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in .env (gitignored).
"""
import json, re, sys, urllib.request
from datetime import date, timedelta, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "scripts"))
import refresh_availability as ra

WATCHES = ROOT / "data" / "watches.json"
STATE = ROOT / "data" / ".watch_state.json"

def load_env():
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text,
                          "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()

def fmt12(t):
    h, m = map(int, t.split(":"))
    return f"{(h % 12) or 12}:{m:02d}{'pm' if h >= 12 else 'am'}"

def resolve_days(spec):
    if isinstance(spec, list):
        return [d for d in spec if d >= date.today().isoformat()]
    n = int(re.sub(r"\D", "", str(spec)) or 3)
    return [(date.today() + timedelta(days=i)).isoformat() for i in range(n)]

def main():
    now = datetime.now()
    if now.hour >= 23 or now.hour < 8:   # quiet hours
        return
    if not WATCHES.exists():
        return
    watches = json.loads(WATCHES.read_text())
    if not watches:
        return
    env = load_env()
    token, chat_id = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        print("missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in .env", file=sys.stderr)
        sys.exit(1)

    restaurants = {r["name"]: r for r in ra.load_restaurants()}
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    for w in watches:
        r = restaurants.get(w["venue"])
        if not r:
            print(f"  ? unknown venue: {w['venue']}", file=sys.stderr)
            continue
        party = int(w.get("party", 2))
        lo, hi = w.get("from", "17:00"), w.get("to", "22:00")
        for day in resolve_days(w.get("days", "next3")):
            try:
                if r.get("platform") == "resy" and r.get("resy_slug"):
                    slots = ra.resy_slots(r["resy_slug"], day, party)
                elif r.get("platform") == "sevenrooms" and r.get("book_url"):
                    slots = ra.sevenrooms_slots(r["book_url"], day, party)
                else:
                    continue  # opentable/walk-in: can't be watched
            except Exception as e:
                print(f"  ! {w['venue']} {day}: {e}", file=sys.stderr)
                continue
            hits = [t for t in (slots or []) if lo <= t <= hi]
            new = [t for t in hits
                   if f"{w['venue']}|{day}|{party}|{t}" not in state]
            if new:
                nice = datetime.strptime(day, "%Y-%m-%d").strftime("%a %b %-d")
                url = r.get("book_url", "")
                if r.get("platform") == "resy" and "resy.com" in url:
                    url += f"{'&' if '?' in url else '?'}date={day}&seats={party}"
                msg = (f"🍽 Table open: {w['venue']} — {nice}, party of {party}\n"
                       f"{', '.join(fmt12(t) for t in new[:8])}\n{url}")
                send_telegram(token, chat_id, msg)
                print(f"  alerted: {w['venue']} {day} {new}")
                for t in new:
                    state[f"{w['venue']}|{day}|{party}|{t}"] = now.isoformat()
    STATE.write_text(json.dumps(state, indent=1))

if __name__ == "__main__":
    main()
