from dataclasses import dataclass


@dataclass(frozen=True)
class Piece:
    id: str
    page_slug: str
    page_title: str
    url: str
    anchor: str
    heading_path: tuple[str, ...]
    text: str
    docs_ref: str
    docs_version: str | None
    last_updated: str | None
    anchor_explicit: bool = False

    @property
    def citation_url(self) -> str:
        # Only headings with their own {#id} have an id on the published page (spike S7);
        # a generated slug would silently open the page at the top, so cite the page instead.
        return f"{self.url}#{self.anchor}" if self.anchor and self.anchor_explicit else self.url

    @property
    def search_text(self) -> str:
        return " › ".join(self.heading_path) + "\n" + self.text
