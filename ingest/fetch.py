"""Download one GitHub tarball and read docs/*.md in memory (nothing is written to disk)."""
import io
import tarfile

import httpx


def _docs_from_tarball(data: bytes, docs_path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    prefix = docs_path.strip("/") + "/"
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf:
            if not member.isfile():
                continue
            parts = member.name.split("/", 1)
            if len(parts) != 2 or not parts[1].startswith(prefix):
                continue
            name = parts[1][len(prefix):]
            if "/" in name or not name.endswith(".md"):
                continue
            f = tf.extractfile(member)
            if f is not None:
                out[name] = f.read().decode("utf-8", errors="replace")
    return out


def fetch_docs(repo: str, ref: str, docs_path: str,
               client: httpx.Client | None = None, max_bytes: int = 400_000_000) -> dict[str, str]:
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=180)
    try:
        r = client.get(f"https://codeload.github.com/{repo}/tar.gz/{ref}")
        r.raise_for_status()
        if len(r.content) > max_bytes:
            raise ValueError(f"tarball too large: {len(r.content)} bytes")
        return _docs_from_tarball(r.content, docs_path)
    finally:
        if own:
            client.close()
