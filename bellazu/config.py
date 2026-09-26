import os, pathlib, yaml
ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_env():
    """Optional keys from ROOT/.env (KEY=VALUE lines) — never required."""
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_assumptions(path=None, overrides=None):
    a = yaml.safe_load(open(path or ROOT / "assumptions.yaml"))
    for sect, vals in (overrides or {}).items():
        a.setdefault(sect, {}).update(vals)
    return a


def by_beds(table, beds):
    beds = 0 if beds is None else int(min(max(beds, 0), max(table)))
    return table.get(beds, list(table.values())[-1])
