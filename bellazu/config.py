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


_ASM = {}


def load_assumptions(path=None, overrides=None):
    import copy
    f = pathlib.Path(path or ROOT / "assumptions.yaml")
    k = (str(f), f.stat().st_mtime_ns)
    if k not in _ASM:                      # parse the YAML once per process (per file version); hand out copies
        with open(f) as fh:
            _ASM[k] = yaml.safe_load(fh)
    a = copy.deepcopy(_ASM[k])
    for sect, vals in (overrides or {}).items():
        a.setdefault(sect, {}).update(vals)
    return a


def by_beds(table, beds):
    beds = 0 if beds is None else int(min(max(beds, 0), max(table)))
    return table.get(beds, list(table.values())[-1])
