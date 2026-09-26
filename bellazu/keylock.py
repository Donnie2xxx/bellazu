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
    out, i = b"", 0
    while len(out) < length:
        out += hashlib.sha256(key + i.to_bytes(8, "big")).digest()
        i += 1
    return out[:length]


def lock(secret, passcode):
    salt = os.urandom(16)
    ek, mk = _keys(passcode, salt)
    pt = secret.encode()
    ct = bytes(a ^ b for a, b in zip(pt, _stream(ek, len(pt))))
    tag = hmac.new(mk, _HDR + salt + ct, hashlib.sha256).digest()
    return {"v": VERSION, "kdf": "scrypt", "n": N, "r": R, "p": P, "salt": salt.hex(), "ct": ct.hex(), "tag": tag.hex()}


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
