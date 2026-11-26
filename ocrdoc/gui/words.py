"""Every word ocrdoc's window shows, in English and German, registered with the words of
doccor (:mod:`doccor.gui.words`), which give them in the language of the application that
opens the window (``--language``), else that of the system.  A tool's name is a
placeholder (``{tool}``), so that the words of several tools can live in one program.  An
error has its own two languages (:func:`ocrdoc.errors.describe_error`).
"""

from __future__ import annotations

from doccor.gui import words as _words
from doccor.gui.words import LANGUAGES, Words, system_language

WORDS: dict[str, tuple[str, str]] = {  # key: (English, German)
    "title": ("{tool}: {name}", "{tool}: {name}"),
    "page": ("Page {number}", "Seite {number}"),
    "page_corrected": ("Page {number} ✎", "Seite {number} ✎"),
    "tab_filters": ("1 Filters", "1 Filter"),
    "tab_regions": ("2 Areas", "2 Bereiche"),
    "tab_text": ("3 Check the text", "3 Text prüfen"),
    "apply": ("Apply", "Übernehmen"),
    "later": ("Save and continue later", "Speichern und später weitermachen"),
    "cancel": ("Cancel", "Abbrechen"),
    "discard_title": ("Discard the work?", "Arbeit verwerfen?"),
    "discard_text": ("Nothing will be written. Discard what was done in this window?",
                     "Es wird nichts geschrieben. Das in diesem Fenster Getane verwerfen?"),
    "reading_page": ("Reading page {number} of {total} …", "Lese Seite {number} von {total} …"),
    "read_all": ("Every page read.", "Alle Seiten gelesen."),
    "failed": ("That did not work: {error}", "Das ging nicht: {error}"),
    # filters
    "filters_page": ("The page as it is (it stays so in the PDF)",
                     "Die Seite, wie sie ist (so bleibt sie im PDF)"),
    "filters_ocr": ("As OCR reads it (the filters change only this copy; Shift/Option + drag "
                    "moves both views)",
                    "So liest sie die Texterkennung (die Filter ändern nur diese Kopie; "
                    "Umschalt/Option + Ziehen verschiebt beide Ansichten)"),
    "filters": ("Filters for OCR on this page", "Filter für die Texterkennung dieser Seite"),
    "upscale": ("Upscale", "Hochskalieren"),
    "not": ("not", "nicht"),
    "upscale_tip": ("OCR reads the page at that multiple of the resolution (up to 4×, at most "
                    "9000 pixels): for scans and photos of low resolution.",
                    "Die Texterkennung liest die Seite mit dem Vielfachen der Auflösung (bis 4×, "
                    "höchstens 9000 Pixel): für Scans und Fotos geringer Auflösung."),
    "letter_mode": ("Letter mode: grey, strokes sharpened",
                    "Buchstabenmodus: grau, Striche geschärft"),
    "letter_mode_tip": ("Sharpens the strokes in grey, best with upscaling. A hard black-and-white "
                        "threshold made recognition much worse in measurements, so the image "
                        "stays grey.",
                        "Schärft die Striche in Graustufen, am besten mit Hochskalieren. Eine "
                        "harte Schwarz-Weiß-Schwelle verschlechterte die Erkennung in Messungen "
                        "deutlich, deshalb bleibt das Bild grau."),
    "remove_colour": ("Take coloured ink away (stamps, highlighter, blue signatures)",
                      "Farbige Tinte wegnehmen (Stempel, Marker, blaue Unterschriften)"),
    "remove_colour_tip": ("Coloured ink becomes white, so that it hides no print beneath it; the "
                          "stamp stays in the document and is found as an area.",
                          "Farbige Tinte wird weiß, damit sie keinen Druck darunter verdeckt; der "
                          "Stempel bleibt im Dokument und wird als Bereich erkannt."),
    "remove_lines": ("Take ruled lines away (forms, tables)",
                     "Linien wegnehmen (Formulare, Tabellen)"),
    "remove_lines_tip": ("Long horizontal and vertical lines become white; the grid of a table "
                         "is found all the same.",
                         "Lange waagrechte und senkrechte Linien werden weiß; das Gitter einer "
                         "Tabelle wird trotzdem erkannt."),
    "black_white": ("Black and white", "Schwarz-Weiß"),
    "black_white_tip": ("An adaptive threshold; not with letter mode, where it read worse.",
                        "Eine anpassende Schwelle; nicht im Buchstabenmodus, wo sie schlechter "
                        "las."),
    "restore": ("Restore the suggestion", "Vorschlag wiederherstellen"),
    "no_filters": ("No filter on this page", "Kein Filter auf dieser Seite"),
    "to_all": ("Copy the filters to every page", "Filter auf alle Seiten übertragen"),
    "filters_suggested": ("The filters {tool} suggests for this page.",
                          "Die Filter, die {tool} für diese Seite vorschlägt."),
    "filters_chosen": ("Filters chosen by hand; the page is read again.",
                       "Von Hand gewählte Filter; die Seite wird neu gelesen."),
    "filters_none_needed": ("This page has a text layer of its own; it is read as it is, "
                            "without OCR.",
                            "Diese Seite hat eine eigene Textebene; sie wird gelesen, wie sie ist, "
                            "ohne Texterkennung."),
    "no_opencv": ("Filters need OpenCV and NumPy (extra 'ocr').",
                  "Filter brauchen OpenCV und NumPy (Extra „ocr“)."),
    # text
    "page_image": ("The page as OCR read it (click a word to find it in the text; yellow: "
                   "read with little confidence)",
                   "Die Seite, wie die Texterkennung sie gelesen hat (Klick auf ein Wort findet "
                   "es im Text; gelb: unsicher gelesen)"),
    "text_ocr": ("Recognised text, to be corrected by hand. A gap between table cells is a tab; "
                 "the correction goes into the PDF's text layer, the reading and the Markdown.",
                 "Erkannter Text, von Hand zu berichtigen. Eine Lücke zwischen Tabellenzellen ist "
                 "ein Tabulator; die Berichtigung kommt in die Textebene des PDFs, die Lesung "
                 "und das Markdown."),
    "text_layer": ("Text of the text layer (cannot be changed)",
                   "Text der Textebene (nicht veränderbar)"),
    "text_none": ("No text on this page.", "Kein Text auf dieser Seite."),
    "reset_text": ("Back to the OCR text", "Auf den erkannten Text zurücksetzen"),
    "corrected": ("corrected", "berichtigt"),
    "as_read": ("as read", "wie gelesen"),
    "uncertain": ("{n} word(s) read with little confidence", "{n} Wort/Wörter unsicher gelesen"),
    "zoom_reset": ("1:1", "1:1"),
    # areas
    "kind_text": ("Text", "Text"),
    "kind_table": ("Table", "Tabelle"),
    "kind_image": ("Picture", "Bild"),
    "kind_barcode": ("Barcode", "Barcode"),
    "kind_handwriting": ("Handwriting", "Handschrift"),
    "kind_stamp": ("Stamp", "Stempel"),
    "kind_ignore": ("Do not read", "Nicht lesen"),
    "kind": ("Kind of the area selected", "Art des ausgewählten Bereichs"),
    "kind_tip": ("Gives the area selected another kind",
                 "Gibt dem ausgewählten Bereich eine andere Art"),
    "tools": ("Tools", "Werkzeuge"),
    "tool_select": ("Select, move, resize; drag a table's lines",
                    "Auswählen, verschieben, Größe ändern; Tabellenlinien ziehen"),
    "tool_draw": ("Draw an area", "Bereich zeichnen"),
    "tool_column": ("Add a column line (click in the table)",
                    "Spaltenlinie einfügen (in die Tabelle klicken)"),
    "tool_row": ("Add a row line (click in the table)",
                 "Zeilenlinie einfügen (in die Tabelle klicken)"),
    "tool_remove": ("Remove a line (click on it)", "Linie entfernen (darauf klicken)"),
    "tool_merge": ("Merge cells (drag over them) or split them (click)",
                   "Zellen verbinden (darüber ziehen) oder trennen (klicken)"),
    "delete_region": ("Delete the area", "Bereich löschen"),
    "find_again": ("Find the areas again", "Bereiche neu erkennen"),
    "regions_help": ("What is in no area is read as text. Pictures, barcodes and areas not to "
                     "be read stay out of the text; handwriting and stamps are read and marked. "
                     "The numbers are the order of reading. Delete or Backspace deletes the area "
                     "selected, Escape goes back to selecting.",
                     "Was in keinem Bereich liegt, wird als Text gelesen. Bilder, Barcodes und "
                     "Bereiche, die nicht gelesen werden sollen, bleiben aus dem Text; "
                     "Handschrift und Stempel werden gelesen und markiert. Die Nummern sind die "
                     "Lesereihenfolge. Entf oder Rückschritt löscht den ausgewählten Bereich, "
                     "Escape kehrt zum Auswählen zurück."),
    "regions_auto": ("Areas found by {tool}: {count}", "Von {tool} erkannte Bereiche: {count}"),
    "regions_person": ("Areas set by hand: {count}", "Von Hand gesetzte Bereiche: {count}"),
    "regions_table": ("Table selected: {rows} rows, {columns} columns",
                      "Ausgewählte Tabelle: {rows} Zeilen, {columns} Spalten"),
    "regions_barcode": ("Barcode selected ({format}): {content}",
                        "Ausgewählter Barcode ({format}): {content}"),
    "regions_no_tables": ("Tables are not found automatically here (extra 'tables' or "
                          "--no-cells); they can be drawn.",
                          "Tabellen werden hier nicht automatisch erkannt (Extra „tables“ oder "
                          "--no-cells); sie lassen sich zeichnen."),
    "finding_regions": ("Finding the areas of page {number} …",
                        "Erkenne die Bereiche auf Seite {number} …"),
}

_words.register(WORDS)
__all__ = ["LANGUAGES", "WORDS", "Words", "system_language"]
