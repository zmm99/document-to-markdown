from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Tag

from app.converters.base import ConvertResult, read_text_file, rows_to_markdown_table


class HtmlConverter:
    engine = "beautifulsoup4"

    def convert(self, input_path: Path, output_dir: Path) -> ConvertResult:
        soup = BeautifulSoup(read_text_file(input_path), "html.parser")
        for node in soup(["script", "style"]):
            node.decompose()

        body = soup.body or soup
        markdown = "\n\n".join(
            part for part in (self._node_to_markdown(node) for node in body.children) if part
        )

        return ConvertResult(
            markdown=markdown,
            metadata={
                "engine": self.engine,
                "source_format": "html",
                "title": soup.title.get_text(strip=True) if soup.title else None,
            },
        )

    def _node_to_markdown(self, node) -> str:
        if not isinstance(node, Tag):
            return str(node).strip()

        name = node.name.lower()
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            return f"{'#' * level} {node.get_text(' ', strip=True)}"
        if name == "p":
            return node.get_text(" ", strip=True)
        if name in {"ul", "ol"}:
            return "\n".join(
                f"- {item.get_text(' ', strip=True)}"
                for item in node.find_all("li", recursive=False)
                if item.get_text(strip=True)
            )
        if name == "table":
            rows = []
            for row in node.find_all("tr"):
                cells = row.find_all(["th", "td"])
                rows.append([cell.get_text(" ", strip=True) for cell in cells])
            return rows_to_markdown_table(rows)
        if name == "pre":
            return f"```\n{node.get_text()}\n```"
        if name == "blockquote":
            text = node.get_text(" ", strip=True)
            return "\n".join(f"> {line}" for line in text.splitlines())
        if name == "br":
            return "\n"

        return "\n\n".join(
            part for part in (self._node_to_markdown(child) for child in node.children) if part
        )
