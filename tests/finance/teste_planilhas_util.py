"""Ajuda dos testes de planilhas: monta um .xlsx mínimo sem biblioteca externa."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import zipfile


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def xlsx(abas: dict, datas_na_coluna: dict = None) -> bytes:
    """Monta um .xlsx mínimo. Células int/float viram números; str, texto em linha; objetos ('data', n) viram datas (estilo 1); ('pct', x) viram porcentagem (estilo 2)."""
    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    nomes = list(abas)
    z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
               + "".join(f'<sheet name="{esc(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(nomes)) + "</sheets></workbook>")
    z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               + "".join(f'<Relationship Id="rId{i + 1}" Type="x" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(nomes))) + "</Relationships>")
    z.writestr("xl/styles.xml", '<?xml version="1.0"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs count="3">'
               '<xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="10"/></cellXfs></styleSheet>')
    for i, n in enumerate(nomes):
        linhas = []
        for r, lin in enumerate(abas[n], 1):
            cel = []
            for c, v in enumerate(lin):
                ref = "ABCDEFGHIJ"[c] + str(r)
                if isinstance(v, tuple) and v[0] == "data":
                    cel.append(f'<c r="{ref}" s="1"><v>{v[1]}</v></c>')
                elif isinstance(v, tuple) and v[0] == "pct":
                    cel.append(f'<c r="{ref}" s="2"><v>{v[1]}</v></c>')
                elif isinstance(v, (int, float)):
                    cel.append(f'<c r="{ref}"><v>{v}</v></c>')
                else:
                    cel.append(f'<c r="{ref}" t="inlineStr"><is><t>{esc(v)}</t></is></c>')
            linhas.append(f'<row r="{r}">{"".join(cel)}</row>')
        z.writestr(f"xl/worksheets/sheet{i + 1}.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   + "".join(linhas) + "</sheetData></worksheet>")
    z.close()
    return buf.getvalue()
