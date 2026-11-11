"""Tiny dependency-free secret box for ONE short API key, unlocked by the app passcode.
Scheme (v1): scrypt(passcode, salt, n=2**16, r=8, p=1) -> 64 bytes = 32-byte stream key + 32-byte MAC key.
Ciphertext = plaintext XOR SHA-256(stream_key || counter) blocks; tag = HMAC-SHA256(mac_key, header || salt || ciphertext).
The lock file stores only salt, ciphertext and tag (hex). A wrong passcode fails the tag check and returns None."""
import hashlib, hmac, json, os

VERSION = 1
N, R, P = 2 ** 16, 8, 1
_HDR = b"bellazu-keylock-v1"


def _norm(passcode):
    return (passcode or "").strip().lower().encode()


def _keys(passcode, salt, n=N, r=R, p=P):
    k = hashlib.scrypt(_norm(passcode), salt=salt, n=n, r=r, p=p, maxmem=256 * 1024 * 1024, dklen=64)
    return k[:32], k[32:]


def _stream(key, length):
    out = bytearray(length)
    i = off = 0
    while off < length:
        block = hashlib.sha256(key + i.to_bytes(8, "big")).digest()
        n = min(32, length - off)
        out[off:off + n] = block[:n]
        off += n
        i += 1
    return out


def _xor(a, b):
    n = len(a)
    out = bytearray(n)
    mv_a, mv_b = memoryview(a), memoryview(b)
    step = 8192
    for i in range(0, n, step):
        j = min(i + step, n)
        x = int.from_bytes(mv_a[i:j], "big") ^ int.from_bytes(mv_b[i:j], "big")
        out[i:j] = x.to_bytes(j - i, "big")
    return out


def lock(secret, passcode):
    blob = lock_bytes(secret.encode(), passcode)
    return {"v": blob["v"], "kdf": blob["kdf"], "n": blob["n"], "r": blob["r"], "p": blob["p"],
            "salt": blob["salt"].hex(), "ct": blob["ct"].hex(), "tag": blob["tag"].hex()}


def lock_bytes(secret, passcode):
    """Same scheme as lock(), but for raw bytes. Returns salt/ct/tag as bytes (not hex)."""
    salt = os.urandom(16)
    ek, mk = _keys(passcode, salt)
    pt = bytes(secret)
    ct = bytes(_xor(pt, _stream(ek, len(pt))))
    tag = hmac.new(mk, _HDR + salt + ct, hashlib.sha256).digest()
    return {"v": VERSION, "kdf": "scrypt", "n": N, "r": R, "p": P, "salt": salt, "ct": ct, "tag": tag}


def unlock(blob, passcode):
    """blob: dict (or JSON text / path). Returns the secret string, or None if the passcode is wrong or the blob is bad."""
    try:
        if isinstance(blob, (str, os.PathLike)) and os.path.exists(str(blob)):
            blob = open(blob, encoding="utf-8").read()
        if isinstance(blob, str):
            blob = json.loads(blob)
        if not passcode or blob.get("v") != VERSION or blob.get("kdf") != "scrypt":
            return None
        salt, ct, tag = bytes.fromhex(blob["salt"]), bytes.fromhex(blob["ct"]), bytes.fromhex(blob["tag"])
        ek, mk = _keys(passcode, salt, int(blob["n"]), int(blob["r"]), int(blob["p"]))
        if not hmac.compare_digest(hmac.new(mk, _HDR + salt + ct, hashlib.sha256).digest(), tag):
            return None
        return bytes(a ^ b for a, b in zip(ct, _stream(ek, len(ct)))).decode()
    except Exception:
        return None


def unlock_bytes(blob, passcode):
    """Like unlock(), but returns raw bytes (or None). blob: dict with bytes or hex salt/ct/tag, or a JSON/hex lock path."""
    try:
        if isinstance(blob, (str, os.PathLike)) and os.path.exists(str(blob)):
            raw = open(blob, "rb").read()
            if raw.startswith(BIN_MAGIC):
                blob = read_bin(raw)
            else:
                blob = json.loads(raw.decode())
        if isinstance(blob, str):
            blob = json.loads(blob)
        if not passcode or blob.get("v") != VERSION or blob.get("kdf") != "scrypt":
            return None
        def _b(x):
            return x if isinstance(x, (bytes, bytearray)) else bytes.fromhex(x)
        salt, ct, tag = _b(blob["salt"]), _b(blob["ct"]), _b(blob["tag"])
        ek, mk = _keys(passcode, salt, int(blob["n"]), int(blob["r"]), int(blob["p"]))
        if not hmac.compare_digest(hmac.new(mk, _HDR + salt + ct, hashlib.sha256).digest(), tag):
            return None
        return bytes(_xor(ct, _stream(ek, len(ct))))
    except Exception:
        return None


# Binary lock file: magic + NUL (so privacy greps treat it as binary) + 4-byte header length + JSON header + raw ciphertext.
# Same crypto as the JSON/hex locks; used for large blobs (study podcasts) that must not be hex-expanded into the public repo.
BIN_MAGIC = b"BZPOD1\n\x00"


def write_bin(path, secret, passcode, meta=None):
    """Encrypt secret and write a BZPOD1 lock file. Returns header metadata (no ciphertext)."""
    blob = lock_bytes(secret, passcode)
    header = {
        "v": blob["v"], "kdf": blob["kdf"], "n": blob["n"], "r": blob["r"], "p": blob["p"],
        "salt": blob["salt"].hex(), "tag": blob["tag"].hex(), "ct_len": len(blob["ct"]),
    }
    if meta:
        header["meta"] = meta
    h = json.dumps(header, separators=(",", ":")).encode()
    path = os.fspath(path)
    with open(path, "wb") as f:
        f.write(BIN_MAGIC)
        f.write(len(h).to_bytes(4, "big"))
        f.write(h)
        f.write(blob["ct"])
    return header


def read_bin(src):
    """Parse a BZPOD1 file (path or bytes) into a dict with bytes salt/ct/tag. Raises on a bad file."""
    raw = open(src, "rb").read() if isinstance(src, (str, os.PathLike)) else src
    if not raw.startswith(BIN_MAGIC):
        raise ValueError("not a BZPOD1 lock")
    off = len(BIN_MAGIC)
    n = int.from_bytes(raw[off:off + 4], "big")
    off += 4
    header = json.loads(raw[off:off + n].decode())
    off += n
    ct = raw[off:]
    if header.get("ct_len") is not None and len(ct) != int(header["ct_len"]):
        raise ValueError("ciphertext length mismatch")
    return {
        "v": header["v"], "kdf": header["kdf"], "n": header["n"], "r": header["r"], "p": header["p"],
        "salt": bytes.fromhex(header["salt"]), "tag": bytes.fromhex(header["tag"]), "ct": ct,
        "meta": header.get("meta") or {},
    }


def unlock_bin(path, passcode):
    """Decrypt a BZPOD1 file. Returns (plaintext bytes, meta dict), or (None, None) if the passcode is wrong or the file is bad."""
    try:
        blob = read_bin(path)
        pt = unlock_bytes(blob, passcode)
        if pt is None:
            return None, None
        return pt, dict(blob.get("meta") or {})
    except Exception:
        return None, None

