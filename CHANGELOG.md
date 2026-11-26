# Changelog

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
