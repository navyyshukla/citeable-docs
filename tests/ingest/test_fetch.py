import io
import tarfile

import httpx
import pytest

from ingest.fetch import _docs_from_tarball, fetch_docs


def make_tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


TAR = make_tar({
    "visidata-stable/docs/join.md": b"## Join\ntext\n",
    "visidata-stable/docs/api/x.md": b"nested",
    "visidata-stable/docs/pic.png": b"\x89PNG",
    "visidata-stable/README.md": b"root",
    "visidata-stable/docs/bad.md": b"caf\xe9 \xff",
})


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_keeps_only_top_level_markdown_in_docs():
    out = _docs_from_tarball(TAR, "docs")
    assert set(out) == {"join.md", "bad.md"}


def test_non_utf8_bytes_do_not_crash():
    assert "caf" in _docs_from_tarball(TAR, "docs")["bad.md"]


def test_fetch_docs_uses_given_ref():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, content=TAR)

    out = fetch_docs("saulpw/visidata", "stable", "docs", client=_client(handler))
    assert seen["url"] == "https://codeload.github.com/saulpw/visidata/tar.gz/stable"
    assert "join.md" in out


def test_oversized_download_is_refused():
    client = _client(lambda request: httpx.Response(200, content=TAR))
    with pytest.raises(ValueError, match="too large"):
        fetch_docs("saulpw/visidata", "stable", "docs", client=client, max_bytes=10)


def test_http_error_is_raised_not_swallowed():
    client = _client(lambda request: httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_docs("saulpw/visidata", "no-such-ref", "docs", client=client)
