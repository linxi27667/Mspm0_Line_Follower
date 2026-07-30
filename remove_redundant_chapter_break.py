from pathlib import Path
import sys

from docx import Document
from docx.oxml.ns import qn


def main():
    path = Path(sys.argv[1])
    doc = Document(path)
    chapter = next(
        paragraph
        for paragraph in doc.paragraphs
        if paragraph.text.strip() == "设计需求分析"
    )
    previous = chapter._p.getprevious()
    while previous is not None:
        if (
            previous.tag == qn("w:p")
            and previous.find("./" + qn("w:pPr") + "/" + qn("w:sectPr"))
            is not None
        ):
            breaks = previous.findall(".//" + qn("w:br"))
            for page_break in breaks:
                page_break.getparent().remove(page_break)
            print(f"removed_breaks={len(breaks)}")
            doc.save(path)
            return
        previous = previous.getprevious()
    raise RuntimeError("Section-break paragraph before chapter 1 was not found")


if __name__ == "__main__":
    main()
