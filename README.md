# DP-800 · Cheatsheet

Material de estudio personal para el examen **DP-800 — Developing AI-Enabled Database Solutions** (Microsoft Certified: SQL AI Developer Associate).

No es contenido oficial de Microsoft ni está afiliado a Microsoft. Es un resumen basado en Microsoft Learn y su documentación pública; verifica lo crítico en la [guía de estudio oficial](https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-800).

## Ver el sitio

**https://memomsft.github.io/dp-800-cheatsheet/**

| Archivo | Qué es |
| --- | --- |
| `index.html` | Cheatsheet corto: 51 pistas «si el enunciado dice… → piensa en…», una tarjeta por módulo (M1–M11) y las cifras que se confunden. Con **modo práctica** (tapa las respuestas), filtro por texto y dominio, tema claro/oscuro y vista de impresión A4 (~7 páginas). |
| `en/index.html` | **English version** of the short cheatsheet, generated from `index.html` (see [Idiomas](#idiomas)). |
| `referencia.html` | Referencia completa y detallada (11 módulos, buscador, progreso ⭐/✓ y tema claro/oscuro). Solo en español. |
| `i18n/` | Generador de la versión en inglés (`build.py`) y su diccionario ES → EN (`en.index.json`). |

Son páginas estáticas autocontenidas (sin dependencias externas); también funcionan abriendo el `.html` en el navegador. El progreso y el tema se guardan por dispositivo (no se sincronizan).

## Idiomas

El botón **EN / ES** de la barra superior cambia de idioma y conserva la sección en la que estás (`#d2`, `#m5`…). Los anclajes son iguales en ambos idiomas.

Las páginas en español son la fuente; `en/index.html` **no se edita a mano**. Tras cambiar `index.html`:

```bash
python3 i18n/build.py build -v   # regenera en/index.html y avisa de lo que falte
```

Si hay textos nuevos aparecen como «sin traducir»: añade su traducción a `i18n/en.index.json` (`"texto en español": "English text"`, con las mismas etiquetas en línea) y vuelve a ejecutar. `python3 i18n/build.py todo` lista los pendientes en JSON y `import <pagina> <lista.json>` los incorpora en bloque. No necesita dependencias (solo Python 3).

## Diseño

Mismo lenguaje visual que el deck «Fabric AI Development»: hero oscuro con orbes, color por dominio (D1 azul · D2 violeta · D3 verde azulado), grupos punteados, terminales para el código y paleta Fluent 2. Sin fuentes web ni CDN.

## Alcance y verificación

Contenido alineado con los *skills measured* vigentes (12-mar-2026) y contrastado el 17-nov-2026 con Microsoft Learn y la documentación de SQL Server 2025, Azure SQL, Data API builder y GitHub Copilot. Donde Learn y la doc actual difieren (p. ej. `VECTOR_SEARCH`), el cheatsheet marca ambas formas.
