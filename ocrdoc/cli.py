"""The command line: ``ocrdoc about``, ``ocrdoc run``, ``ocrdoc edit`` (the window) and
``ocrdoc bench``.

Every command answers with exactly one JSON object on standard output, whether it
succeeds or fails, so that programs in any language can call ocrdoc as a helper (a
Tauri sidecar, for one).  ``docs/interface.md`` describes the answers; they carry the
version of that description as ``interface``.  A failure answers with its kind
(:mod:`ocrdoc.errors`) and its message in English and German, and ends with exit status
2.  No answer and no message quotes a document or its path, and ``bench`` names no file
at all.  ``--progress`` writes a line of JSON per page to standard error.  ``run`` and
``edit`` take a configuration document (``--config``) and make the same result from it
every time (:mod:`ocrdoc.project`).

The command line keeps the manners every tool of docrepro keeps (:mod:`doccor.cli`): one
JSON answer whatever happens, standard error for its own lines, and never the network
(:mod:`doccor.offline`).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from doccor import cli as frame
from doccor import models as modelstore

from ocrdoc import __version__, areas, filters, tables
from ocrdoc import ocr as ocrlib
from ocrdoc.errors import OcrdocError
from ocrdoc.models import CATALOGUE
from ocrdoc.project import SUFFIX, Options, Project, load_config

INTERFACE = 1  # the version of docs/interface.md the answers follow
TOOL = "ocrdoc"


def _about(args: argparse.Namespace) -> dict[str, Any]:
    """What this installation can do."""
    from ocrdoc import gui

    return {"version": __version__, "readers": ocrlib.available_backends(),
            "filters": filters.available(), "tables": tables.available(),
            "barcodes": areas.barcodes_available(), "window": gui.available(),
            "models": modelstore.listing(CATALOGUE)}


# the options that decide the result; with --config the configuration decides them
_SETTINGS = ("reader", "languages", "no_tables", "no_structure", "no_areas")


def _project(args: argparse.Namespace) -> Project:
    """The project on the file: from its configuration document (``--config``, a JSON
    file or a PDF ocrdoc wrote), or fresh with the options given.  Both at once is a
    "usage"."""
    if args.config is not None:
        if any(getattr(args, name) is not None for name in _SETTINGS):
            raise OcrdocError("usage")
        project = Project.open(args.file, config=load_config(args.config))
        project.scratch = _out(args)  # nothing of the document anywhere but there
        project.models = args.models
        if args.no_cells:  # as before the configuration held it: no tables found
            project.leave_out_found_tables()
        return project
    options = Options(reader=args.reader or "auto", languages=args.languages,
                      tables=not args.no_tables, structure=not args.no_structure,
                      cells=not args.no_cells, areas=not args.no_areas)
    project = Project.open(args.file, options)
    project.scratch = _out(args)  # nothing of the document anywhere but there
    project.models = args.models
    return project


def _out(args: argparse.Namespace) -> Path:
    """The folder for the results: ``--out``, else ``<file>.ocrdoc`` beside the file."""
    return args.out or args.file.with_name(f"{args.file.stem}.ocrdoc")


def _results(project: Project, args: argparse.Namespace) -> dict[str, Any]:
    """Make the result of a project, write it, and sum it up."""
    from ocrdoc import output

    reading = project.build(frame.progress if args.progress else None)
    try:
        paths = output.write(reading, _out(args))
        return {
            **{k: str(v) for k, v in paths.items()},
            "pages": len(reading.pages),
            "ocr_pages": [s.number + 1 for s in reading.pages if s.ocr],
            "pages_without_text": [n + 1 for n in reading.without_text],
            "filtered": [n + 1 for n in range(len(project.pages))
                         if (f := project.filters(n)) is not None and f.active],
            "corrected": [n + 1 for n in project.corrected],
            "dropped": [n + 1 for n in project.dropped],
            "reader": reading.reader,
            "tables": (None if reading.tables is None
                       else sum(len(t) for t in reading.tables.values())),
            "carried": sorted(reading.carried),
        }
    finally:
        reading.close()


def _run(args: argparse.Namespace) -> dict[str, Any]:
    """Read the file (or read it again from its configuration) and write the results."""
    project = _project(args)
    try:
        return _results(project, args)
    finally:
        project.close()


def _edit(args: argparse.Namespace) -> dict[str, Any]:
    """Open the window on the file; write the results when the person applies, the
    configuration alone when they will continue later, nothing when they cancel."""
    from ocrdoc import gui

    if not gui.available():
        raise OcrdocError("no-gui")
    from ocrdoc.gui.app import edit

    project = _project(args)
    try:
        outcome = edit(project, language=args.language, self_test=args.self_test)
        if outcome == "cancelled":
            raise OcrdocError("cancelled")
        if outcome == "saved":
            saved = project.save(_out(args) / f"{args.file.stem}{SUFFIX}")
            return {"config": str(saved), "finished": False,
                    "dropped": [n + 1 for n in project.dropped]}
        return {**_results(project, args), "finished": True}
    finally:
        project.close()


def _bench(args: argparse.Namespace) -> dict[str, Any]:
    """Score the documents of a bench folder; numbers only."""
    from ocrdoc.bench import bench, documents_in

    if not args.folder.is_dir():
        raise OcrdocError("missing")
    result = bench(args.folder, args.reader).as_dict()
    return {"documents_found": len(documents_in(args.folder)), **result}


def _document_options(pr: argparse.ArgumentParser) -> None:
    """The options of run and edit.  The settings default to None, so that the use of one
    beside ``--config`` can be told."""
    pr.add_argument("file", type=Path, help="a PDF (a page optdoc prepared, a scan, any PDF)")
    pr.add_argument("--out", type=Path, help="folder for the results (default: <file>.ocrdoc/)")
    pr.add_argument("--config", type=Path,
                    help="configuration to start from: <name>.ocrdoc.json, or a PDF ocrdoc wrote")
    pr.add_argument("--reader", choices=["auto", "rapidocr", "tesseract", "none"],
                    help="OCR engine (default: auto)")
    pr.add_argument("--languages", help="language packs: deu+eng for Tesseract, de for RapidOCR")
    pr.add_argument("--no-tables", action="store_const", const=True,
                    help="no second pass for table grids (Tesseract)")
    pr.add_argument("--no-structure", action="store_const", const=True,
                    help="raw OCR lines, no Markdown")
    pr.add_argument("--no-cells", action="store_true",
                    help="find no tables with their cells (extra 'tables'); "
                         "a person can still set them in the window")
    pr.add_argument("--no-areas", action="store_const", const=True,
                    help="find no barcodes, stamps, pictures or handwriting; "
                         "a person can still set them in the window")
    frame.add_models_option(pr)
    pr.add_argument("--progress", action="store_true",
                    help='a line {"page": n, "of": m} on standard error per page')


def _parser() -> argparse.ArgumentParser:
    """The argument parser."""
    p = frame.Parser(prog=TOOL,
                     description="Recognise what is on the pages of a PDF: areas, text, "
                                 "tables, barcodes.")
    p.add_argument("--version", action="version", version=f"{TOOL} {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("about", help="what this installation can do: OCR engines, finders, window")
    ru = sub.add_parser("run", help="read a PDF and write the results")
    _document_options(ru)
    ed = sub.add_parser("edit", help="open the window: check the areas, correct the text")
    _document_options(ed)
    ed.add_argument("--language", choices=["de", "en"],
                    help="language of the window (default: the system's)")
    ed.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    frame.add_models(sub, TOOL)
    be = sub.add_parser("bench", help="score readings against truth files (numbers only)")
    be.add_argument("folder", type=Path, help="PDFs with a <name>.truth.txt next to each")
    be.add_argument("--reader", action="append", choices=["rapidocr", "tesseract"],
                    help="engine to score; repeatable (default: every installed engine)")
    return p


COMMANDS: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
    "about": _about, "run": _run, "edit": _edit, "bench": _bench,
    "models": frame.models_command(CATALOGUE, TOOL)}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status."""
    return frame.main(_parser(), COMMANDS, tool=TOOL, version=__version__,
                      interface=INTERFACE, argv=argv)
