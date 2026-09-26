"""Nightly pre-warm for the BellaZu server (cron, as the app user). Fills the on-disk caches the app reads, so the
first tap of the day on a town is fast.

  RapidAPI   : home lists (for sale) and rental lists (for rent; these also feed the rent estimates) for the first-home towns
               + saved-homes towns, oldest cache first, so the towns rotate. Budget follows the plan RapidAPI itself reports
               (x-ratelimit-requests-limit, stored by bellazu/listings.py):
                 free (500/mo) : at most 5 searches a night, never past 350 in the month (the app cap is 450);
                                 sale lists refreshed when older than 18 h, rent lists when older than 72 h.
                 Pro (10,000)  : up to 80 searches a night, never past 70% of the plan (7,000); every list refreshed nightly
                                 (older than 20 h), i.e. about 35-50 searches a night, ~1,500 a month.
               --rapid N / --ceiling N override. A list can cost 2 searches (city search finds <25 -> one more by ZIP), so a list
               is only tried if 2 fit (1 if last time the city search alone found 25+).
  free part  : every first-home town + every town in the saved-homes list -> town check (Craigslist, realtor.com rent list
               from the cache just filled, Redfin, Inside Airbnb, HUD, rates). Never makes a RapidAPI call. Rent.com is skipped
               on the server (robot check).
  RentCast   : never.

  galleries  : Pro only (--galleries auto = 120 a night): photo sets for the first 8 cards of each town's feed, homes listed in
               the last 2 days and the saved homes, so swiping a card's photos is instant (7-day cache).

usage: python tools/prewarm.py [--rapid auto|N] [--ceiling auto|N] [--galleries auto|N] [--free-only] [--towns A,B] [--dry-run]
Log: one line per step on stdout (cron appends it to /var/log/bellazu/prewarm.log)."""
import argparse, json, os, pathlib, sys, time, tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


SAVED_IDS = []                 # realtor.com ids of the saved homes (their galleries are pre-fetched on Pro)


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def load_secrets():
    """Same secrets file the app reads (~/.streamlit/secrets.toml of the app user). Values go into this process only."""
    for p in (pathlib.Path.home() / ".streamlit" / "secrets.toml", ROOT / ".streamlit" / "secrets.toml"):
        if p.exists():
            with open(p, "rb") as f:
                return {k: str(v) for k, v in tomllib.load(f).items()}
    return {}


def saved_towns(sec):
    """Towns of the homes in the saved list (read-only copy of the online list; never written from here)."""
    from bellazu import saves
    os.environ["BELLAZU_SAVES_DIR"] = os.environ.get("BELLAZU_PREWARM_SAVES_DIR", "/var/lib/bellazu/saves-prewarm.git")
    k, pc = sec.get("BELLAZU_SAVES_DEPLOY_KEY"), sec.get("APP_PASSCODE", "").strip().lower()
    if not (k and pc):
        return [], "no key"
    saves.set_key(k)
    lst, err = saves.cloud_get(pc)
    if err or not lst:
        return [], err or "empty"
    its = (lst.get("items") or {}).values()
    SAVED_IDS[:] = [str(it.get("listing_id")) for it in its if it.get("listing_id")]
    return sorted({(it.get("town") or "").strip() for it in its if (it.get("town") or "").strip()}), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapid", default="auto", help="max RapidAPI searches tonight (auto: 5 free, 80 Pro)")
    ap.add_argument("--ceiling", default="auto", help="never let the month's RapidAPI count pass this (auto: 350 free, 70%% of the plan on Pro)")
    ap.add_argument("--galleries", default="auto", help="max photo galleries (detail calls) tonight (auto: 0 free, 120 Pro)")
    ap.add_argument("--free-only", action="store_true")
    ap.add_argument("--towns", default="", help="only these towns (comma list), for tests")
    ap.add_argument("--dry-run", action="store_true", help="list what would be done")
    a = ap.parse_args()
    sec = load_secrets()
    for k in ("RAPIDAPI_KEY",):
        if sec.get(k) and not os.environ.get(k):
            os.environ[k] = sec[k]
    os.environ["RENTCAST_API_KEY"] = ""                       # pre-warm never uses RentCast
    from bellazu import core, listings, towns
    from bellazu import compare as C
    pro = listings.pro()
    a.rapid = (80 if pro else 5) if str(a.rapid) == "auto" else int(a.rapid)
    a.ceiling = (int(listings.plan() * 0.7) if pro else 350) if str(a.ceiling) == "auto" else int(a.ceiling)
    a.galleries = (120 if pro else 0) if str(a.galleries) == "auto" else int(a.galleries)
    t0 = time.time()
    if a.towns:
        todo = [t.strip() for t in a.towns.split(",") if t.strip()]
        st_towns = []
    else:
        first = list(C.mode_towns("first"))
        st_towns, err = saved_towns(sec)
        if err:
            log("saved list:", err)
        known = {n.lower(): n for n, _ in towns.supported()}
        st_towns = [known[t.lower()] for t in st_towns if t.lower() in known]
        todo = list(dict.fromkeys(first + st_towns))
    log(f"start: {len(todo)} towns ({len(st_towns)} from saved homes); plan {listings.plan()}/mo ({'Pro' if pro else 'free'}), "
        f"rapid budget {0 if a.free_only else a.rapid}, ceiling {a.ceiling}")
    if a.dry_run:
        log("towns:", ", ".join(todo))
    # 1) RapidAPI lists (sale + rent), within budget, oldest cache first (rotates through the towns night after night)
    spent = 0
    if not a.free_only and listings.available():
        def age(job):
            p = listings._cpath(f"{job[0]}_{job[1]}_0_v2")
            return p.stat().st_mtime if p.exists() else 0

        def stale(job):
            h = listings.age_h(job[0], job[1])
            return h is None or h > (20 if pro else listings.ttl_h(job[1]))
        u0 = listings.usage()
        log(f"rapidapi: {u0['used']} of {u0['cap']} used this month (resets {u0.get('resets')})")
        jobs = sorted([(t, st) for t in todo for st in ("for_sale", "for_rent")], key=age)
        for t, status in jobs:
            if not stale((t, status)):
                continue
            u = listings.usage()
            need = 2                                            # a small town can cost 2 (city search + ZIP search)
            try:
                if len(json.loads(listings._cpath(f"{t}_{status}_0_v2").read_text()).get("rows") or []) >= 25:
                    need = 1                                    # last time the city search alone found plenty
            except Exception:
                pass
            if spent + need > a.rapid or u["used"] + need > a.ceiling or u["left"] < need:
                if spent >= a.rapid or u["used"] + 1 > a.ceiling or u["left"] < 1:
                    log(f"rapidapi: stop (spent {spent} tonight, {u['used']} used this month, ceiling {a.ceiling})")
                    break
                continue                                        # this one might need 2; a cheaper list may still fit
            if a.dry_run:
                log(f"rapidapi: would fetch {t} {status}"); spent += need; continue
            before = u["used"]
            r = listings.fetch_town(t, status, zip_code=(C.town_info(t) or {}).get("zip"), force=True)
            used = listings.usage()["used"] - before
            spent += max(used, 1 if r.get("ok") else 0)
            what = "homes" if status == "for_sale" else "rentals"
            log(f"rapidapi: {t} {status} {'ok ' + str(len(r.get('rows') or [])) + ' ' + what if r.get('ok') else 'FAILED ' + str(r.get('error'))} ({used} search{'es' if used != 1 else ''})")
        log(f"rapidapi: {spent} searches tonight, {listings.usage()['used']} used this month")
        # photo galleries (Pro only): the cards the feed shows first (under $500K, newest 8 per town), homes listed in the last
        # 2 days, and the saved homes; each is one detail call cached 7 days, so a home is fetched about once a week at most
        if a.galleries > 0:
            want = list(SAVED_IDS)
            for t in todo:
                rows = (listings.read_cache(t, "for_sale") or {}).get("rows") or []
                rows = sorted(listings.filter_rows(rows, None, 500_000), key=lambda r: (r.get("days") is None, r.get("days") or 0))
                want += [r["id"] for r in rows[:8]] + [r["id"] for r in rows if (r.get("days") if r.get("days") is not None else 99) <= 2]
            want = [x for x in dict.fromkeys(str(w) for w in want if w) if listings.detail_cached(x) is None]
            got = 0
            for pid in want[:a.galleries]:
                u = listings.usage()
                if u["used"] + 1 > a.ceiling or u["left"] < 1:
                    log(f"galleries: stop at the ceiling ({u['used']} used)"); break
                if a.dry_run:
                    got += 1; continue
                got += bool(listings.detail(pid).get("ok"))
            log(f"galleries: {got} of {len(want)} wanted fetched (limit {a.galleries}), {listings.usage()['used']} used this month")
    elif not a.free_only:
        log("rapidapi: no key, skipped")
    # 2) free: town checks (fills the Craigslist / Redfin / Inside Airbnb disk caches, 12 h+; reads the rent lists, never calls RapidAPI)
    ok = bad = 0
    for t in todo:
        if a.dry_run:
            break
        s = time.time()
        try:
            r = core.town_snapshot(t, {"use_rentcast": False, "allow_rent_call": False})
            fails = [x["source"] for x in r.get("sources_status") or [] if not x.get("ok")]
            ok += bool(r.get("ok")); bad += not r.get("ok")
            log(f"town {t}: {'ok' if r.get('ok') else 'FAILED ' + str(r.get('error'))} {time.time() - s:.1f}s" + (f" (no answer: {', '.join(fails)})" if fails else ""))
        except Exception as e:
            bad += 1
            log(f"town {t}: ERROR {e.__class__.__name__}: {e}")
    log(f"done in {time.time() - t0:.0f}s: {ok} town checks ok, {bad} failed, {spent} RapidAPI searches")


if __name__ == "__main__":
    main()
