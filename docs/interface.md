# ocrdoc's command line as an interface

**Interface 1**, since ocrdoc 0.1.0 (this description: ocrdoc 0.2.0). This is what a program may
rely on when it calls ocrdoc, whatever language it is written in: a records app, a pseudonymiser,
a script, docrepro.

Every answer carries `interface`. It goes up when something a caller relies on changes in a way
that breaks it: a field or a kind of error removed or renamed, a meaning changed. Within one
interface, new fields, new options and new kinds of error may come; a caller ignores fields it
does not know and treats an unknown kind of error like any other (its message says what
happened). Releases are tagged; pin a tag, not a branch.

**Added within interface 1 (ocrdoc 0.2.0):** the way models come as an optional download, the same
as in every tool of docrepro: the commands `models list` and `models fetch`, the option `--models`,
`models` in the answer of `about`, and the kinds of error `unknown-model`, `model-unreachable` and
`model-checksum`. ocrdoc lists no model yet (below).

ocrdoc does one step of docrepro: it **recognises** what is on the pages of a PDF and leaves the
pages as they are. Making a photo or a scan faithful (upright, unwarped, evenly lit) is optdoc's
step before it; the two came out of optdoc 0.6.0, which did both (its `prepare` is optdoc's and
ocrdoc's `run` one after the other).

## Calling

```
ocrdoc about
ocrdoc run  <file.pdf> --out <folder> [options]
ocrdoc edit <file.pdf> --out <folder> [options] [--language de|en]
ocrdoc bench <folder> [--reader rapidocr|tesseract]
ocrdoc models list [--models <folder>]
ocrdoc models fetch <name> --to <folder> [--progress]
ocrdoc --version
```

Every command writes **exactly one JSON object to standard output**, whether it succeeds or not,
and ends with exit status **0** on success and **2** on failure. Standard error is free for
`--progress` (below) and the usage line of an invalid command line; nothing else reaches it, not
even what the libraries inside write there. No answer and no message ever quotes the content of
a document or a path given to ocrdoc, since a file name may name a patient.

Every answer has these two fields:

| field | example | meaning |
|---|---|---|
| `interface` | `1` | the version of this description |
| `made_with` | `"ocrdoc 0.2.0"` | the program and its version, for the record of what made a file |

## `about`: what this installation can do

```json
{"interface": 1, "made_with": "ocrdoc 0.2.0", "version": "0.2.0",
 "readers": ["rapidocr", "tesseract"], "filters": true, "tables": true, "barcodes": true,
 "window": true, "models": []}
```

`readers` lists the OCR engines found, in order of preference (`tesseract` is listed where the
system has it). `filters` says whether the filters for OCR and the finders of pictures, stamps and
handwriting are there (OpenCV and NumPy, the extra "ocr"), `tables` whether tables are found with
their cells (Camelot, the extra "tables"), `barcodes` whether barcodes are found and read
(zxing-cpp, the extra "barcodes"), `window` whether `edit` can open its window (PySide6, the extra
"gui"), `models` the models ocrdoc can use (none yet; see `models` below). The engines are not
loaded for this, so the answer is quick.

## `run`: recognise a PDF

```
ocrdoc run <file.pdf> --out <folder> [--config <file.ocrdoc.json | file.pdf>]
    [--reader auto|rapidocr|tesseract|none] [--languages <packs>]
    [--no-tables] [--no-structure] [--no-cells] [--no-areas] [--models <folder>] [--progress]
```

`<file>` is a PDF: one optdoc prepared, a scan, any PDF. A photo or an image goes through optdoc
first (`not-pdf` otherwise). ocrdoc never changes the file. It writes four files into `<folder>`
(made when missing) and **nothing anywhere else**: no copies, no caches, no images of pages in the
temporary folder (Camelot reads a page from a file, which ocrdoc writes into a hidden folder in
`<folder>` for a moment and removes at once). Without `--out` the folder is `<file>.ocrdoc` beside
the file.

| file | what it is |
|---|---|
| `<stem>.pdf` | the input with its pages as they came, an invisible text layer on every page read by OCR, and the configuration documents of every step inside |
| `<stem>.reading.json` | the reading (format `ocrdoc-reading`, below) |
| `<stem>.md` | the text as Markdown, a heading per page |
| `<stem>.ocrdoc.json` | the configuration document (format `ocrdoc-config`, below): from it and the file, the same four files again |

With `--config`, ocrdoc starts from a configuration document instead of its suggestions: a
`<stem>.ocrdoc.json`, or a PDF ocrdoc wrote, which carries it. The document then decides every
setting; `--reader`, `--languages`, `--no-tables`, `--no-structure` and `--no-areas` beside it are
a `usage` error. `--no-cells` beside it leaves out the tables found before, but not a person's.

The answer:

```json
{"interface": 1, "made_with": "ocrdoc 0.2.0",
 "pdf": "<folder>/<stem>.pdf", "reading": "<folder>/<stem>.reading.json",
 "markdown": "<folder>/<stem>.md", "config": "<folder>/<stem>.ocrdoc.json",
 "pages": 2, "ocr_pages": [1, 2], "pages_without_text": [], "filtered": [1, 2],
 "corrected": [], "dropped": [], "reader": "rapidocr", "tables": 1,
 "carried": ["optdoc.json"]}
```

Pages are counted from 1. `ocr_pages` were read by OCR (the others had a text layer of their own),
`pages_without_text` hold no text at all afterwards (no layer, no engine, or nothing legible),
`filtered` were read through at least one filter (below), `corrected` are pages whose text a
person corrected (in the window; carried by the configuration), `dropped` are pages whose
decisions no longer fit a changed input (below), `reader` is the engine used (`null` without one),
`tables` the number of tables with their cells (`null` when they were neither looked for,
`--no-cells` or the extra "tables" not installed, nor set by a person), `carried` the
configuration documents of the steps before that the input carried and the PDF carries on.

**Filters for OCR.** What helps OCR read a page often harms the document: grey instead of colour,
a stamp taken away. So ocrdoc filters only its own rendering of a page, never the page itself:
**upscale** (OCR reads the page at a multiple of its resolution, up to 4×), **letter mode** (grey,
strokes sharpened), **remove colour** (coloured ink becomes white, so that a stamp or a blue
signature hides no print beneath it), **remove lines** (long ruled lines become white) and
**black and white** (an adaptive threshold, never in letter mode). ocrdoc suggests them per page:
upscaling where the page's picture has less than 150 dpi, colour taken away where more than 0.3 %
of the page is coloured; a person can choose them in the window. Tesseract also reads the cells
of ruled tables a second time without their lines (`--no-tables` leaves that out).

**Areas and tables.** Every page is divided into areas (regions): text, tables with their grid
of rows and columns, pictures, barcodes, handwriting, stamps, and areas not to be read. ocrdoc
finds the tables with Camelot, on scanned pages in its own text layer, and keeps each as an area
with its grid; a person can correct every area and grid in the window (below). The words of a
page then go into the cells of the grid they lie in, so that a laboratory result is a row of
cells (name, value, unit, range, flag) rather than a line to take apart. Words in pictures,
barcodes and areas not to be read stay out of the text, the text layer and the reading;
handwriting and stamps are read and marked, so that a program can treat them apart. What lies in
no area is read as text. Barcodes are read as well (QR, DataMatrix, PDF417, Code 128, EAN and
more). A stamp is told by its colour (one strong hue, lines and letters), so not on a scan in
grey; handwriting by ink of the height of writing in which OCR read hardly a word; a picture
needs a clear case (filled or in many tones, hardly a word read in it). The areas are looked for
on the page as it is, in its colours. `--no-cells` finds no tables, `--no-areas` no barcodes,
pictures, stamps or handwriting; a person can set them all the same. Camelot's tables suffer
from a page that is tilted by more than a third of a degree: optdoc straightens such pages.

**Progress.** With `--progress`, a line goes to standard error before each page:

```
{"page": 1, "of": 2}
{"page": 2, "of": 2}
```

**Network.** ocrdoc never goes on the network while it works; everything it needs travels with
it. The command line refuses every attempt to resolve a name or open a connection before it does
anything else (the answer would be the error `network`), and switches off the telemetry of ONNX
Runtime, which would otherwise queue facts about the computer for sending to Microsoft. The one
command that would go out is `models fetch`, on request (below).

## `models`: optional downloads

```
ocrdoc models list [--models <folder>]
ocrdoc models fetch <name> --to <folder> [--progress]
```

The way every tool of docrepro takes models (optdoc's `docs/interface.md` describes the answers in
full): a tool lists the models it can use with the address each comes from, its SHA-256, size and
licence; `models fetch` is the only command that goes on the network, for that one file, and keeps
it only when it is the file listed; `run` and `edit` use what lies in the folder of `--models` and
do without what does not; what a model found is kept in the configuration document, so making the
result again needs no model.

**ocrdoc lists no model yet**: `models list` answers `{"models": []}`, `models fetch` answers
`unknown-model`, and `--models` changes nothing. A model is listed only after it did better than
the rules it would add to, and the one measured did not. `bench/areas_bench.py` counts on six
invented letters, as made, scanned in colour, scanned in grey and photographed, how many of the
areas drawn on them are found and how many are found where none was drawn:

| found of drawn (found where none was) | as made | colour scan | grey scan | photo |
|---|---|---|---|---|
| pictures, by the rules | 12 of 12 | 12 of 12 | 12 of 12 | 11 of 12 (1) |
| barcodes, by the rules (all read right) | 17 of 17 | 17 of 17 | 17 of 17 | 17 of 17 |
| stamps, by the rules | 6 of 6 | 5 of 6 (1) | 0 of 6 | 6 of 6 |
| handwriting, by the rules | 11 of 12 | 11 of 12 | 9 of 12 | 10 of 12 (3) |

PaddleOCR's layout model PP-DocLayout_plus-L (Apache-2.0, 130 MB) on the same pages found 6 to 9
of the 12 pictures, with many areas where none was drawn (barcodes and signatures taken for
pictures, the logo for a page header), and none of the 6 stamps in any variant, at 0.6 to 0.7
seconds a page against 0.2. Invented letters are not what the model was trained on, so this says
it is no gain here, not that it is a poor model; it is not listed until a measurement on real
documents says otherwise. The rules' weak spot is plain in the table: a stamp on a page scanned
in grey.

## `edit`: the window

```
ocrdoc edit <file.pdf> --out <folder> [--config <file.ocrdoc.json | file.pdf>]
    [--language de|en] [the settings of run] [--no-cells] [--progress]
```

Opens a window on the file, in German or English (`--language`, else the system's language),
and asks to bring it to the front. It starts as `run` would (ocrdoc's suggestions, or the
configuration document given), so that **Apply** at once gives the same files as `run`. Three
tabs, in FineReader's order:

- **Filters:** the page as it is and as OCR reads it, side by side; every filter switchable,
  the suggestion restored, no filter, the filters copied to every page. A page with a text layer
  of its own needs none.
- **Areas:** the areas ocrdoc found, in their colours and numbered in reading order; a tool to
  draw an area of each kind, to select, move and resize one and change its kind, to delete it,
  and for a table to add a column or row line, drag one, take one away, and merge cells or split
  them again; "find again" brings ocrdoc's areas back.
- **Check the text:** the page as OCR read it, words read with little confidence marked yellow, a
  click on a word selects it in the text; the text beside it, to be corrected by hand. A
  correction goes into the PDF's text layer, the reading (as words `"by": "person"`) and the
  Markdown; the words keep the boxes of the page.

The window closes in one of three ways:

| the person chooses | written into `<folder>` | answer |
|---|---|---|
| **Apply** | the four files, as `run` writes them | as `run`, and `"finished": true` |
| **Save and continue later** | the configuration document alone: `<stem>.ocrdoc.json` | `{"config": "<folder>/<stem>.ocrdoc.json", "finished": false, "dropped": []}` |
| **Cancel**, or closing the window | nothing | the error `cancelled` (status 2) |

`edit <file> --config <folder>/<stem>.ocrdoc.json` goes on where the person stopped; so does
`--config <the PDF ocrdoc wrote>`, to improve a result later. The window has no time limit; the
caller waits until it is closed. It keeps no settings of its own and writes nothing outside
`<folder>` (checked with empty home and temporary folders).

## The configuration document: `ocrdoc-config`, version 1

```json
{"format": "ocrdoc-config", "version": 1, "made_with": "ocrdoc 0.2.0",
 "input": {"sha256": "…", "bytes": 245678, "suffix": ".pdf",
           "pages": [{"width": 595.276, "height": 841.89, "frame": "…"}]},
 "options": {"reader": "auto", "languages": null, "tables": true, "structure": true,
             "dpi": 300, "cells": true, "areas": true},
 "reader": "rapidocr",
 "pages": [{"page": 1,
            "filters": {"upscale": 2, "letter_mode": false, "remove_colour": true,
                        "remove_lines": false, "black_white": false, "by": "auto"},
            "ocr": true, "words": [["Kalium", 56.2, 210.4, 89.9, 221.0, 0.998], "…"],
            "layout": {"by": "person", "regions": [
                {"kind": "text", "box": [56.2, 40.0, 536.0, 140.0], "by": "person"},
                {"kind": "table", "box": [56.2, 150.1, 536.0, 451.3], "by": "auto",
                 "columns": [226.2, 296.2, 386.0, 496.0], "rows": [168.4, 186.2, "…"],
                 "merged": [[0, 0, 0, 4]], "confidence": 0.863}]},
            "correction": null}]}
```

Everything that decides the result, and nothing else: no paths, no times. `input` names the file
it belongs to by its SHA-256, and every page's size and frame. `options` are the settings. Per
page: its `filters` (`null` for a page with a text layer of its own; `by` "auto" as ocrdoc
suggested them, "person" once a person chose them), whether it was read by `ocr` (`null`: not
read yet), the `words` OCR read (text, box in points, confidence), its `layout` (`null`: not found
yet; `by` "auto" as ocrdoc found it, "person" once a person changed it), and the person's
`correction` of the page text (`null`: as read). An area has its `kind`, its `box` in points of
the page as shown and who set it (`by`); a table also its inner column lines (`columns`, x) and
row lines (`rows`, y) and its merged cells, each as first row, first column, last row, last
column, counted from 0. Changing the filters of a page drops what OCR read on it and the areas
found there; a person's areas and correction stay.

**The same file and the same document give the same four files, byte for byte**, on the same
version of ocrdoc: the text is made from the words stored (OCR, which is not always
deterministic, does not run again), the tables from the areas stored (Camelot does not run again
either), and the PDF carries no time and a file identifier made from the configuration documents
it carries. A page whose words are not stored yet (a document saved before that page was read) is
read when the result is made. The tests check the bytes for `run`, `run --config` with the
document and with the PDF, and `edit`.

**When the step before changed.** A person may go back to optdoc and change a page (more
contrast); optdoc's PDF, ocrdoc's input, is then another file, and the document's SHA-256 no
longer fits. It is not thrown away. optdoc records every page's **frame** in its own document,
which its PDF carries (`optdoc.json`; from the version of optdoc that comes with ocrdoc on): a fingerprint of the page's geometry (its size, and the
turning, unwarping and straightening that made it). Where a page's frame is the same as the one
the document recorded, what a person decided on it stays (the filters they chose, the areas they
drew, a table grid they set, the text they corrected), and what a machine found is found again
(OCR reads the page anew). Where the frame changed, the page's decisions no longer fit and go;
the answer names the page in `dropped`. An input without frames must be the very file the
document names (`config-mismatch` otherwise).

## Failures

```json
{"interface": 1, "made_with": "ocrdoc 0.2.0", "error": "not-pdf", "details": {},
 "message": {"en": "ocrdoc reads PDFs; optdoc makes one of a photo or an image first.",
             "de": "ocrdoc liest PDFs; aus einem Foto oder Bild macht optdoc zuerst eines."}}
```

A caller decides by `error` and shows `message` in the language of its interface. `details` hold
what the message is made from, never a path or content.

| `error` | when | `details` |
|---|---|---|
| `missing` | the file (or the configuration document, or the bench folder) does not exist | |
| `not-pdf` | not a PDF: a photo or an image, which optdoc prepares first | |
| `unreadable` | the file cannot be read: damaged, empty, or not what its name says | |
| `encrypted` | the PDF needs a password | |
| `unknown-reader` | an engine ocrdoc does not know | `name` |
| `no-reader` | the engine asked for is not installed | `reader` |
| `reader-failed` | the engine failed on a page | `reader` |
| `bad-config` | the document is no readable JSON, not of this version, has no entry for each page, or a value of the wrong kind | `reason`: `json`, `format`, `page`, `field` |
| `config-mismatch` | the document belongs to another file, and no frame says the pages are the same | |
| `not-ocr` | a correction of a page that was not read by OCR (as a library) | `page` |
| `same-as-source` | the PDF would overwrite the document itself | |
| `unwritable` | the folder cannot take the results | |
| `cancelled` | the person cancelled the window; nothing was written | |
| `no-gui` | `edit`, and PySide6 is not installed | |
| `network` | something tried to reach the network; it was stopped | |
| `unknown-model` | `models fetch` names a model ocrdoc does not list | `name` |
| `model-unreachable` | the model's address did not answer, or the download broke off | `name` |
| `model-checksum` | what came is not the file listed (size or SHA-256); nothing was kept | `name` |
| `usage` | the command line is not valid (the usage line goes to standard error) | |
| `internal` | a fault of ocrdoc | `error`: the name of the exception class |

The same kinds and wording are there for programs that use ocrdoc as a Python library:
`ocrdoc.errors.OcrdocError` (`kind`, `details`) and `ocrdoc.errors.describe_error(error, "de")`.

## The reading: `ocrdoc-reading`, version 1

```json
{"format": "ocrdoc-reading", "version": 1, "made_with": "ocrdoc 0.2.0",
 "reader": "rapidocr", "input": {"sha256": "…"},
 "pages": [{"page": 1, "width": 595.28, "height": 841.89, "source": "ocr",
            "text": "Kalium\t5,8\tmmol/l\t3,5 - 5,1\tH\n…", "markdown": "…",
            "words": [{"text": "Kalium", "start": 0, "end": 6,
                       "box": [56.2, 210.4, 89.9, 221.0], "confidence": 0.998, "by": "ocr"}],
            "regions": [{"kind": "text", "box": [56.2, 40.0, 536.0, 140.0], "by": "person"},
                        {"kind": "table", "box": [56.2, 150.1, 536.0, 451.3], "by": "auto",
                         "table": 0}],
            "tables": [{"box": [56.2, 150.1, 536.0, 451.3], "confidence": 0.863, "by": "auto",
                        "rows": [[{"text": "Kalium", "box": [56.2, 208.4, 226.2, 224.4]},
                                  {"text": "5,8", "box": [226.2, 208.4, 296.2, 224.4]},
                                  "…"]]}]}]}
```

The content of optdoc 0.6.0's `optdoc-reading` version 1, without its clean-up `plan` (optdoc's
now) and without the input's file name (a name may name a patient, and the reading belongs to the
PDF beside it); `input` names the input by its SHA-256 instead.

Per page: its size in points, where its text came from (`text` layer or `ocr`), the text, its
Markdown, and every word with its offsets in the text and its `box` as **[left, top, right,
bottom] in points from the top left of the page as shown**, the same page as in the PDF. OCR words
carry the engine's `confidence` (0 to 1) and `by`: `"ocr"`, or `"person"` for a word a person
wrote in the window (confidence 1). In the text, a line of the page is a line; on a page read by
OCR, a gap wider than the words are high (between the cells of a table, or columns) is a tab.

`regions` lists the areas of the page in reading order: `kind` (`text`, `table`, `image`,
`barcode`, `handwriting`, `stamp`, `ignore`), `box`, `by` ("auto" or "person"), for a table the
number of its table in `tables`, and for a barcode ocrdoc read its `format` (as zxing-cpp names
it: "QRCode", "DataMatrix", "Code128", "EAN13" …) and its `content`. A program that covers what a
person marked (a pseudonymiser: handwriting, stamps, barcodes) takes the boxes from here.

`tables` lists the tables of the page in the order of their areas, each with its `box`, the
`confidence` of the automatic finding (0 to 1; 1 for a grid a person set), `by` ("auto" or
"person") and its `rows`, top to bottom, each a list of cells from left to right: `text` (the
words whose middle lies in the cell, lines joined by a space; empty for an empty cell or one
covered by merged cells, of which the first holds the text and the box of all) and `box`, in the
same points as the words. Every row is given once, even where Camelot found a table twice.
`tables` is `[]` when the page has none and `null` when tables were neither looked for nor set by
a person.

## The text layer

On every page read by OCR, the PDF carries the words invisibly where they are printed, one OCR
line as one line of text, with real spaces between the words. Within a cell of a table the space
is stretched over the gap; between two cells (a tab in the reading) the gap stays open, so that a
program finding tables by the gaps between text (Camelot, Tabula) sees the columns. PDFKit's
`PDFPage.string` gives every row of a table as one line, name, value, unit, range and flag in
order. MuPDF gives running text as a line and a table row cell by cell, as it does for a
born-digital table. Each word is scaled to its printed width, so a search or a selection covers
it. Every character is written as it was read, "≤", "↑" and "µ" included; a corrected text is
laid on the same boxes. The tests check this with PDFKit (on macOS) and MuPDF.

## Licence

ocrdoc is free software under the GNU Affero General Public License 3.0 or later; its source is at
https://github.com/fre-ms/ocrdoc. A program that ships it names it and where its source is.
