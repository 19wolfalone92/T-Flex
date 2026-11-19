# WINGED CHARACTER V6 — EXECUTION AND QUALITY GATES

STATUS: ENGINEERING CODE BUILT, ART MASTER NOT YET GENERATED/APPROVED.
V5 must NOT be relabelled as V6. A 2D reference sheet is NOT a 3D mesh.

## Actual original source: eighteen in-game screenshots

The user supplied 8 general angles and 10 extra high-detail captures:
heterochromia eyes, short layered white hair, black asymmetrical upper
plague-doctor helmet, lower black face mask, silver buckles, 2 full sleeves,
two blue feathered wings, a rear silver star and two vivid blue ribbons.

The ORIGINAL screenshots and cropped multi-view atlas are delivered privately
in the conversation as a ZIP. User photos are NOT committed to public GitHub.
AI-generated concept art is only supplemental, not visual ground truth.

## Fail-closed production stages

1. Produce a genuinely new high-detail GLB/BLEND from the original screenshots,
   not V1–V5 geometry.
2. Render five views from the ACTUAL 3D mesh (front, back, L/R and 3/4).
3. Review accuracy against originals. Reject wrong faces, wing plates, cut sleeves,
   missing eye detail and incorrect boots. No invented "99% fidelity" scoring.
4. Signed-off JSON with SHA256 of accepted GLB, original screenshot SHA256,
   real mesh renders, explicit user/expert approval and per-solid material map.
5. Only then run physical colour partition: reject painted textures masquerading
   as physical volumes, incomplete body nodes and disconnected fragments.
6. Integrate geometrically real two-key wing mounts into the approved torso and
   wing roots, plus other role-specific joints. Validate no interference.
7. Check actual FDM wall thickness, print orientation, supports, tolerance
   coupons, and T-FLEX 18 STEP assembly with matching peg bores.
8. Publish Release only if real CAD/STL files and independent QA pass. Physical
   printer acceptance still requires actual printer tests.

## Colour and segmentation

Different VISIBLE filament colours -> actual separate physical STL solids.
Same-colour connected regions -> one STL when safe (do not over-split).
Same colour but disconnected (e.g. two wings) -> separate individual STL, grouped
in the same filament batch. Very small studs and thin wing stripes may instead
be raised detail with post-painting. No horizontal clipping through arms.

## Floating wings: mechanical proof already created

Module: src/tflex_figurines/wing_mount_v6.py

- Real CAD central back bridge, two independently solid wing socket carriers.
- Two handed noncollinear pegs per wing; cannot rotate as a one-pin fixture.
- Local test gap 4.0 mm between body plate and wing carrier.
- Peg diameter 2.6 mm; blind bore diameter 3.0 mm; 0.20 mm radial clearance.
- Four printed fit coupons (0.15/0.20/0.25 radial plus a 2.6 mm pin).
- Independently checked watertight STL, CAD geometry, STEP reimport, no clashes.
- This is a PROTOTYPE, not an attachment to real V6 feathers or torso: final
  joint location and root reinforcement follow actual accepted sculpture.
- Unknown until tests: mass of wings, filament, shrink, layer bond, clearances.

## Implementation

- scripts/reconstruct_true_4view_master.py — 4 original locally held screenshots
  via private ZeroGPU inference; dry run by default, explicit generation opt-in.
- scripts/generate_new_master_trellis2.py — experimental free 3D alternative.
- scripts/try_free_triposg_v6.py — another public no-money geometry trial.
- src/tflex_figurines/wing_mount_v6.py — prototype real STEP/STL and fit coupons.
- src/tflex_figurines/v6_colour_split.py — approved solid-by-solid colour
  exporter; refuses to emit incomplete, fake or unapproved geometry.

IMPORTANT: Microsoft TRELLIS.2 already returned upstream inference failure and
Hunyuan3D-2mv public ZeroGPU quota was exhausted. No paid generation was run.
A true artist-approved 3D master is NOT YET AVAILABLE. Do not release a
fake final figurine from V5. No main merge before actual quality checks pass.
