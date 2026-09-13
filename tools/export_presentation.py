"""Export this project's text-and-table PowerPoint as local HTML slides.

Run from the repository root with ``python tools/export_presentation.py``.
This deliberately supports the shapes used by the interview deck, rather than
claiming to be a general PowerPoint renderer. Unsupported shapes fail clearly.
"""

from html import escape
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def export(source, destination):
    """Write HTML and layout CSS from the supplied interview PPTX.

    Args:
        source: Path to the deck containing text boxes and tables.
        destination: Demo directory receiving presentation.html and slide CSS.

    Returns:
        Number of slides exported, including their speaker notes.

    Raises:
        ValueError: A shape requires conversion support not implemented here.
    """
    css = []

    def styled(rules):
        """Store a generated CSS rule and return its unique class name."""
        name = f"ppt-{len(css)}"
        css.append(f".{name} {{{rules}}}")
        return name

    def color(node, fallback="222B2B"):
        """Read an explicit RGB fill from a PowerPoint element."""
        fill = node.find("a:solidFill/a:srgbClr", NS)
        return "#" + (fill.get("val") if fill is not None else fallback)

    with ZipFile(source) as package:
        size = ET.fromstring(package.read("ppt/presentation.xml")).find("p:sldSz", NS)
        width, height = int(size.get("cx")), int(size.get("cy"))

        def length(value):
            """Convert EMU lengths to slide-container-relative CSS units."""
            return f"{float(value) / width * 100:.6f}cqw"

        def position(transform):
            """Preserve the slide element's original location and dimensions."""
            offset, extent = transform.find("a:off", NS), transform.find("a:ext", NS)
            return (
                f"position:absolute;left:{length(offset.get('x'))};"
                f"top:{length(offset.get('y'))};width:{length(extent.get('cx'))};"
                f"height:{length(extent.get('cy'))};"
            )

        def paragraphs(body):
            """Convert text paragraphs and explicit run styling to escaped HTML."""
            output = []
            for paragraph in body.findall("a:p", NS):
                runs = []
                for run in paragraph:
                    if run.tag == f"{{{NS['a']}}}br":
                        runs.append("<br>")
                    elif run.tag == f"{{{NS['a']}}}r":
                        props = run.find("a:rPr", NS)
                        if props is None:
                            props = paragraph.find("a:pPr/a:defRPr", NS)
                        if props is None:
                            raise ValueError("Text without explicit formatting")
                        font = props.find("a:latin", NS)
                        family = "Georgia,serif" if font is not None and font.get("typeface") == "Georgia" else "Arial,sans-serif"
                        # DrawingML font size is hundredths of a point; 1pt = 12700 EMU.
                        style = styled(
                            f"font-size:{length(float(props.get('sz', '1800')) * 127)};"
                            f"font-family:{family};color:{color(props)};"
                            f"font-weight:{'700' if props.get('b') == '1' else '400'};"
                        )
                        runs.append(f'<span class="{style}">{escape(run.findtext("a:t", "", NS))}</span>')
                output.append("<p>" + "".join(runs) + "</p>")
            return "".join(output)

        files = sorted(
            (name for name in package.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=lambda name: int(re.search(r"slide(\d+)", name).group(1)),
        )
        slides, notes = [], []
        for number, name in enumerate(files, 1):
            slide = ET.fromstring(package.read(name))
            background = slide.find("p:cSld/p:bg/p:bgPr", NS)
            style = styled(f"background:{color(background, 'F5F4EF')};aspect-ratio:{width}/{height};")
            elements = []
            for shape in slide.find("p:cSld/p:spTree", NS):
                if shape.tag.endswith(("}nvGrpSpPr", "}grpSpPr")):
                    continue
                if shape.tag.endswith("}sp"):
                    body = shape.find("p:txBody", NS)
                    if body is None:
                        raise ValueError("Only text shapes and tables are supported")
                    box = styled(position(shape.find("p:spPr/a:xfrm", NS)))
                    elements.append(f'<div class="text-box {box}">{paragraphs(body)}</div>')
                elif shape.tag.endswith("}graphicFrame"):
                    table = shape.find(".//a:tbl", NS)
                    if table is None:
                        raise ValueError("Only table graphic frames are supported")
                    box = styled(position(shape.find("p:xfrm", NS)))
                    columns = "".join(
                        f'<col class="{styled("width:" + length(col.get("w")) + ";")}">'
                        for col in table.findall("a:tblGrid/a:gridCol", NS)
                    )
                    rows = []
                    for index, row in enumerate(table.findall("a:tr", NS)):
                        cells = []
                        for cell in row.findall("a:tc", NS):
                            properties = cell.find("a:tcPr", NS)
                            cell_style = styled(f"background:{color(properties, 'FFFFFF')};")
                            tag = "th" if index == 0 else "td"
                            scope = ' scope="col"' if index == 0 else ""
                            cells.append(f'<{tag}{scope} class="{cell_style}">{paragraphs(cell.find("a:txBody", NS))}</{tag}>')
                        row_style = styled(f"height:{length(row.get('h'))};")
                        rows.append(f'<tr class="{row_style}">{"".join(cells)}</tr>')
                    elements.append(f'<table class="{box}"><colgroup>{columns}</colgroup>{"".join(rows)}</table>')
                else:
                    raise ValueError(f"Unsupported slide element: {shape.tag}")
            hidden = "" if number == 1 else " hidden"
            slides.append(f'<section class="slide {style}" aria-label="Slide {number} of {len(files)}"{hidden}>{"".join(elements)}</section>')
            note_path = f"ppt/notesSlides/notesSlide{number}.xml"
            note_lines = []
            if note_path in package.namelist():
                note = ET.fromstring(package.read(note_path))
                for shape in note.findall(".//p:sp", NS):
                    placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
                    if placeholder is not None and placeholder.get("type") == "body":
                        for para in shape.findall("p:txBody/a:p", NS):
                            note_lines.append("".join(para.itertext()))
            notes.append(f'<div class="speaker-note"{hidden}>' + "".join(f"<p>{escape(line)}</p>" for line in note_lines) + "</div>")

    html = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shipment Risk · Presentation</title><link rel="stylesheet" href="/presentation.css"><link rel="stylesheet" href="/presentation-slides.css"><script src="/presentation.js" defer></script></head>
<body><header><a href="/">← Live demo</a><span>SHIPMENT RISK LAB / PRESENTATION</span><button id="fullscreen" type="button">Fullscreen</button></header>
<main id="stage" aria-label="Interview presentation">''' + "".join(slides) + '''</main>
<nav aria-label="Slide controls"><button id="previous" type="button" aria-label="Previous slide">← Previous</button><label>Slide <select id="slide-picker" aria-label="Choose slide">''' + "".join(f'<option value="{i}">{i} / {len(slides)}</option>' for i in range(1, len(slides) + 1)) + '''</select></label><button id="next" type="button" aria-label="Next slide">Next →</button><button id="toggle-notes" type="button" aria-controls="notes" aria-expanded="false">Speaker notes</button></nav>
<p id="status" role="status" aria-live="polite">Arrow keys: change slide · F: fullscreen · N: notes</p>
<aside id="notes" hidden><h2>Speaker notes</h2>''' + "".join(notes) + '''</aside></body></html>'''
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "presentation.html").write_text(html, encoding="utf-8")
    (destination / "presentation-slides.css").write_text("\n".join(css) + "\n", encoding="utf-8")
    return len(slides)


if __name__ == "__main__":
    count = export(ROOT / "outputs/presentation/Shipment_Risk_Interview.pptx", ROOT / "demo")
    print(f"Exported {count} slides to demo/presentation.html")
