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


def test_content_length_over_the_limit_is_refused_before_reading_the_body():
    read = []

    def body():
        read.append(1)
        yield b"x" * 10

    client = _client(lambda request: httpx.Response(
        200, headers={"content-length": "999999999"}, content=body()))
    with pytest.raises(ValueError, match="too large"):
        fetch_docs("saulpw/visidata", "stable", "docs", client=client, max_bytes=1000)
    assert read == []


def test_streamed_body_without_content_length_is_cut_off_at_the_limit():
    def body():
        for _ in range(100):
            yield b"x" * 100

    client = _client(lambda request: httpx.Response(200, content=body()))
    with pytest.raises(ValueError, match="too large"):
        fetch_docs("saulpw/visidata", "stable", "docs", client=client, max_bytes=1000)


def test_a_huge_markdown_member_is_skipped():
    tar = make_tar({"r/docs/small.md": b"## S\nok\n", "r/docs/huge.md": b"a" * 6_000_000})
    assert set(_docs_from_tarball(tar, "docs")) == {"small.md"}


def test_no_markdown_found_is_an_error_not_an_empty_result():
    # a wrong docs_path or a moved folder must not look like "zero pages"
    client = _client(lambda request: httpx.Response(200, content=TAR))
    with pytest.raises(ValueError, match="no markdown"):
        fetch_docs("saulpw/visidata", "stable", "no-such-folder", client=client)


def test_utf8_bom_is_dropped():
    tar = make_tar({"r/docs/a.md": b"\xef\xbb\xbf---\nUpdate: 2020-01-01\n---\ntext\n"})
    assert _docs_from_tarball(tar, "docs")["a.md"].startswith("---")


def test_commit_sha_is_read_from_the_tarball_header():
    from ingest.fetch import commit_from_tarball, fetch_docs_and_commit
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT,
                      pax_headers={"comment": "6c4c5a4f24e68d1fa34d79bbb8362662e30b2450"}) as tf:
        data = b"## Join\ntext\n"
        info = tarfile.TarInfo("visidata-stable/docs/join.md")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    tar = buf.getvalue()
    assert commit_from_tarball(tar) == "6c4c5a4f24e68d1fa34d79bbb8362662e30b2450"
    assert commit_from_tarball(TAR) is None
    files, sha = fetch_docs_and_commit("a/b", "stable", "docs",
                                       _client(lambda r: httpx.Response(200, content=tar)))
    assert set(files) == {"join.md"} and sha.startswith("6c4c5a4f")


def test_non_utf8_file_gives_a_warning_that_names_it():
    with pytest.warns(UserWarning, match="bad.md"):
        _docs_from_tarball(TAR, "docs")
