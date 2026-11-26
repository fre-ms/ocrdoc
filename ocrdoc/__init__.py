"""ocrdoc: recognises what is on the pages of a PDF, and leaves the pages as they are.

Divides every page into areas (text, tables with their grids, pictures, barcodes with
their content, stamps, handwriting), reads its text (RapidOCR, Tesseract) with a box for
every word where the page has no text of its own, gives it structure (paragraphs, lists,
tables) and lays it invisibly over the page.  Everything a machine found and everything a
person decided is kept in a configuration document, from which the result is made again,
byte for byte.  Everything runs locally.

The modules:

- :mod:`ocrdoc.project`: the work on one PDF and its configuration document;
- :mod:`ocrdoc.filters`: what ocrdoc's own rendering of a page goes through before OCR;
- :mod:`ocrdoc.ocr`: the OCR engines and the page text they produce;
- :mod:`ocrdoc.pagetext`: the page text with a box for every character;
- :mod:`ocrdoc.layout`: the areas of a page and the grids of its tables;
- :mod:`ocrdoc.areas`: barcodes, pictures, stamps and handwriting found;
- :mod:`ocrdoc.tables`: tables found with Camelot;
- :mod:`ocrdoc.structure`: lines, paragraphs, headings, lists and tables as Markdown;
- :mod:`ocrdoc.alignment`: a corrected text laid back onto the OCR boxes;
- :mod:`ocrdoc.reading`: what a reading is, and the short way to one;
- :mod:`ocrdoc.output`: the searchable PDF, the reading as JSON, Markdown;
- :mod:`ocrdoc.textlayer`: the invisible text layer, one line per OCR line;
- :mod:`ocrdoc.errors`: ocrdoc's own kinds of error, worded in English and German;
- :mod:`ocrdoc.settings`: the settings of the OCR layer;
- :mod:`ocrdoc.cli` and :mod:`ocrdoc.bench`: the command line and the test bench.

What every tool of docrepro shares (configuration documents, the command line's manners,
no network, the window's building blocks) is doccor's (:mod:`doccor`).
"""

__version__ = "0.1.0"
