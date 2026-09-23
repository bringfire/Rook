# Vision panel — vendored web fonts

The Vision WebView2 surface pins `font-src 'self'` (see [VisionWebSurface.cs](../../VisionWebSurface.cs)),
so external font hosts (Google Fonts, etc.) are blocked. These files are vendored
in so the panel renders in its intended typography rather than system fallbacks.

Both families are licensed under the SIL Open Font License 1.1, which permits
bundling and redistribution with Rook (MIT-licensed). The OFL text
from each upstream is preserved verbatim alongside the fonts.

## Provenance

| File | Upstream | Commit SHA | Source path |
|---|---|---|---|
| `CormorantGaramond-VariableFont_wght.woff2` | [google/fonts](https://github.com/google/fonts) | `5457e22d106dd3b693c4f9eca2551a615341ea86` | `ofl/cormorantgaramond/CormorantGaramond[wght].ttf` (converted, see below) |
| `CormorantGaramond-Italic-VariableFont_wght.woff2` | google/fonts @ same SHA | `5457e22d106dd3b693c4f9eca2551a615341ea86` | `ofl/cormorantgaramond/CormorantGaramond-Italic[wght].ttf` (converted) |
| `EBGaramond-VariableFont_wght.woff2` | google/fonts @ same SHA | `5457e22d106dd3b693c4f9eca2551a615341ea86` | `ofl/ebgaramond/EBGaramond[wght].ttf` (converted) |
| `EBGaramond-Italic-VariableFont_wght.woff2` | google/fonts @ same SHA | `5457e22d106dd3b693c4f9eca2551a615341ea86` | `ofl/ebgaramond/EBGaramond-Italic[wght].ttf` (converted) |
| `JetBrainsMono-VariableFont_wght.woff2` | [JetBrains/JetBrainsMono](https://github.com/JetBrains/JetBrainsMono) | `19371302b95d218af43299bce79ddbddd0bc364d` | `fonts/webfonts/JetBrainsMono[wght].woff2` (renamed) |
| `Archivo-VariableFont_wdth_wght.woff2` | [Omnibus-Type/Archivo](https://github.com/Omnibus-Type/Archivo) | `b5d63988ce19d044d3e10362de730af00526b672` | `fonts/variable/Archivo[wdth,wght].ttf` (converted, see below) |
| `OFL-CormorantGaramond.txt` | google/fonts @ `5457e22d…` | — | `ofl/cormorantgaramond/OFL.txt` (renamed) |
| `OFL-EBGaramond.txt` | google/fonts @ `5457e22d…` | — | `ofl/ebgaramond/OFL.txt` (renamed) |
| `OFL-JetBrainsMono.txt` | JetBrains/JetBrainsMono @ same SHA | — | `OFL.txt` (renamed) |
| `OFL-Archivo.txt` | Omnibus-Type/Archivo @ same SHA | — | `OFL.txt` (renamed) |

Cormorant Garamond ships a `wght` axis of **300–700**; EB Garamond **400–800**.
The Vision `@font-face` weight ranges in `styles.css` mirror these. Display
elements that request `font-weight: 800` clamp to Cormorant's 700 ceiling.

Cormorant Garamond + EB Garamond match the typography of the Rook docs site.
Both are SIL OFL 1.1.

## Pinned download URLs

```
https://raw.githubusercontent.com/JetBrains/JetBrainsMono/19371302b95d218af43299bce79ddbddd0bc364d/fonts/webfonts/JetBrainsMono%5Bwght%5D.woff2
https://raw.githubusercontent.com/JetBrains/JetBrainsMono/19371302b95d218af43299bce79ddbddd0bc364d/OFL.txt
https://raw.githubusercontent.com/Omnibus-Type/Archivo/b5d63988ce19d044d3e10362de730af00526b672/fonts/variable/Archivo%5Bwdth,wght%5D.ttf
https://raw.githubusercontent.com/Omnibus-Type/Archivo/b5d63988ce19d044d3e10362de730af00526b672/OFL.txt
```

## SHA-256 (final vendored files)

```
979bf5b8e13e8349cb29aff8f127b2f104b01034a0c247b06cbf9bd85c0ad308  CormorantGaramond-VariableFont_wght.woff2
c89c47a6e6d9fedf896df54fa943fa29946b29d10f822d2da130f85fa565a978  CormorantGaramond-Italic-VariableFont_wght.woff2
1232444689d5ef033a35a88b8c347210265b2cb4177df358869f64a29bdf266a  EBGaramond-VariableFont_wght.woff2
62b158e422cb2cb89211d5fa1432ce9879339548263ef16743b86bce42a836b1  EBGaramond-Italic-VariableFont_wght.woff2
5fdabafe84eb704c67d7e87c1ec3a75172c6d1420b8a6c61f78dbb768804593a  Archivo-VariableFont_wdth_wght.woff2
31ec365b93e4bad6f202ce23352a56d01ca4462b2afc782ed2cf6fa42ca9ac0e  JetBrainsMono-VariableFont_wght.woff2
60700d351cac4650c51f3f9db318d2a420f8b45052dba2715eb5fec41f0f6956  OFL-CormorantGaramond.txt
0985066662eb755ed3683ae5482a81a9195b49ce3f7e165cc2388b3dbece7dd7  OFL-EBGaramond.txt
108b4e57c9c796d3d38d0428ca7ee39de47ad93187302718d9b2d8864b9b716b  OFL-Archivo.txt
a76abf002c49097d146e86740a3105a5d00450b1592e820a1109a8c5680cd697  OFL-JetBrainsMono.txt
```

> Note: the upstream `OFL.txt` SHA-256 for Cormorant Garamond and EB Garamond
> differ from the JetBrains/Archivo licenses (different copyright holders);
> the body of each is the standard SIL OFL 1.1 boilerplate.

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
