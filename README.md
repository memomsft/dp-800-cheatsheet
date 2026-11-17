# DP-800 · Cheatsheet

Material de estudio personal para el examen **DP-800 — Developing AI-Enabled Database Solutions** (Microsoft Certified: SQL AI Developer Associate).

No es contenido oficial de Microsoft ni está afiliado a Microsoft. Es un resumen basado en Microsoft Learn y su documentación pública; verifica lo crítico en la [guía de estudio oficial](https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-800).

## Ver el sitio

**https://memomsft.github.io/dp-800-cheatsheet/**

| Archivo | Qué es |
| --- | --- |
| `index.html` | Cheatsheet corto: 51 pistas «si el enunciado dice… → piensa en…», una tarjeta por módulo (M1–M11) y las cifras que se confunden. Con **modo práctica** (tapa las respuestas), filtro por texto y dominio, tema claro/oscuro y vista de impresión A4 (~7 páginas). |
| `referencia.html` | Referencia completa y detallada (11 módulos, buscador, progreso ⭐/✓ y tema claro/oscuro). |
| `en/index.html`, `en/reference.html` | **English versions** of the short cheatsheet and of the full reference, generated from the Spanish pages (ver [Idiomas](#idiomas)). |
| `i18n/` | Generador (`build.py`), diccionarios ES → EN (`en.index.json`, `en.referencia.json`) y literales de código de la referencia (`code.referencia.json`). |

Son páginas estáticas autocontenidas (sin dependencias externas); también funcionan abriendo el `.html` en el navegador. El progreso y el tema se guardan por dispositivo (no se sincronizan).

## Idiomas

Cada página tiene su versión en inglés (`en/`). El botón **EN / ES** (barra superior del cheatsheet, barra lateral de la referencia) cambia de idioma y conserva la sección en la que estás (`#d2`, `#m05`…). Los anclajes son iguales en ambos idiomas y el progreso ⭐/✓ y el tema se comparten entre ellos (mismo almacenamiento del navegador).

Las páginas en español son la fuente; `en/*.html` **no se editan a mano**. Tras cambiar `index.html` o `referencia.html`:

```bash
python3 i18n/build.py build -v      # regenera en/index.html y en/reference.html y avisa de lo que falte
python3 i18n/build.py status referencia
```

Los textos nuevos aparecen como «sin traducir». Para añadirlos:

1. `python3 i18n/build.py chunk referencia /tmp/lotes` los parte en lotes de texto plano (`cNNN.es.txt`; el formato está descrito en `build.py`).
2. Traduce cada lote a `cNNN.en.txt` (`@@ NNNN` + traducción, o `@@ NNNN =` si queda igual).
3. `python3 i18n/build.py verify cNNN.es.txt cNNN.en.txt` comprueba etiquetas, atributos, números y español residual; `python3 i18n/build.py merge referencia cNNN.es.txt cNNN.en.txt` lo incorpora al diccionario.

Para pocos textos basta añadirlos a mano a `i18n/en.<pagina>.json` (`"texto en español": "English text"`, con las mismas etiquetas en línea). Solo requiere Python 3.

## Diseño

Mismo lenguaje visual que el deck «Fabric AI Development»: hero oscuro con orbes, color por dominio (D1 azul · D2 violeta · D3 verde azulado), grupos punteados, terminales para el código y paleta Fluent 2. Sin fuentes web ni CDN.

## Alcance y verificación

Contenido alineado con los *skills measured* vigentes (12-mar-2026) y contrastado el 17-nov-2026 con Microsoft Learn y la documentación de SQL Server 2025, Azure SQL, Data API builder y GitHub Copilot. Donde Learn y la doc actual difieren (p. ej. `VECTOR_SEARCH`), el cheatsheet marca ambas formas.
