"""Build the base institutional letterhead used by approval_documents.py."""

from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


BASE = Path(__file__).parent / "templates" / "documents"
TEMPLATE = BASE / "reservation_approval_template.docx"
SEAL = BASE / "norsu_seal.png"
NAVY = "123B68"
BLUE = "1F5A91"
GOLD = "C9A449"
MUTED = "536273"


def style(run, size, *, bold=False, color=NAVY, font="Arial"):
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def border(parent, edge, color, size="8"):
    is_cell = hasattr(parent, "_tc")
    properties = parent._tc.get_or_add_tcPr() if is_cell else parent._p.get_or_add_pPr()
    borders = properties.find(qn("w:tcBorders" if is_cell else "w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:tcBorders" if is_cell else "w:pBdr")
        properties.append(borders)
    node = OxmlElement(f"w:{edge}")
    node.set(qn("w:val"), "single")
    node.set(qn("w:sz"), size)
    node.set(qn("w:space"), "4")
    node.set(qn("w:color"), color)
    borders.append(node)


doc = Document()
section = doc.sections[0]
section.page_width = Inches(8.5)
section.page_height = Inches(11)
section.top_margin = Inches(1.25)
section.bottom_margin = Inches(0.52)
section.left_margin = Inches(0.7)
section.right_margin = Inches(0.7)
section.header_distance = Inches(0.28)
section.footer_distance = Inches(0.35)

normal = doc.styles["Normal"]
normal.font.name = "Arial"
normal.font.size = Pt(10)
normal.font.color.rgb = RGBColor.from_string("202B36")
normal.paragraph_format.space_after = Pt(0)
normal.paragraph_format.line_spacing = 1.08

header = section.header
header.is_linked_to_previous = False
table = header.add_table(rows=1, cols=1, width=Inches(7.1))
table.autofit = False
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.columns[0].width = Inches(7.1)
for cell in table.rows[0].cells:
    width = 7.1
    cell.width = Inches(width)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    margins = OxmlElement("w:tcMar")
    for edge, value in (("top", 0), ("start", 35), ("bottom", 70), ("end", 35)):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        margins.append(node)
    cell._tc.get_or_add_tcPr().append(margins)
    border(cell, "bottom", GOLD, "12")
brand = table.cell(0, 0)
brand.text = ""
p = brand.paragraphs[0]
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(1)
p.add_run().add_picture(str(SEAL), width=Inches(0.45))
p = brand.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(1)
style(p.add_run("NEGROS ORIENTAL STATE UNIVERSITY"), 13, bold=True, color=NAVY, font="Cambria")
p = brand.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(1)
style(p.add_run("Bayawan-Sta. Catalina Campus"), 9.2, color=MUTED)
p = brand.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(1)
style(p.add_run("STUDENT AFFAIRS AND SERVICES  |  SAS RESERVE"), 8.2, bold=True, color=BLUE)

# Replace the default empty paragraph above the header table with one compact line.
for p in list(header.paragraphs):
    p._element.getparent().remove(p._element)

footer = section.footer
footer.is_linked_to_previous = False
p = footer.paragraphs[0]
p.clear()

# The template supplies only the institutional header. The generator builds
# the reservation body and signatures; no sidebar or repeated disclaimer is
# carried into approval letters.
doc.save(TEMPLATE)
print(TEMPLATE)
