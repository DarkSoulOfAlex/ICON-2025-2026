"""Costruisce il documento di riferimento per pandoc a partire dal template del docente.

**Perche' serve.** `pandoc --reference-doc` prende dal documento indicato *gli
stili*, non i contenuti: il frontespizio va quindi scritto nel Markdown. Il
problema e' un altro, e non e' evidente finche' non si apre il `.docx` prodotto:
pandoc **riferisce** stili che il template del docente non **definisce**.

In particolare emette `<w:tblStyle w:val="Table"/>` per ogni tabella, ma il
template dichiara solo `TableNormal`. Lo stile riferito non esiste, Word ricade
sul nulla, e le tabelle escono senza alcun filetto e senza intestazione
distinguibile: per una sezione "Valutazione" che e' fatta di tabelle, il
documento risulterebbe illeggibile. Lo stesso vale per `CaptionedFigure` e
`ImageCaption`, senza i quali le didascalie delle figure diventano testo di corpo
indistinguibile dal resto. Pandoc non colma la lacuna da solo: inietta
`SourceCode` e gli stili di colorazione della sintassi, e nient'altro.

**Perche' un file derivato invece di modificare il template.**
`docs/template_docente.docx` e' materiale ricevuto e va lasciato intatto, sia per
poterlo riconfrontare sia perche' e' il riferimento su cui il progetto viene
giudicato. Il file generato qui e' rigenerabile in ogni momento da quello, quindi
non e' una seconda fonte di verita' ma una sua funzione.

Gli stili aggiunti derivano da `Normal` e da `TableNormal` del template, non da
quelli predefiniti di pandoc: cosi' font, corpo e interlinea restano quelli
scelti dal docente e l'aggiunta riguarda solo cio' che manca.

Uso:

    python scripts/prepara_riferimento.py
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

TEMPLATE = Path("docs/template_docente.docx")
RIFERIMENTO = Path("docs/riferimento_pandoc.docx")

# Stili riferiti da pandoc e assenti dal template. I filetti della tabella sono
# solo orizzontali (sopra, sotto, sotto l'intestazione, e leggeri fra le righe):
# e' la convenzione tipografica delle tabelle scientifiche, e su tabelle di
# numeri le linee verticali aggiungono inchiostro senza aggiungere lettura.
STILI_MANCANTI = """
  <w:style w:type="table" w:default="1" w:styleId="Table">
    <w:name w:val="Table"/><w:basedOn w:val="TableNormal"/><w:qFormat/>
    <w:tblPr><w:tblInd w:w="0" w:type="dxa"/>
      <w:tblBorders>
        <w:top w:val="single" w:sz="8" w:space="0" w:color="595959"/>
        <w:bottom w:val="single" w:sz="8" w:space="0" w:color="595959"/>
        <w:insideH w:val="single" w:sz="2" w:space="0" w:color="BFBFBF"/>
      </w:tblBorders>
      <w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>
        <w:bottom w:w="60" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar>
    </w:tblPr>
    <w:tblStylePr w:type="firstRow"><w:rPr><w:b/></w:rPr>
      <w:tcPr><w:tcBorders><w:bottom w:val="single" w:sz="8" w:space="0" w:color="595959"/></w:tcBorders>
      <w:vAlign w:val="bottom"/></w:tcPr></w:tblStylePr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="BodyText">
    <w:name w:val="Body Text"/><w:basedOn w:val="Normal"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="FirstParagraph">
    <w:name w:val="First Paragraph"/><w:basedOn w:val="BodyText"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Compact">
    <w:name w:val="Compact"/><w:basedOn w:val="BodyText"/><w:qFormat/>
    <w:pPr><w:spacing w:before="20" w:after="20"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="CaptionedFigure">
    <w:name w:val="Captioned Figure"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:keepNext/><w:jc w:val="center"/><w:spacing w:before="240" w:after="60"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="ImageCaption">
    <w:name w:val="Image Caption"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:pPr><w:jc w:val="center"/><w:spacing w:before="0" w:after="240"/></w:pPr>
    <w:rPr><w:i/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>
  <w:style w:type="character" w:styleId="VerbatimChar">
    <w:name w:val="Verbatim Char"/><w:basedOn w:val="DefaultParagraphFont"/><w:qFormat/>
    <w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>
      <w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>
"""


def inserisci_stili(styles_xml: str, stili: str = STILI_MANCANTI) -> str:
    """Aggiunge le definizioni in coda al foglio di stili, prima della chiusura.

    Funzione pura, separata dalla lettura dell'archivio, perche' e' la sola parte
    che puo' sbagliare in modo silenzioso: un `</w:styles>` non trovato
    produrrebbe un file valido come zip e rotto come documento.
    """
    if "</w:styles>" not in styles_xml:
        raise ValueError("il foglio di stili non contiene la chiusura </w:styles>")
    return styles_xml.replace("</w:styles>", stili + "</w:styles>")


def prepara(template: Path = TEMPLATE, destinazione: Path = RIFERIMENTO) -> Path:
    """Riscrive il template con gli stili mancanti, lasciandolo intatto."""
    if not template.exists():
        raise FileNotFoundError(f"template assente: {template}")

    with zipfile.ZipFile(template) as archivio:
        # Le voci "[trash]" sono residui dell'editor con cui il template e' stato
        # salvato: inutili a pandoc e potenzialmente sgradite a Word.
        voci = [
            (info, archivio.read(info.filename))
            for info in archivio.infolist()
            if not info.filename.startswith("[trash]")
        ]

    with zipfile.ZipFile(destinazione, "w", zipfile.ZIP_DEFLATED) as archivio:
        for info, dati in voci:
            if info.filename == "word/styles.xml":
                dati = inserisci_stili(dati.decode("utf-8")).encode("utf-8")
            archivio.writestr(info, dati)
    return destinazione


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=TEMPLATE)
    parser.add_argument("--destinazione", type=Path, default=RIFERIMENTO)
    argomenti = parser.parse_args()
    esito = prepara(argomenti.template, argomenti.destinazione)
    print(f"scritto {esito} ({esito.stat().st_size} byte)")


if __name__ == "__main__":
    main()
