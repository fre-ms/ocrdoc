# Changelog

## 0.3.0 (2026-11-27)

Interface 2: one field renamed, in every tool of docrepro at once.

### Changed

- **The answer names the PDF with its text layer `document`**, no longer `pdf` (`run`, and `edit`
  on Apply); `ocrdoc.output.write` returns it under that key. No step of docrepro is to force a
  file type, so a document need not be a PDF, and a field called `pdf` would then point at a
  picture. ocrdoc itself still reads and writes PDFs; that it reads a picture and lays its
  reading beside it is to come. Callers read `document` where they read `pdf`.

## 0.2.0 (2026-11-26)

The way models come as an optional download, a bench for the finders of areas, and barcodes
read once and right. Interface 1 and both formats stay: everything here is added.

### Added

- **`ocrdoc models list`, `ocrdoc models fetch <name> --to <folder>`, `--models <folder>`** for
  `run` and `edit`, and `models` in the answer of `about`: doccor's mechanism (0.2.0), the same in
  every tool of docrepro. `models fetch` is the only command that goes on the network, and only
  when asked; work never does. Kinds of error `unknown-model`, `model-unreachable`,
  `model-checksum`.
- **ocrdoc lists no model yet.** A model is listed only after it did better than the rules it
  would add to. PaddleOCR's layout model PP-DocLayout_plus-L (Apache-2.0, 130 MB), measured on the
  invented letters of the bench, found 6 to 9 of 12 pictures with many areas where none was
  drawn, and none of the 6 stamps, at three times the time per page; the rules found 11 to 12
  pictures. Invented letters are not what it was trained on, so it stays unlisted until a
  measurement on real documents says otherwise.
- **`bench/areas_bench.py`** measures the finders of pictures, barcodes, stamps and handwriting
  on the invented letters of `bench/area_letters.py`, as made, scanned in colour, scanned in
  grey, and photographed and prepared by optdoc; with `--models` what a model gains. The rules,
  found of drawn (found where none was drawn):

  | | as made | colour scan | grey scan | photo |
  |---|---|---|---|---|
  | pictures | 12 of 12 | 12 of 12 | 12 of 12 | 11 of 12 (1) |
  | barcodes, all read right | 17 of 17 | 17 of 17 | 17 of 17 | 17 of 17 |
  | stamps | 6 of 6 | 5 of 6 (1) | 0 of 6 | 6 of 6 |
  | handwriting | 11 of 12 | 11 of 12 | 9 of 12 | 10 of 12 (3) |

### Fixed

- **A barcode found twice counts once, and its content is what most readings say.** On scans the
  same barcode could come twice, once with a wrong content. Now one reading per barcode stays,
  and where two readings of it differ, the cut-out is read again larger and smoothed and the
  majority decides; without a majority the area stays and its content is left empty, never
  guessed.

### Changed

- ocrdoc needs doccor 0.2.

## 0.1.0 (2026-11-26)

ocrdoc comes out of optdoc 0.6.0 with the history of its modules: the recognition, while optdoc
keeps the preparation of the page (`docs/family-design.md` in optdoc says why and how). What
changed in the move:

- **The pages stay as they came.** ocrdoc reads a PDF and lays its text layer over the input's
  pages; it never cleans them up. Photos and images go through optdoc first (error `not-pdf`).
- **Filters for OCR** (`ocrdoc.filters`): upscaling, letter mode, taking coloured ink and ruled
  lines away, black and white, done to ocrdoc's own rendering of a page and never to the
  document; suggested per page (upscaling below 150 dpi, colour taken away above 0.3 % of colour),
  chosen by a person in the window's first tab, kept in the configuration document with who chose
  them. Tesseract's second pass over ruled tables uses them.
- **The configuration document** `<stem>.ocrdoc.json`, format `ocrdoc-config` version 1: the input
  by its SHA-256 and every page's size and frame, the settings, and per page the filters, the
  words OCR read, the areas and the correction. Byte for byte the same result from the same input
  and document, as in optdoc.
- **The chain.** The PDF carries the configuration documents of the steps before (`optdoc.json`)
  as the input had them, with ocrdoc's own (`ocrdoc.json`); its file identifier is made from all of
  them. When the input changed but a page's frame (recorded by optdoc) did not, what a person
  decided on the page stays and what a machine found is found again; pages whose frame changed are
  named (`dropped`). An input without frames must be the very file (`config-mismatch`).
- **The reading** is format `ocrdoc-reading` version 1: optdoc's `optdoc-reading` 1 without the
  clean-up plan and without the input's file name; `input` names it by its SHA-256.
- **The command line** has the verbs of every tool of docrepro: `about` (optdoc's `readers`,
  fields `readers`, `filters`, `tables`, `barcodes`, `window`), `run` (optdoc's `prepare`), `edit`,
  and `bench` (PDFs only). Interface 1 (`docs/interface.md`); the answer has `filtered`, `dropped`
  and `carried`.
- **Settings** from the environment are `OCRDOC_OCR`, `OCRDOC_TESSERACT`,
  `OCRDOC_TESSERACT_LANGUAGES`.
- The window's words name the tool by a placeholder, so that the words of several tools can live
  in one program; the kinds of error two tools share are worded alike.
- No standalone program of its own: one program with every tool inside comes with docrepro.

The history of the code before the move is in optdoc's changelog up to 0.6.0:
https://github.com/fre-ms/optdoc/blob/v0.6.0/CHANGELOG.md
