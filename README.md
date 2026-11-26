# ocrdoc

ocrdoc recognises what is on the pages of a PDF and leaves the pages as they are. It divides every
page into areas (text, tables with their grid, pictures, barcodes, handwriting, stamps, areas not to be
read), reads the text with word boxes where the page has no text of its own, finds the cells of its
tables and the content of its barcodes, gives the text structure (paragraphs, lists, tables) and lays
it invisibly over the page. The result is a searchable PDF and a machine-readable reading that other
programs can build on. Everything runs on your own computer; nothing is sent anywhere (the command line
refuses any attempt to reach the network, and switches off the telemetry ONNX Runtime would otherwise
queue for Microsoft).

It is one step of **docrepro**, a family of tools that reproduce photographed and scanned documents as
real digital documents, one tool for one step:

| tool | its step |
|---|---|
| [optdoc](https://github.com/fre-ms/optdoc) | makes the page faithful: upright, unwarped, in its true proportions, evenly lit, in its own colours |
| **ocrdoc** | recognises: areas, text, tables, barcodes |
| semdoc, tagdoc (planned) | understand the text (medical terms, identifying information) and describe the document |

What they share (configuration documents, the command line's manners, no network, the window's building
blocks) is [doccor](https://github.com/fre-ms/doccor)'s. ocrdoc works on any PDF, optdoc's or another
program's, and knows nothing of the applications that use it.

**Status: pre-alpha (0.2.0).** The code comes out of optdoc 0.6.0, with its history, where it read the
pages optdoc had prepared. `CHANGELOG.md` lists what changed in the move.

## Every step can be reproduced and resumed

The configuration document (`<name>.ocrdoc.json`, also inside the PDF ocrdoc writes) holds every
setting, the filters every page was read through, the words OCR read, the areas found and those a person
drew, and the person's corrections, and nothing else (no paths, no times). **The same PDF with the same
document gives the same four files, byte for byte**: OCR and the finders do not run again where their
results are stored. The window saves the document and opens it again where the person stopped.

The PDF ocrdoc writes carries the documents of every step that made it: optdoc's (`optdoc.json`) as its
input had it, and ocrdoc's own (`ocrdoc.json`). So a finished document says how it was made, and with the
original it is made again. When a person goes back and changes a page in optdoc (more contrast), ocrdoc's
document no longer fits its input by hash; where the page's frame (its geometry, which optdoc records in
its own document from its version that comes with ocrdoc on) stayed the same, what the person decided in
ocrdoc stays and what a machine found is found again, and the pages whose frame changed are named.

## What it does

- **Reads** with [RapidOCR](https://github.com/RapidAI/RapidOCR) (ONNX models in the wheel, no download) or
  [Tesseract](https://github.com/tesseract-ocr/tesseract), with real word boxes and confidences. Tables with
  ruled grids, which Tesseract's page segmentation tends to drop, are read a second time without their lines.
  A page with a text layer of its own is read as it is.
- **Filters only its own copy.** What helps OCR (upscaling a coarse scan, a letter mode, taking coloured
  ink or ruled lines away, black and white) is done to ocrdoc's rendering of a page, never to the page:
  the stamp stays in the document. ocrdoc suggests the filters per page; a person can choose them.
- **Divides a page into areas**: text, tables, pictures, barcodes, handwriting, stamps, and areas not to
  be read; what lies in no area is text. Words in pictures, barcodes and areas not to be read stay out of
  the text; handwriting and stamps are read and marked, so that a program such as a pseudonymiser can
  cover them. Barcodes are found and read (QR, DataMatrix, Code 128, EAN …; extra `barcodes`), pictures,
  stamps (by their colour) and handwriting found by measured rules.
- **Finds tables with their grid** (extra `tables`, Camelot), in born-digital PDFs and, through its own
  text layer, in scans, and puts every word into the cell of the grid it lies in: a laboratory result
  comes out as a row of cells, name, value, unit, range, flag.
- **Structures** the OCR text as Markdown: paragraphs re-joined, headings by size and weight, lists,
  tables from their grids or from wide gaps.
- **Writes** a searchable PDF (the input's pages with the recognised words laid invisibly over the printed
  ones, line by line, so that selecting a word in a reader covers it and a program that takes the text out
  gets a row of a table as one line; every character as read, "≤" and "↑" too), the reading as JSON, the
  text as Markdown, and the configuration document.
- **Lets a person correct it** in a window (extra `gui`, Qt): the filters of every page, the page as it is
  beside the page as OCR reads it; the areas of the page, to be drawn, moved, resized, given another kind
  or deleted, and a table's grid, whose lines can be added, dragged and taken away and whose cells can be
  merged and split; and the text read by OCR beside the page, uncertain words marked, to be corrected by
  hand. A correction reaches the PDF's text layer, the reading and the Markdown.

## Install

Python 3.12 or later, with [uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/fre-ms/ocrdoc
cd ocrdoc
uv sync --extra ocr --extra tables --extra gui --extra barcodes
```

The `ocr` extra brings RapidOCR, ONNX Runtime, OpenCV and NumPy (for the filters and the finders); the
`tables` extra brings [Camelot](https://github.com/camelot-dev/camelot), which finds tables with their
cells; the `barcodes` extra zxing-cpp; the `gui` extra PySide6 (Qt, LGPL 3.0) for the window. Tesseract
is optional and installed separately (`brew install tesseract tesseract-lang`,
`apt install tesseract-ocr tesseract-ocr-deu`). The standalone program with every tool of docrepro inside
is [docrepro](https://github.com/fre-ms/docrepro)'s.

## Command line

```
ocrdoc about
ocrdoc run scan.pdf --out results/
ocrdoc run scan.pdf --reader tesseract --languages deu+eng
ocrdoc edit scan.pdf --out results/ --language en
ocrdoc edit scan.pdf --out results/ --config results/scan.ocrdoc.json
```

`run` writes `<name>.pdf`, `<name>.reading.json`, `<name>.md` and `<name>.ocrdoc.json` into the folder
given and nowhere else. `edit` opens the window; *Apply* writes the same four files, *Save and continue
later* the configuration document alone, *Cancel* nothing. `--config` (a `<name>.ocrdoc.json` or a PDF
ocrdoc wrote) starts from a configuration document instead of ocrdoc's suggestions, for `run` and `edit`
alike. Every command answers with one JSON object on standard output, so that programs in any language
can use ocrdoc as a helper; a failure too, with a fixed kind and its message in English and German, and
exit status 2. No answer quotes a document or its path. Options: `--reader auto|rapidocr|tesseract|none`,
`--languages`, `--config`, `--no-tables`, `--no-structure`, `--no-cells` (no tables with their cells),
`--no-areas` (no barcodes, pictures, stamps or handwriting), `--models <folder>`, `--progress` (a line of
JSON per page on standard error). [docs/interface.md](docs/interface.md) describes the answers, the kinds
of error, the configuration document and the reading.

**Models** come the way they do in every tool of docrepro: `ocrdoc models list` shows the models ocrdoc
can use, `ocrdoc models fetch <name> --to <folder>` fetches one (the only command that goes on the
network, and only when asked), `run` and `edit` use what lies in the folder of `--models`. ocrdoc lists
none yet: a model is listed only after it did better than the rules it would add to, and the layout model
measured so far (PP-DocLayout_plus-L) did not, on the invented letters of the bench below.

Settings without a configuration file: `OCRDOC_OCR` (the engine `auto` stands for), `OCRDOC_TESSERACT`
(the program's path), `OCRDOC_TESSERACT_LANGUAGES`. An application that embeds ocrdoc hands over its own
with `ocrdoc.settings.set_settings`.

## Test bench

`ocrdoc bench <folder>` scores the readings of PDFs whose content is known. Next to every PDF lies a truth
file `<name>.truth.txt`, one line per item as it is printed (`Kalium 5,8 mmol/l 3,5 - 5,1 H`). The answer
is numbers only (rows found word for word, numbers read right in their own row, rows with every number
right, similarity, engine confidence), per document and per engine. Documents are named by their position,
never by file name, and no word of a document or a truth file is printed, not even in an error. So the
bench can run on real documents on your own computer while only the figures are shared.

Invented laboratory reports to print and scan (a photo goes through optdoc first):

```
uv run python bench/lab_reports.py reports/ 6     # reports/lab-01.pdf … and lab-01.truth.txt …
ocrdoc bench reports/
```

Where a document also has `<name>.cells.json` (the cells of each row as printed; `bench/lab_reports.py`
writes it), the bench scores its tables as well: rows cut into the right cells, rows read exactly.
`bench/area_letters.py` makes invented letters with a logo, a picture, a stamp, handwriting and barcodes,
and the boxes where they lie, and `bench/areas_bench.py` measures the finders on them, as made, scanned in
colour, scanned in grey and photographed (the last with optdoc installed beside ocrdoc): how many of the
areas drawn are found, how many are found where none was drawn, and how many barcodes are read right.
With `--models <folder>` it measures what a model gains over the rules.

```
uv run python bench/areas_bench.py letters/
```

## In Python

```python
from ocrdoc import output
from ocrdoc.reading import read

reading = read("scan.pdf")
try:
    output.write(reading, "results")
    print(reading.pages[0].markdown)
finally:
    reading.close()
```

To keep the work, or to change it before the result is made, open a project:

```python
from ocrdoc import output
from ocrdoc.filters import Filters
from ocrdoc.project import Project, load_config

project = Project.open("scan.pdf")              # or config=load_config("results/scan.ocrdoc.json")
try:
    project.set_filters(0, Filters(upscale=2, letter_mode=True))
    project.set_correction(0, project.text(0).replace("U/I", "U/l"))
    reading = project.build()
    try:
        output.write(reading, "results")        # the configuration document is written with it
    finally:
        reading.close()
finally:
    project.close()
```

Errors are `ocrdoc.errors.OcrdocError` with a `kind` and `details`; `ocrdoc.errors.describe_error(error, "de")`
words one in German, `"en"` in English.

## Planned

- The reading order of text areas.
- Stamps on pages scanned in grey, which the rules miss (0 of 6 on the bench); a layout model measured on
  real documents, where the invented letters cannot judge it.
- Apple Vision as a reader on macOS, including its document recognition with table cells.
- Two independent readings of every number, so that a value is only trusted where both agree.

## Licence

GNU Affero General Public License 3.0 or later (see `LICENSE`); PyMuPDF, on which ocrdoc rests, is AGPL as well.
