# Reconstruction Provider Note: Hunyuan Rapid Options

Date: 2026-06-23

## Rule

For `fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d`, do not send `enable_pbr:true` for the normal Textured reconstruction path.

Use omitted options (`{}`) for default textured output. `enable_pbr:false` also produced the same working base-texture shape in live testing, but omission is the default Rook contract.

## Evidence

Live A/B testing against the deployed Rhino build showed:

- `{}` returned an OBJ/MTL package with a base-color texture such as `texture_20250901.png`, referenced by `map_Kd`, and no missing-map warning.
- `{ "enable_pbr": false }` returned the same working base-color texture shape.
- `{ "enable_pbr": true }` returned a PBR-style MTL, but only delivered `texture_pbr_v128_metallic.png`; the referenced base-color, roughness, and normal maps were absent, so Rhino imported the mesh white/untextured.

This is not a polling issue. Rook fetches the provider response after the job reaches the provider's complete state.

## Guardrails

- The production catalog marks rapid as `supports_pbr:false` and `default_texture_expected:true`.
- The Vision Reconstruct UI emits `enable_pbr:true` only when the selected model advertises PBR support.
- The managed reconstruction submit path rejects direct `enable_pbr:true` submissions for models that do not advertise PBR support.

If a future provider/model reliably returns a complete PBR set, add it as a separate PBR-capable catalog entry or re-enable PBR only with fresh live evidence and tests.
