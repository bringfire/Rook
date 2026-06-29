# Mesh2Splat Sampling Matrix

Date: 2026-06-29

Source repo: `C:/Users/aryan/source/repos/mesh2splat`
Mesh2Splat branch: `codex/sampling-resolution-cli`
Binary: `C:/Users/aryan/source/repos/mesh2splat/bin/Debug/Mesh2Splat.exe`
Raw matrix: `C:/Users/aryan/source/repos/Rook/docs/superpowers/audits/2026-06-29-mesh2splat-sampling-matrix.json`

Command:

```powershell
python C:/Users/aryan/source/repos/mesh2splat/tests/integration/run_sampling_matrix.py C:/Users/aryan/source/repos/mesh2splat/bin/Debug/Mesh2Splat.exe > C:/Users/aryan/source/repos/Rook/docs/superpowers/audits/2026-06-29-mesh2splat-sampling-matrix.json
```

chosenDefaultSamplingResolution: 128

## Fixture Metadata

| Fixture | Version | Triangles | Primitive Instances | Materials | Textures |
| --- | ---: | ---: | ---: | ---: | --- |
| `cube_textured_1m_v1` | 1 | 12 | 1 | 1 | 64x64 |
| `building_lowpoly_textured_v1` | 1 | 152 | 5 | 5 | 128x128 |

## Results

| Fixture | Sampling | Gaussians | PLY Bytes | CLI Duration ms | Process Wall ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cube_textured_1m_v1` | 64 | 24,576 | 1,180,098 | 51 | 802 |
| `cube_textured_1m_v1` | 128 | 98,304 | 4,719,042 | 156 | 647 |
| `cube_textured_1m_v1` | 256 | 393,216 | 18,874,819 | 625 | 1,133 |
| `cube_textured_1m_v1` | 512 | 1,572,864 | 75,497,924 | 2,528 | 3,029 |
| `cube_textured_1m_v1` | 1024 | 6,291,456 | 301,990,340 | 10,663 | 11,219 |
| `building_lowpoly_textured_v1` | 64 | 17,364 | 833,922 | 45 | 574 |
| `building_lowpoly_textured_v1` | 128 | 70,104 | 3,365,442 | 137 | 659 |
| `building_lowpoly_textured_v1` | 256 | 278,444 | 13,365,763 | 499 | 1,041 |
| `building_lowpoly_textured_v1` | 512 | 1,111,948 | 53,373,956 | 1,911 | 3,140 |
| `building_lowpoly_textured_v1` | 1024 | 4,449,472 | 213,575,108 | 7,412 | 7,943 |

## Rationale

`64` is very small, but it produces only 17,364 gaussians for the building fixture and is likely too sparse for an architectural default.

`128` keeps the building fixture at 70,104 gaussians and 3.37 MB, with sub-second process wall time. That is the best first-slice default for repeated Rhino capture tests.

`256` is still feasible, but it quadruples the building fixture to 278,444 gaussians and 13.37 MB. It is better treated as an explicit quality increase after the basic pipeline is stable.

`512` and `1024` remain large-output territory for the first slice.
