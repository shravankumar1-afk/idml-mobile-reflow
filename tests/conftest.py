"""Shared fixtures: build a tiny synthetic IDML package on the fly.

Keeps tests fast and repo-light (no large binary sample committed).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

DESIGNMAP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Document xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
          DOMVersion="18.0" Self="doc" StoryList="ustory1 ustory2">
  <idPkg:Spread src="Spreads/Spread_uspr.xml"/>
  <idPkg:Story src="Stories/Story_ustory1.xml"/>
  <idPkg:Story src="Stories/Story_ustory2.xml"/>
</Document>
"""

STORY1 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="18.0">
  <Story Self="ustory1">
    <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Heading 1">
      <CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]" PointSize="24">
        <Content>Solutions</Content>
      </CharacterStyleRange>
    </ParagraphStyleRange>
    <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Body">
      <CharacterStyleRange PointSize="11">
        <Content>Water boils at a </Content>
      </CharacterStyleRange>
      <CharacterStyleRange PointSize="11" FontStyle="Bold">
        <Content>lower</Content>
      </CharacterStyleRange>
      <CharacterStyleRange PointSize="11">
        <Content> temperature at altitude.</Content>
      </CharacterStyleRange>
    </ParagraphStyleRange>
  </Story>
</idPkg:Story>
"""

# Second story: an option paragraph + an anchored image (equation).
STORY2 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Story xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="18.0">
  <Story Self="ustory2">
    <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Question">
      <CharacterStyleRange PointSize="11">
        <Content>What is molarity?</Content>
      </CharacterStyleRange>
    </ParagraphStyleRange>
    <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/Option">
      <CharacterStyleRange PointSize="11">
        <Content>(A) moles per litre </Content>
        <Rectangle Self="uanchor">
          <Image Self="uimg">
            <Link LinkResourceURI="file:Links/eqn.wmf"/>
          </Image>
        </Rectangle>
      </CharacterStyleRange>
    </ParagraphStyleRange>
  </Story>
</idPkg:Story>
"""

SPREAD = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Spread xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="18.0">
  <Spread Self="uspr">
    <Page Self="upage" Name="1" GeometricBounds="0 0 792 612" ItemTransform="1 0 0 1 0 0"/>
    <TextFrame Self="utf1" ParentStory="ustory1" GeometricBounds="50 50 300 300"
               ItemTransform="1 0 0 1 0 0"/>
    <TextFrame Self="utf2" ParentStory="ustory2" GeometricBounds="350 50 600 300"
               ItemTransform="1 0 0 1 0 0"/>
  </Spread>
</idPkg:Spread>
"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Styles xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="18.0">
  <RootParagraphStyleGroup>
    <ParagraphStyle Self="ps1" Name="Heading 1"/>
    <ParagraphStyle Self="ps2" Name="Body"/>
  </RootParagraphStyleGroup>
</idPkg:Styles>
"""

FONTS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<idPkg:Fonts xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging" DOMVersion="18.0">
  <FontFamily Self="f1" Name="Minion Pro"/>
</idPkg:Fonts>
"""


def _write_idml(path: Path) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/vnd.adobe.indesign-idml-package")
        zf.writestr("designmap.xml", DESIGNMAP)
        zf.writestr("Stories/Story_ustory1.xml", STORY1)
        zf.writestr("Stories/Story_ustory2.xml", STORY2)
        zf.writestr("Spreads/Spread_uspr.xml", SPREAD)
        zf.writestr("Resources/Styles.xml", STYLES)
        zf.writestr("Resources/Fonts.xml", FONTS)


@pytest.fixture
def sample_package(tmp_path: Path) -> Path:
    """A folder containing a tiny .idml plus empty Links/ and Document fonts/."""
    folder = tmp_path / "pkg"
    folder.mkdir()
    _write_idml(folder / "sample.idml")
    (folder / "Links").mkdir()
    (folder / "Document fonts").mkdir()
    return folder


@pytest.fixture
def sample_idml(sample_package: Path) -> Path:
    return sample_package / "sample.idml"
