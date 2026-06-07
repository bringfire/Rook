# Vision panel — vendored web fonts

The Vision WebView2 surface pins `font-src 'self'` (see [VisionWebSurface.cs](../../VisionWebSurface.cs)),
so external font hosts (Google Fonts, etc.) are blocked. These files are vendored
in so the panel renders in its intended typography rather than system fallbacks.

Both families are licensed under the SIL Open Font License 1.1, which permits
bundling and redistribution within Rook's proprietary distribution. The OFL text
from each upstream is preserved verbatim alongside the fonts.

## Provenance

| File | Upstream | Commit SHA | Source path |
|---|---|---|---|
| `JetBrainsMono-VariableFont_wght.woff2` | [JetBrains/JetBrainsMono](https://github.com/JetBrains/JetBrainsMono) | `19371302b95d218af43299bce79ddbddd0bc364d` | `fonts/webfonts/JetBrainsMono[wght].woff2` (renamed) |
| `Archivo-VariableFont_wdth_wght.woff2` | [Omnibus-Type/Archivo](https://github.com/Omnibus-Type/Archivo) | `b5d63988ce19d044d3e10362de730af00526b672` | `fonts/variable/Archivo[wdth,wght].ttf` (converted, see below) |
| `OFL-JetBrainsMono.txt` | JetBrains/JetBrainsMono @ same SHA | — | `OFL.txt` (renamed) |
| `OFL-Archivo.txt` | Omnibus-Type/Archivo @ same SHA | — | `OFL.txt` (renamed) |

## Pinned download URLs

```
https://raw.githubusercontent.com/JetBrains/JetBrainsMono/19371302b95d218af43299bce79ddbddd0bc364d/fonts/webfonts/JetBrainsMono%5Bwght%5D.woff2
https://raw.githubusercontent.com/JetBrains/JetBrainsMono/19371302b95d218af43299bce79ddbddd0bc364d/OFL.txt
https://raw.githubusercontent.com/Omnibus-Type/Archivo/b5d63988ce19d044d3e10362de730af00526b672/fonts/variable/Archivo%5Bwdth,wght%5D.ttf
https://raw.githubusercontent.com/Omnibus-Type/Archivo/b5d63988ce19d044d3e10362de730af00526b672/OFL.txt
```

## SHA-256 (final vendored files)

```
5fdabafe84eb704c67d7e87c1ec3a75172c6d1420b8a6c61f78dbb768804593a  Archivo-VariableFont_wdth_wght.woff2
31ec365b93e4bad6f202ce23352a56d01ca4462b2afc782ed2cf6fa42ca9ac0e  JetBrainsMono-VariableFont_wght.woff2
108b4e57c9c796d3d38d0428ca7ee39de47ad93187302718d9b2d8864b9b716b  OFL-Archivo.txt
a76abf002c49097d146e86740a3105a5d00450b1592e820a1109a8c5680cd697  OFL-JetBrainsMono.txt
```

The intermediate Archivo TTF (not vendored, deleted after conversion):
```
664bbeb10522dac35c174a3860aaecad7b1ad3a0fc8b0d26888e26c824ec556d  Archivo[wdth,wght].ttf
```

## Archivo TTF → WOFF2 conversion

JetBrains ships variable WOFF2 directly. Omnibus-Type ships only TTF for the
variable axis (their `webfonts/` dir is static-only), so Archivo was converted
locally with fontTools + brotli. Lossless: the variable-axis tables (`fvar`,
`gvar`, `HVAR`, etc.) pass through untouched; only the table data is rewrapped
with brotli compression in the WOFF2 container.

Conversion environment: throwaway venv at `.scratch/font-woff2-venv/` (delete
when no longer needed):

```bash
python -m venv .scratch/font-woff2-venv
.scratch/font-woff2-venv/Scripts/python.exe -m pip install fonttools brotli
```

Conversion script (run from `.scratch/`):

```python
from fontTools.ttLib import TTFont
f = TTFont("Archivo[wdth,wght].ttf")
f.flavor = "woff2"
f.save("Archivo-VariableFont_wdth_wght.woff2")
```

To reproduce: re-run the four `curl --fail --location` downloads at the SHAs
above, run the conversion, and confirm the SHA-256s in the table match. If the
upstream regenerates the TTF (rare for variable masters, but possible), the
WOFF2 SHA will shift even though the typography is unchanged — at that point,
re-pin the upstream SHA and the new WOFF2 SHA together.
