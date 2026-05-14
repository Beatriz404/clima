"""
Genera artefactos de documentación en la raíz del proyecto:

1. DOCUMENTACION_FUNCIONAMIENTO_print.html — abrir en el navegador y «Guardar como PDF» (Ctrl+P).
2. DOCUMENTACION_FUNCIONAMIENTO.pdf — si está instalado fpdf2 y hay fuente TTF (DejaVu o Arial).

Uso (desde la raíz del repo clima):

    pip install -r requirements.txt
    python scripts/publicar_documentacion.py
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "DOCUMENTACION_FUNCIONAMIENTO.md"
HTML_OUT = ROOT / "DOCUMENTACION_FUNCIONAMIENTO_print.html"
PDF_OUT = ROOT / "DOCUMENTACION_FUNCIONAMIENTO.pdf"


def _fuente_ttf() -> tuple[str, str] | None:
    candidatos = [
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for p in candidatos:
        if p.is_file():
            return str(p), "DocUnicode"
    try:
        import fpdf
        from glob import glob

        base = Path(fpdf.__file__).resolve().parent
        found = sorted(glob(str(base / "**" / "DejaVuSans.ttf"), recursive=True))
        if found:
            return found[0], "DejaVu"
    except Exception:
        pass
    return None


def _limpiar_md_linea(texto: str) -> str:
    t = texto.replace("**", "")
    t = re.sub(r"`([^`]+)`", r"\1", t)
    return t


def escribir_html_impresion(texto_md: str) -> None:
    esc = html.escape(texto_md)
    body = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Documentación — Clima Agrícola El Salvador</title>
  <style>
    body {{ font-family: "Segoe UI", system-ui, sans-serif; margin: 24px; max-width: 900px; color: #222; }}
    h1 {{ font-size: 1.25rem; }}
    @media print {{
      body {{ margin: 12mm; max-width: none; }}
      .no-print {{ display: none; }}
    }}
    pre.doc {{
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 10.5pt;
      line-height: 1.4;
      background: #fafafa;
      padding: 16px;
      border: 1px solid #ddd;
      border-radius: 8px;
    }}
  </style>
</head>
<body>
  <p class="no-print"><strong>PDF:</strong> use <kbd>Ctrl+P</kbd> (o Cmd+P) y elija <strong>Guardar como PDF</strong>.</p>
  <pre class="doc">{esc}</pre>
</body>
</html>"""
    HTML_OUT.write_text(body, encoding="utf-8")
    print(f"OK HTML: {HTML_OUT}")


def intentar_pdf(texto_md: str) -> bool:
    try:
        from fpdf import FPDF
    except ImportError:
        print("Aviso: fpdf2 no instalado; omito PDF. Ejecute: pip install fpdf2", file=sys.stderr)
        return False

    info = _fuente_ttf()
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    if info:
        ruta, familia = info
        pdf.add_font(familia, "", ruta, uni=True)
        nombre = familia
    else:
        pdf.set_font("Helvetica", "", 10)
        nombre = "Helvetica"

    def set_size(pt: int) -> None:
        pdf.set_font(nombre, "", pt)

    for raw in texto_md.splitlines():
        linea = raw.rstrip()
        if not linea.strip():
            pdf.ln(3)
            continue
        if linea.strip() == "---":
            pdf.ln(2)
            continue
        if linea.startswith("|") and re.search(r"-{3,}", linea):
            continue

        texto = _limpiar_md_linea(linea)

        if linea.startswith("# "):
            set_size(15)
            pdf.multi_cell(0, 9, texto[2:].strip())
            pdf.ln(2)
            continue
        if linea.startswith("## "):
            set_size(12)
            pdf.multi_cell(0, 8, texto[3:].strip())
            pdf.ln(1)
            continue
        if linea.startswith("### "):
            set_size(11)
            pdf.multi_cell(0, 7, texto[4:].strip())
            continue
        if linea.startswith("#### "):
            set_size(10)
            pdf.multi_cell(0, 6, texto[5:].strip())
            continue
        if linea.startswith("|"):
            set_size(9)
            pdf.multi_cell(0, 5, texto.replace("|", "  "))
            continue
        set_size(10)
        pdf.multi_cell(0, 6, texto)

    pdf.output(str(PDF_OUT))
    print(f"OK PDF: {PDF_OUT}")
    return True


def main() -> int:
    if not MD.is_file():
        print(f"No existe {MD}", file=sys.stderr)
        return 1
    texto = MD.read_text(encoding="utf-8")
    escribir_html_impresion(texto)
    intentar_pdf(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
