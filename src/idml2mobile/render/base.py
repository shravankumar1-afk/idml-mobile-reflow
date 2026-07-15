"""Template Method base for content renderers.

`Renderer.render()` fixes the algorithm skeleton — prepare, emit head, walk the
document emitting each block via a type-dispatched hook, then finalize.
Subclasses fill the hooks. The content model (Document) is passed in, keeping
content and rendering on opposite sides of the Bridge.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from idml2mobile.model.blocks import (
    Block,
    Document,
    ImageBlock,
    MathBlock,
    Section,
    TableBlock,
    TextBlock,
)


class Renderer(ABC):
    def render(self, document: Document) -> str:
        self.prepare(document)
        parts = [self.render_head(document), self.open_body(document)]
        for section in document.sections:
            parts.append(self.render_section(section))
        parts.append(self.close_body(document))
        return self.finalize("".join(parts))

    # -- template hooks (override as needed) -------------------------------
    def prepare(self, document: Document) -> None:  # noqa: D401
        return None

    @abstractmethod
    def render_head(self, document: Document) -> str: ...

    @abstractmethod
    def open_body(self, document: Document) -> str: ...

    @abstractmethod
    def close_body(self, document: Document) -> str: ...

    def render_section(self, section: Section) -> str:
        out = [self.open_section(section)]
        for child in section.children:
            if isinstance(child, Block):
                out.append(self.render_block(child))
        out.append(self.close_section(section))
        return "".join(out)

    def open_section(self, section: Section) -> str:
        return ""

    def close_section(self, section: Section) -> str:
        return ""

    def render_block(self, block: Block) -> str:
        if isinstance(block, ImageBlock):
            return self.render_image(block)
        if isinstance(block, MathBlock):
            return self.render_math(block)
        if isinstance(block, TableBlock):
            return self.render_table(block)
        if isinstance(block, TextBlock):
            return self.render_text(block)
        return ""

    @abstractmethod
    def render_text(self, block: TextBlock) -> str: ...

    @abstractmethod
    def render_image(self, block: ImageBlock) -> str: ...

    @abstractmethod
    def render_math(self, block: MathBlock) -> str: ...

    @abstractmethod
    def render_table(self, block: TableBlock) -> str: ...

    def finalize(self, body: str) -> str:
        return body
