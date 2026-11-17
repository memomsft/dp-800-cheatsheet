#!/usr/bin/env python3
"""Genera la versión en inglés (en/) a partir de las páginas en español.

Las páginas en español (index.html, referencia.html) son la fuente. Este script:
  1. extrae el texto traducible (bloques de texto con su marcado en línea, atributos
     title/aria-label/placeholder/alt, <title>, meta description y comentarios de
     los bloques de código) SIN tocar el resto del archivo (CSS, JS, estructura);
  2. sustituye cada fragmento por su traducción de i18n/en.<pagina>.json
     (diccionario «fragmento en español» -> «fragmento en inglés»);
  3. aplica unos pocos reemplazos fijos (idioma, enlaces, textos del JS).

Uso:
  python3 i18n/build.py build [-v]       # genera en/*.html (-v: detalle de avisos)
  python3 i18n/build.py todo [pagina]    # lista los fragmentos sin traducir (JSON)
  python3 i18n/build.py import <pagina> <lista.json>
                                         # añade traducciones: lista EN en el mismo orden que `todo`
  python3 i18n/build.py check            # cobertura y validación de marcado
"""
import json
import re
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = Path(__file__).resolve().parent

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK = {"html", "head", "body", "main", "header", "footer", "nav", "section", "article", "aside", "div", "p", "ul", "ol", "li",
         "dl", "dt", "dd", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "figure", "figcaption", "h1", "h2",
         "h3", "h4", "h5", "h6", "blockquote", "details", "summary", "form", "fieldset", "legend", "button", "label", "title",
         "option", "select", "textarea"}
SKIP = {"script", "style", "svg", "pre", "noscript", "template"}
NOTEXT = {"code", "kbd", "svg", "samp", "var"}
ATTRS = ("title", "aria-label", "placeholder", "alt")
WORD = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")
COMMENT_RE = {
    "sql": re.compile(r"--[ \t]*([^\n]*)"),
    "hash": re.compile(r"(?:^|[ \t])#[ \t]*([^\n]*)"),
    "slash": re.compile(r"(?:^|[ \t])//[ \t]*([^\n]*)"),
}
LANG_COMMENT = {"sql": "sql", "tsql": "sql", "bash": "hash", "sh": "hash", "shell": "hash", "powershell": "hash", "pwsh": "hash",
                "yaml": "hash", "yml": "hash", "json": "slash", "jsonc": "slash", "js": "slash", "javascript": "slash",
                "csharp": "slash", "cs": "slash"}


class Node:
    __slots__ = ("tag", "s", "oe", "ce", "e", "kids", "attrs")

    def __init__(self, tag, s, oe, ce, e, attrs=()):
        self.tag, self.s, self.oe, self.ce, self.e, self.attrs = tag, s, oe, ce, e, dict(attrs)
        self.kids = []


class Tree(HTMLParser):
    def __init__(self, src):
        super().__init__(convert_charrefs=False)
        self.src = src
        self.ls = [0] + [m.end() for m in re.finditer("\n", src)]
        self.root = Node("#root", 0, 0, len(src), len(src))
        self.stack = [self.root]
        self.feed(src)
        self.close()
        for n in self.stack[1:]:
            n.ce = n.e = len(src)

    def pos(self):
        line, col = self.getpos()
        return self.ls[line - 1] + col

    def handle_starttag(self, tag, attrs):
        s = self.pos()
        oe = s + len(self.get_starttag_text())
        n = Node(tag, s, oe, None, None, attrs)
        self.stack[-1].kids.append(n)
        if tag in VOID:
            n.ce = n.e = oe
        else:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        s = self.pos()
        oe = s + len(self.get_starttag_text())
        self.stack[-1].kids.append(Node(tag, s, oe, oe, oe, attrs))

    def handle_endtag(self, tag):
        s = self.pos()
        e = self.src.index(">", s) + 1
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                n = self.stack[i]
                n.ce, n.e = s, e
                for m in self.stack[i + 1:]:
                    m.ce = m.e = s
                del self.stack[i:]
                return

    def _opaque(self, tag, end_marker):
        s = self.pos()
        e = self.src.index(end_marker, s) + len(end_marker)
        self.stack[-1].kids.append(Node(tag, s, e, e, e))

    def handle_comment(self, data):
        self._opaque("#comment", "-->")

    def handle_decl(self, decl):
        self._opaque("#decl", ">")

    def handle_pi(self, data):
        self._opaque("#pi", ">")


def visible_text(src, n):
    """Texto visible de un nodo, sin contar code/kbd/svg."""
    out, pos = [], n.oe
    for k in n.kids:
        out.append(src[pos:k.s])
        if k.tag not in NOTEXT and k.tag not in SKIP and not k.tag.startswith("#"):
            out.append(visible_text(src, k))
        pos = k.e
    out.append(src[pos:n.ce])
    return "".join(out)


def skipped(n):
    """Elementos que no se traducen: translate="no" o con atributo lang propio (p. ej. el selector de idioma)."""
    return n.attrs.get("translate") == "no" or (n.tag != "html" and "lang" in n.attrs)


def has_words(src, items):
    for it in items:
        if it[0] == "t":
            txt = unescape(src[it[1]:it[2]])
        else:
            n = it[1]
            if n.tag in NOTEXT or n.tag in SKIP or n.tag.startswith("#") or skipped(n):
                continue
            txt = unescape(visible_text(src, n))
        if WORD.search(txt):
            return True
    return False


def is_empty_inline(src, n):
    return n.tag not in SKIP and not n.tag.startswith("#") and not src[n.oe:n.ce].strip() and not n.kids


def extract(src):
    """Devuelve la lista ordenada de unidades traducibles: (inicio, fin, tipo, texto)."""
    root = Tree(src).root
    units = []

    def attr_units(n):
        raw = src[n.s:n.oe]
        for a in ATTRS + (("content",) if n.tag == "meta" and n.attrs.get("name") == "description" else ()):
            if a in n.attrs and WORD.search(unescape(n.attrs[a] or "")):
                m = re.search(r"(?<![\w-])" + re.escape(a) + r"\s*=\s*(\"([^\"]*)\"|'([^']*)')", raw)
                if m:
                    g = 2 if m.group(2) is not None else 3
                    units.append((n.s + m.start(g), n.s + m.end(g), "a", m.group(g)))

    def code_units(pre):
        code = next((k for k in pre.kids if k.tag == "code"), None)
        if not code:
            return
        cls = code.attrs.get("class", "") or ""
        lang = next((LANG_COMMENT[c.split("-", 1)[1]] for c in cls.split() if "-" in c and c.split("-", 1)[1] in LANG_COMMENT), None)
        if not lang or code.kids:
            return
        body = src[code.oe:code.ce]
        for m in COMMENT_RE[lang].finditer(body):
            txt = m.group(1).rstrip()
            if WORD.search(unescape(txt)):
                units.append((code.oe + m.start(1), code.oe + m.start(1) + len(txt), "c", txt))

    def walk(n):
        if n.tag in SKIP:
            if n.tag == "pre":
                code_units(n)
            return
        if n.tag != "#root" and skipped(n):
            return
        if n.tag != "#root":
            attr_units(n)
        pos, run, runs = n.oe, [], []

        def flush():
            if run:
                runs.append(list(run))
                run.clear()

        kids_blocks = []
        for k in n.kids:
            if k.s > pos:
                run.append(("t", pos, k.s))
            if k.tag.startswith("#"):
                flush()
            elif k.tag in BLOCK or k.tag in ("script", "style", "pre"):
                flush()
                kids_blocks.append(k)
                runs.append(("b", k))
            else:
                run.append(("n", k))
            pos = k.e
        if n.ce is not None and n.ce > pos:
            run.append(("t", pos, n.ce))
        flush()
        for r in runs:
            if r and r[0] == "b":
                walk(r[1])
            else:
                emit(r)

    def emit(run):
        items = list(run)
        # recorta svg y elementos vacíos al inicio/final, y espacios
        def trivial(it):
            return (it[0] == "t" and not src[it[1]:it[2]].strip()) or (
                it[0] == "n" and (it[1].tag == "svg" or skipped(it[1]) or is_empty_inline(src, it[1])))
        def inline_attrs(it):
            # atributos de elementos en línea que quedan FUERA del fragmento (p. ej. <input placeholder>, <meta content>)
            if it[0] != "n":
                return
            stack = [it[1]]
            while stack:
                m = stack.pop()
                if m.tag in SKIP or m.tag.startswith("#") or skipped(m):
                    continue
                attr_units(m)
                stack.extend(m.kids)

        while items and trivial(items[0]):
            inline_attrs(items.pop(0))
        while items and trivial(items[-1]):
            inline_attrs(items.pop())
        if not items or not has_words(src, items):
            for it in items:
                inline_attrs(it)
            return
        s = items[0][1] if items[0][0] == "t" else items[0][1].s
        e = items[-1][2] if items[-1][0] == "t" else items[-1][1].e
        while s < e and src[s].isspace():
            s += 1
        while e > s and src[e - 1].isspace():
            e -= 1
        units.append((s, e, "t", src[s:e]))

    walk(root)
    units.sort()
    # los atributos de elementos en línea pueden repetirse al recorrer; elimina duplicados exactos
    seen, out = set(), []
    for u in units:
        if (u[0], u[1]) not in seen:
            seen.add((u[0], u[1]))
            out.append(u)
    return out


TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)")


def skeleton(fragment):
    """Marcado de un fragmento: secuencia de etiquetas y contenido de <code>."""
    tags = [(m.group(1), m.group(2).lower()) for m in TAG_RE.finditer(fragment)]
    codes = re.findall(r"<code[^>]*>(.*?)</code>", fragment, flags=re.S)
    return tags, codes


# --------------------------------------------------------------------------------------------
# Configuración por página
# --------------------------------------------------------------------------------------------
LANG_LINK_ES = '<a class="tbtn lang" id="lang" href="en/" data-base="en/" hreflang="en" lang="en" title="English version"><svg class="ic"><use href="#g-globe"/></svg>EN</a>'
LANG_LINK_EN = '<a class="tbtn lang" id="lang" href="../" data-base="../" hreflang="es" lang="es" title="Versión en español"><svg class="ic"><use href="#g-globe"/></svg>ES</a>'

PAGES = {
    "index": {
        "src": "index.html",
        "out": "en/index.html",
        "dict": "en.index.json",
        "raw": [
            ('<html lang="es">', '<html lang="en">', 1),
            (LANG_LINK_ES, LANG_LINK_EN, 1),
            ('href="referencia.html"', 'href="../referencia.html"', 1),
            ("b.textContent='Copiado ✓'", "b.textContent='Copied ✓'", 1),
            ("shown+' de '+rows.length+' pistas':rows.length+' pistas'", "shown+' of '+rows.length+' clues':rows.length+' clues'", 1),
        ],
    },
}


def load_dict(page):
    p = I18N / PAGES[page]["dict"]
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def translate(page, strict=False):
    cfg = PAGES[page]
    src = (ROOT / cfg["src"]).read_text(encoding="utf-8")
    d = load_dict(page)
    units = extract(src)
    out, pos, missing, bad, info = [], 0, [], [], []
    for s, e, kind, es in units:
        en = d.get(es)
        if en is None:
            missing.append(es)
            en = es
        elif kind == "t":
            (tes, ces), (ten, cen) = skeleton(es), skeleton(en)
            if tes != ten:
                bad.append((es, en))
            elif ces != cen:
                info.append((es, en))
        out.append(src[pos:s])
        out.append(en)
        pos = e
    out.append(src[pos:])
    text = "".join(out)
    for old, new, cnt in cfg["raw"]:
        if text.count(old) != cnt:
            bad.append((f"reemplazo fijo ×{text.count(old)} (esperado {cnt})", old[:80]))
        text = text.replace(old, new)
    return text, units, missing, bad, info


def cmd_build():
    ok = True
    for page, cfg in PAGES.items():
        text, units, missing, bad, info = translate(page)
        out = ROOT / cfg["out"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        uniq = len({u[3] for u in units})
        print(f"{cfg['out']}: {len(units)} fragmentos ({uniq} únicos), sin traducir: {len(set(missing))}, "
              f"marcado distinto: {len(bad)}, código modificado: {len(info)}")
        for es in sorted(set(missing))[:10]:
            print("   · sin traducir:", es[:110].replace("\n", " "))
        for a, b in bad[:10]:
            print("   · revisar:", a[:90].replace("\n", " "), "=>", b[:90].replace("\n", " "))
        if "-v" in sys.argv:
            for a, b in info:
                print("   · código distinto:", [c for c in skeleton(a)[1]], "=>", [c for c in skeleton(b)[1]])
        ok = ok and not bad
    return 0 if ok else 1


def cmd_todo(page):
    src = (ROOT / PAGES[page]["src"]).read_text(encoding="utf-8")
    d = load_dict(page)
    seen, todo = set(), []
    for _, _, _, es in extract(src):
        if es not in d and es not in seen:
            seen.add(es)
            todo.append(es)
    print(json.dumps(todo, ensure_ascii=False, indent=0))


def cmd_import(page, listfile):
    """Une la lista de traducciones (mismo orden que `todo`) con sus fragmentos y la guarda en el diccionario."""
    src = (ROOT / PAGES[page]["src"]).read_text(encoding="utf-8")
    d = load_dict(page)
    seen, todo = set(), []
    for _, _, _, es in extract(src):
        if es not in d and es not in seen:
            seen.add(es)
            todo.append(es)
    en = json.loads(Path(listfile).read_text(encoding="utf-8"))
    if len(en) != len(todo):
        print(f"ERROR: {len(en)} traducciones para {len(todo)} fragmentos pendientes")
        return 1
    bad = 0
    for es, t in zip(todo, en):
        if skeleton(es)[0] != skeleton(t)[0]:
            bad += 1
            print("   · etiquetas distintas:", es[:100].replace("\n", " "), "=>", t[:100].replace("\n", " "))
        d[es] = t
    (I18N / PAGES[page]["dict"]).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(en)} traducciones guardadas en i18n/{PAGES[page]['dict']} ({bad} con marcado distinto)")
    return 1 if bad else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        sys.exit(cmd_build())
    if cmd == "todo":
        cmd_todo(sys.argv[2] if len(sys.argv) > 2 else "index")
    elif cmd == "import":
        sys.exit(cmd_import(sys.argv[2], sys.argv[3]))
    elif cmd == "check":
        sys.exit(cmd_build())
    else:
        print(__doc__)
