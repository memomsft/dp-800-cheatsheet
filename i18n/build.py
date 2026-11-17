#!/usr/bin/env python3
"""Genera la versión en inglés (en/) a partir de las páginas en español.

Las páginas en español (index.html, referencia.html) son la fuente. Este script:
  1. extrae el texto traducible (bloques de texto con su marcado en línea, atributos
     title/aria-label/placeholder/alt/data-title/data-short, <title>, meta description y
     comentarios de los bloques de código) SIN tocar el resto del archivo (CSS, JS, estructura);
  2. sustituye cada fragmento por su traducción de i18n/en.<pagina>.json
     (diccionario «fragmento en español» -> «fragmento en inglés»);
  3. aplica unos pocos reemplazos fijos (idioma, enlaces, textos que inserta el JS).
Los literales en español dentro de bloques de código (mensajes de error, datos de ejemplo…) no son
comentarios: se sustituyen antes de extraer con i18n/code.<pagina>.json ([es, en, veces]).

Uso:
  python3 i18n/build.py build [-v]       # genera en/*.html (-v: detalle de avisos)
  python3 i18n/build.py status [pagina]  # fragmentos traducidos / pendientes
  python3 i18n/build.py todo [pagina]    # lista los fragmentos sin traducir (JSON)
  python3 i18n/build.py import <pagina> <lista.json>
                                         # añade traducciones: lista EN en el mismo orden que `todo`
  python3 i18n/build.py chunk <pagina> <dir> [max_chars]
                                         # parte los pendientes en lotes de texto plano cNNN.es.txt
  python3 i18n/build.py verify <lote.es.txt> <lote.en.txt>
                                         # valida una traducción (etiquetas, atributos, números, español residual)
  python3 i18n/build.py merge <pagina> <lote.es.txt> <lote.en.txt> [-q]
                                         # verifica y añade las traducciones válidas al diccionario
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
ATTRS = ("title", "aria-label", "placeholder", "alt", "data-title", "data-short")
WORD = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")
COMMENT_RE = {
    "sql": re.compile(r"--[ \t]*([^\n]*)"),
    "hash": re.compile(r"(?:^|[ \t])#[ \t]*([^\n]*)", re.M),
    "slash": re.compile(r"(?:^|[ \t])//[ \t]*([^\n]*)", re.M),
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
                attr_units(n)
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
REF_LINK_ES = '<a class="btn" id="btnLang" href="en/reference.html" data-base="en/reference.html" hreflang="en" lang="en" title="English version">🌐 EN</a>'
REF_LINK_EN = '<a class="btn" id="btnLang" href="../referencia.html" data-base="../referencia.html" hreflang="es" lang="es" title="Versión en español">🌐 ES</a>'

PAGES = {
    "index": {
        "src": "index.html",
        "out": "en/index.html",
        "dict": "en.index.json",
        "raw": [
            ('<html lang="es">', '<html lang="en">', 1),
            (LANG_LINK_ES, LANG_LINK_EN, 1),
            ('href="referencia.html"', 'href="reference.html"', 1),
            ("b.textContent='Copiado ✓'", "b.textContent='Copied ✓'", 1),
            ("shown+' de '+rows.length+' pistas':rows.length+' pistas'", "shown+' of '+rows.length+' clues':rows.length+' clues'", 1),
        ],
    },
    "referencia": {
        "src": "referencia.html",
        "out": "en/reference.html",
        "dict": "en.referencia.json",
        # Literales en español dentro de bloques de código (se sustituyen en el fuente ANTES de extraer)
        "pre": "code.referencia.json",
        # Textos que el JS de la página inserta en tiempo de ejecución
        "raw": [
            ('<html lang="es">', '<html lang="en">', 1),
            (REF_LINK_ES, REF_LINK_EN, 1),
            ("text: ['Texto', esc]", "text: ['Text', esc]", 1),
            ('type="button">Copiar</button>', 'type="button">Copy</button>', 1),
            ("e.target.textContent = '¡Copiado!'; setTimeout(() => e.target.textContent = 'Copiar', 1200);",
             "e.target.textContent = 'Copied!'; setTimeout(() => e.target.textContent = 'Copy', 1200);", 1),
            ('title="Marcar para repasar">☆</button><label title="Marcar como repasado"><input type="checkbox"> Repasado</label>',
             'title="Mark to review again">☆</button><label title="Mark as reviewed"><input type="checkbox"> Reviewed</label>', 1),
            ("d0: '⚡ Repaso final'", "d0: '⚡ Final review'", 1),
            ("dx: 'Apéndice'", "dx: 'Appendix'", 1),
            ('data-t="overview">🏁 Resumen del examen</a>', 'data-t="overview">🏁 Exam overview</a>', 1),
            ("' temas repasados · '", "' topics reviewed · '", 1),
            ("' tema(s) coinciden'", "' topic(s) match'", 1),
            ("'⇕ Desplegar todo' : '⇕ Plegar todo'", "'⇕ Expand all' : '⇕ Collapse all'", 1),
            # Marcadores de posición en español que quedan dentro de <code> en línea (el código no se traduce)
            ("execute&lt;Entidad&gt;(…)", "execute&lt;Entity&gt;(…)", 1),
            ("dab add &lt;entidad&gt;", "dab add &lt;entity&gt;", 1),
            ("dab update &lt;entidad&gt;", "dab update &lt;entity&gt;", 1),
            ("<code>&lt;entidad&gt;</code>", "<code>&lt;entity&gt;</code>", 1),
            ("dab validate --config &lt;ruta&gt;", "dab validate --config &lt;path&gt;", 1),
            ("<code>ON catálogo</code></td><td><code>nombre</code> · <code>(nombre, FILEGROUP fg)</code>",
             "<code>ON catalog</code></td><td><code>name</code> · <code>(name, FILEGROUP fg)</code>", 1),
            ("<code>SYSTEM</code> · <code>nombre</code>", "<code>SYSTEM</code> · <code>name</code>", 1),
            ("DATABASE SCOPED CREDENTIAL::[nombre]", "DATABASE SCOPED CREDENTIAL::[name]", 1),
            ("N'texto' [, LANGUAGE l]", "N'text' [, LANGUAGE l]", 1),
            ("LEFT(texto, 400)", "LEFT(text, 400)", 1),
            ("HISTORY_TABLE = schema.tabla", "HISTORY_TABLE = schema.table", 1),
            ("WHERE col = valor", "WHERE col = value", 1),
            ("OPTIMIZE FOR (@p = valor)", "OPTIMIZE FOR (@p = value)", 1),
            ("<code>/api/{entidad}</code>", "<code>/api/{entity}</code>", 1),
            ("SELECT * FROM TablaInexistente", "SELECT * FROM NonexistentTable", 1),
            ('{ "columna": "alias" }', '{ "column": "alias" }', 1),
            ('"rol:acciones"', '"role:actions"', 1),
        ],
    },
}


def load_dict(page):
    p = I18N / PAGES[page]["dict"]
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_src(page):
    """Fuente en español de la página, con los literales de código ya en inglés (si la página los define)."""
    cfg = PAGES[page]
    src = (ROOT / cfg["src"]).read_text(encoding="utf-8")
    if cfg.get("pre"):
        for es, en, cnt in json.loads((I18N / cfg["pre"]).read_text(encoding="utf-8")):
            if src.count(es) != cnt:
                raise SystemExit(f"{cfg['pre']}: «{es[:70]}» aparece {src.count(es)} veces (esperado {cnt})")
            src = src.replace(es, en)
    return src


def translate(page, strict=False):
    cfg = PAGES[page]
    src = load_src(page)
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


def pending(page):
    """Fragmentos únicos aún sin traducir, en orden de aparición: (fuente, [(offset, tipo, texto)])."""
    src = load_src(page)
    d = load_dict(page)
    seen, todo = set(), []
    for s, _, kind, es in extract(src):
        if es not in d and es not in seen:
            seen.add(es)
            todo.append((s, kind, es))
    return src, todo


def cmd_todo(page):
    print(json.dumps([es for _, _, es in pending(page)[1]], ensure_ascii=False, indent=0))


def cmd_import(page, listfile):
    """Une la lista de traducciones (mismo orden que `todo`) con sus fragmentos y la guarda en el diccionario."""
    d = load_dict(page)
    todo = [es for _, _, es in pending(page)[1]]
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
    save_dict(page, d)
    print(f"{len(en)} traducciones guardadas en i18n/{PAGES[page]['dict']} ({bad} con marcado distinto)")
    return 1 if bad else 0


def save_dict(page, d):
    (I18N / PAGES[page]["dict"]).write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------
# Traducción por lotes (varios traductores en paralelo): chunk -> verify -> merge
#
# Formato de texto plano, sin escapes (los fragmentos llevan HTML con comillas y barras invertidas):
#   @@ ctx <sección › tema>        contexto informativo (se ignora al leer)
#   @@ 0042 t                      cabecera: id y tipo (t = texto HTML, a = valor de atributo, c = comentario de código)
#   <fragmento, puede ocupar varias líneas>
# La respuesta usa «@@ 0042» + traducción, o «@@ 0042 =» si el fragmento se queda igual.
# --------------------------------------------------------------------------------------------
SENT = "@@ "
HEAD_RE = re.compile(r"<(h[23])\b[^>]*>(.*?)</\1>", re.S)
HDR_RE = re.compile(r"^@@ (\d{4})\b(.*)$")
START_TAG_RE = re.compile(r"<([a-zA-Z][\w-]*)\b([^<>]*)>")
ATTR_RE = re.compile(r"([\w:-]+)\s*=\s*(\"[^\"]*\"|'[^']*')")
ES_STOP = set("""el la los las del que una con por para sin más como cuando solo sólo también pero está están este esta estos estas
 desde entre sobre donde dónde según cada todo todos todas otro otra otros otras muy ya hacia pues aunque mientras tras
 puede pueden debe deben usa usar hace hacer tiene tienen son fue ser sus cuyo cuya algo nada siempre nunca además ejemplo""".split())
ES_CHARS = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")
WORDS_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+")


def heading_marks(src):
    marks = []
    for m in HEAD_RE.finditer(src):
        t = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        marks.append((m.start(), m.group(1), t[:80]))
    return marks


def context_at(marks, off):
    h2 = h3 = None
    for o, lvl, t in marks:
        if o > off:
            break
        if lvl == "h2":
            h2, h3 = t, None
        else:
            h3 = t
    return " › ".join(x for x in (h2, h3) if x)


def cmd_chunk(page, outdir, max_chars=13000):
    src, todo = pending(page)
    marks = heading_marks(src)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    manifest, buf, size, first, last_ctx, n = [], [], 0, None, None, 0

    def flush():
        nonlocal buf, size, first, last_ctx, n
        if not buf:
            return
        name = f"c{len(manifest) + 1:03d}"
        (out / f"{name}.es.txt").write_text("".join(buf), encoding="utf-8")
        manifest.append({"file": name, "first": first, "last": first + n - 1, "n": n, "chars": size})
        buf, size, first, last_ctx, n = [], 0, None, None, 0

    for i, (off, kind, es) in enumerate(todo, 1):
        if any(ln.startswith(SENT) for ln in es.split("\n")):
            raise SystemExit(f"fragmento {i} contiene una línea que empieza por «@@ »")
        if size + len(es) > max_chars and buf:
            flush()
        if first is None:
            first = i
        ctx = context_at(marks, off)
        if ctx and ctx != last_ctx:
            buf.append(f"{SENT}ctx {ctx}\n")
            last_ctx = ctx
        buf.append(f"{SENT}{i:04d} {kind}\n{es}\n")
        size += len(es)
        n += 1
    flush()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"{len(todo)} fragmentos pendientes -> {len(manifest)} lotes en {out}")


def parse_entries(path):
    """Lee un lote: {id: (tipo, texto, igual)} (tipo vacío en las respuestas)."""
    entries, cur = {}, None
    for line in Path(path).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n"):
        m = HDR_RE.match(line)
        if m:
            rest = m.group(2).split()
            kind = next((t for t in rest if t in ("t", "a", "c")), "")
            cur = int(m.group(1))
            entries[cur] = [kind, [], "=" in rest]
            continue
        if line.startswith(SENT):
            cur = None
            continue
        if cur is not None:
            entries[cur][1].append(line)
    return {k: (v[0], "\n".join(v[1]).strip(), v[2]) for k, v in entries.items()}


def start_tags(fragment):
    """Etiquetas de apertura con sus atributos, sin el valor de los atributos traducibles."""
    res = []
    for m in START_TAG_RE.finditer(fragment):
        attrs = []
        for a in ATTR_RE.finditer(m.group(2)):
            name = a.group(1).lower()
            attrs.append((name, "*" if name in ATTRS else a.group(2)))
        res.append((m.group(1).lower(), tuple(sorted(attrs))))
    return res


def plain(fragment, keep_code=False):
    if not keep_code:
        fragment = re.sub(r"<code[^>]*>.*?</code>", " ", fragment, flags=re.S)
    return unescape(re.sub(r"<[^>]*>", " ", fragment))


def numbers(fragment):
    return sorted(re.findall(r"\d+", plain(re.sub(r"&#?\w+;", " ", fragment), keep_code=True)))


def spanish_hits(fragment):
    text = plain(fragment)
    hits = set(ES_CHARS.findall(text))
    for w in WORDS_RE.findall(text):
        if (w.islower() or w.istitle()) and w.lower() in ES_STOP:
            hits.add(w.lower())
    return sorted(hits)


def check_pair(kind, es, en):
    """Devuelve (errores, avisos) de una traducción."""
    err, warn = [], []
    if not en:
        return ["vacío"], warn
    if kind in ("a", "c"):
        if "\n" in en:
            err.append("el fragmento debe ir en una sola línea")
        if kind == "a" and '"' in en:
            err.append('un atributo no puede llevar comillas dobles (usa &quot;)')
        if kind == "a" and "<" in en:
            err.append("un atributo no puede llevar «<»")
    if kind in ("t", ""):
        (tes, ces), (ten, cen) = skeleton(es), skeleton(en)
        if tes != ten:
            err.append(f"etiquetas distintas: {[('/' if a else '') + b for a, b in tes]} => {[('/' if a else '') + b for a, b in ten]}")
        elif start_tags(es) != start_tags(en):
            err.append("atributos de etiquetas modificados (solo se traducen title, aria-label, placeholder, alt, data-title, data-short)")
        elif ces != cen:
            warn.append(f"código modificado: {ces} => {cen}")
        if "<" in re.sub(r"<[^>]*>", "", en):
            err.append("«<» suelto fuera de una etiqueta (usa &lt;)")
        bare = lambda f: len(re.findall(r"&(?!#?\w+;)", re.sub(r"<[^>]*>", "", f)))
        if bare(en) > bare(es):
            err.append("«&» suelto (usa &amp;)")
    if numbers(es) != numbers(en):
        a, b = numbers(es), numbers(en)
        only_es = [x for x in a if x not in b or a.count(x) > b.count(x)]
        only_en = [x for x in b if x not in a or b.count(x) > a.count(x)]
        warn.append(f"números distintos: solo ES {sorted(set(only_es))} / solo EN {sorted(set(only_en))}")
    if es == en and spanish_hits(es):
        warn.append(f"sin traducir (señales de español: {spanish_hits(es)})")
    elif es != en:
        h = spanish_hits(en)
        if h:
            warn.append(f"posible español residual: {h}")
        if len(es) > 80 and not (0.4 <= len(en) / len(es) <= 2.4):
            warn.append(f"longitud sospechosa: {len(es)} => {len(en)}")
    return err, warn


def verify_files(es_path, en_path, show=True):
    es_entries, en_entries = parse_entries(es_path), parse_entries(en_path)
    problems, good = [], {}
    for i in sorted(set(es_entries) | set(en_entries)):
        if i not in en_entries:
            problems.append((i, ["falta en la respuesta"], []))
            continue
        if i not in es_entries:
            problems.append((i, ["id que no existe en el lote"], []))
            continue
        kind, es, _ = es_entries[i]
        _, en, same = en_entries[i]
        if same:
            en = es
        err, warn = check_pair(kind, es, en)
        if err or warn:
            problems.append((i, err, warn))
        if not err:
            good[es] = en
    n_err = sum(1 for p in problems if p[1])
    n_warn = sum(1 for p in problems if p[2] and not p[1])
    if show:
        for i, err, warn in problems:
            kind, es, _ = es_entries.get(i, ("", "", False))
            en = en_entries.get(i, ("", "", False))
            en = es if en[2] else en[1]
            for e in err:
                print(f"ERROR  {i:04d}: {e}")
            for w in warn:
                print(f"aviso  {i:04d}: {w}")
            if err or warn:
                print(f"       ES: {es[:300]!r}\n       EN: {en[:300]!r}")
        print(f"{len(es_entries)} fragmentos · {len(en_entries)} traducidos · {n_err} con ERROR · {n_warn} solo con avisos")
    return good, n_err


def cmd_verify(es_path, en_path):
    return 1 if verify_files(es_path, en_path)[1] else 0


def cmd_merge(page, es_path, en_path):
    good, n_err = verify_files(es_path, en_path, show="-q" not in sys.argv)
    d = load_dict(page)
    d.update(good)
    save_dict(page, d)
    print(f"{len(good)} traducciones añadidas a i18n/{PAGES[page]['dict']} ({n_err} rechazadas con ERROR)")
    return 1 if n_err else 0


def cmd_status(page):
    src, todo = pending(page)
    total = len({u[3] for u in extract(src)})
    print(f"{page}: {total} fragmentos únicos · {total - len(todo)} traducidos · {len(todo)} pendientes")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    args = [a for a in sys.argv[2:] if not a.startswith("-")]
    if cmd == "build" or cmd == "check":
        sys.exit(cmd_build())
    elif cmd == "todo":
        cmd_todo(args[0] if args else "index")
    elif cmd == "import":
        sys.exit(cmd_import(args[0], args[1]))
    elif cmd == "chunk":
        cmd_chunk(args[0], args[1], int(args[2]) if len(args) > 2 else 13000)
    elif cmd == "verify":
        sys.exit(cmd_verify(args[0], args[1]))
    elif cmd == "merge":
        sys.exit(cmd_merge(args[0], args[1], args[2]))
    elif cmd == "status":
        cmd_status(args[0] if args else "index")
    else:
        print(__doc__)
