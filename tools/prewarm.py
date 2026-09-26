"""Nightly pre-warm for the BellaZu server (cron, as the app user). Fills the on-disk caches the app reads, so the
first tap of the day on a town is fast.

  free part  : every first-home town + every town in the saved-homes list -> town check (Craigslist, Rent.com, Redfin,
               Inside Airbnb, HUD, rates). Costs nothing.
  RapidAPI   : home lists (for sale) for at most --rapid towns per night (default 5 searches), oldest cache first, so the
               towns rotate. Never lets the month's count pass --ceiling (default 350 of the 450 cap), leaving room for browsing.
               A town can cost 2 searches (city search finds <25 homes -> one more by ZIP), so a town is only tried if 2 fit.
  RentCast   : never.

usage: python tools/prewarm.py [--rapid 5] [--ceiling 350] [--free-only] [--towns A,B] [--dry-run]
Log: one line per step on stdout (cron appends it to /var/log/bellazu/prewarm.log)."""
import argparse, json, os, pathlib, sys, time, tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


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
    return sorted({(it.get("town") or "").strip() for it in (lst.get("items") or {}).values() if (it.get("town") or "").strip()}), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapid", type=int, default=5, help="max RapidAPI searches tonight")
    ap.add_argument("--ceiling", type=int, default=350, help="never let the month's RapidAPI count pass this")
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
    log(f"start: {len(todo)} towns ({len(st_towns)} from saved homes); rapid budget {0 if a.free_only else a.rapid}, ceiling {a.ceiling}")
    if a.dry_run:
        log("towns:", ", ".join(todo))
    # 1) free: town checks (fills the Craigslist / Rent.com / Redfin / Inside Airbnb disk caches, 12 h+)
    ok = bad = 0
    for t in todo:
        if a.dry_run:
            break
        s = time.time()
        try:
            r = core.town_snapshot(t, {"use_rentcast": False})
            fails = [x["source"] for x in r.get("sources_status") or [] if not x.get("ok")]
            ok += bool(r.get("ok")); bad += not r.get("ok")
            log(f"town {t}: {'ok' if r.get('ok') else 'FAILED ' + str(r.get('error'))} {time.time() - s:.1f}s" + (f" (no answer: {', '.join(fails)})" if fails else ""))
        except Exception as e:
            bad += 1
            log(f"town {t}: ERROR {e.__class__.__name__}: {e}")
    # 2) RapidAPI home lists, within budget, oldest cache first (rotates through the towns night after night)
    spent = 0
    if not a.free_only and listings.available():
        def age(t):
            p = listings._cpath(f"{t}_for_sale_0_v2")
            return p.stat().st_mtime if p.exists() else 0
        u0 = listings.usage()
        log(f"rapidapi: {u0['used']} of {u0['cap']} used this month (resets {u0.get('resets')})")
        for t in sorted(todo, key=age):
            if listings.cached(t, "for_sale"):
                continue
            u = listings.usage()
            if spent + 2 > a.rapid or u["used"] + 2 > a.ceiling or u["left"] < 2:
                log(f"rapidapi: stop (spent {spent} tonight, {u['used']} used this month, ceiling {a.ceiling})")
                break
            if a.dry_run:
                log(f"rapidapi: would fetch {t}"); spent += 1; continue
            before = u["used"]
            r = listings.fetch_town(t, "for_sale", zip_code=(C.town_info(t) or {}).get("zip"))
            used = listings.usage()["used"] - before
            spent += max(used, 1 if r.get("ok") else 0)
            log(f"rapidapi: {t} {'ok ' + str(len(r.get('rows') or [])) + ' homes' if r.get('ok') else 'FAILED ' + str(r.get('error'))} ({used} search{'es' if used != 1 else ''})")
        log(f"rapidapi: {spent} searches tonight, {listings.usage()['used']} used this month")
    elif not a.free_only:
        log("rapidapi: no key, skipped")
    log(f"done in {time.time() - t0:.0f}s: {ok} town checks ok, {bad} failed, {spent} RapidAPI searches")


if __name__ == "__main__":
    main()
