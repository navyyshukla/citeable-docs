"""Download one GitHub tarball and read docs/*.md in memory (nothing is written to disk)."""
import io
import tarfile
import warnings

import httpx


def _docs_from_tarball(data: bytes, docs_path: str,
                       max_member_bytes: int = 5_000_000) -> dict[str, str]:
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
            if "/" in name or not name.endswith(".md") or member.size > max_member_bytes:
                continue
            f = tf.extractfile(member)
            if f is not None:
                text = f.read().decode("utf-8-sig", errors="replace")
                if "\ufffd" in text:
                    warnings.warn(f"{name}: not valid UTF-8, some characters were replaced",
                                  stacklevel=2)
                out[name] = text
    return out


def commit_from_tarball(data: bytes) -> str | None:
    """GitHub puts the commit SHA in the tar's global header: the docs `ref` can move."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        return tf.pax_headers.get("comment") or None


def fetch_docs(repo: str, ref: str, docs_path: str,
               client: httpx.Client | None = None, max_bytes: int = 100_000_000) -> dict[str, str]:
    return fetch_docs_and_commit(repo, ref, docs_path, client, max_bytes)[0]


def fetch_docs_and_commit(repo: str, ref: str, docs_path: str, client: httpx.Client | None = None,
                          max_bytes: int = 100_000_000) -> tuple[dict[str, str], str | None]:
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=180)
    try:
        with client.stream("GET", f"https://codeload.github.com/{repo}/tar.gz/{ref}") as r:
            r.raise_for_status()
            declared = r.headers.get("content-length")
            if declared and int(declared) > max_bytes:
                raise ValueError(f"tarball too large: {declared} bytes")
            data = bytearray()
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > max_bytes:
                    raise ValueError(f"tarball too large: over {max_bytes} bytes")
        files = _docs_from_tarball(bytes(data), docs_path)
        if not files:
            raise ValueError(f"no markdown files found under {docs_path!r} in {repo}@{ref}")
        return files, commit_from_tarball(bytes(data))
    finally:
        if own:
            client.close()
