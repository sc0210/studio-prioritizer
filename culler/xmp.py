"""XMP sidecars that Capture One picks up as star ratings, color labels and keywords."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from .scoring import Result

KEYWORD_PREFIX = "studio-photo"

TEMPLATE = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="studio-photo">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmp:Rating="{rating}"
    xmp:Label="{label}">
   <dc:subject>
    <rdf:Bag>
{keywords}
    </rdf:Bag>
   </dc:subject>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""


def sidecar_path(photo: Path) -> Path:
    # Capture One and Lightroom both look for DSC01234.xmp next to DSC01234.ARW.
    return photo.with_suffix(".xmp")


def render(result: Result) -> str:
    keywords = [f"{KEYWORD_PREFIX}/{result.decision}"]
    keywords += [f"{KEYWORD_PREFIX}/{reason}" for reason in result.reasons]
    lines = "\n".join(f"     <rdf:li>{escape(k)}</rdf:li>" for k in keywords)
    return TEMPLATE.format(rating=result.stars, label=result.label, keywords=lines)


def write_sidecar(result: Result, force: bool = False) -> str:
    """Returns 'written', or 'skipped' if a sidecar exists and force is off.

    An existing sidecar may hold edits or ratings from Capture One, so it is
    never replaced unless asked.
    """
    path = sidecar_path(result.info.path)
    if path.exists() and not force:
        return "skipped"
    path.write_text(render(result), encoding="utf-8")
    return "written"
