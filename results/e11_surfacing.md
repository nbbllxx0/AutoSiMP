# E11 preview-surfacing

- n = 120 P0 prompts (10+10+100)

| | preview flagged | preview silent |
|---|---:|---:|
| specification imperfect | 32 detection | 71 silent miss |
| specification exact (9/9) | 6 false alarm | 11 correct pass |

The ambiguity gate is keyword-based (AMBIGUITY_TERMS in revision_experiments.py). It detects linguistic hedges such as near/around/roughly/mid-right, not semantic error. A confidently worded prompt that the model misreads is a silent miss.

## Silent misses (named)

- `mbb_beam` (canonical, 8/9): MBB beam, 3:1 aspect ratio. Symmetry boundary condition on the left edge, roller support at the bottom right corner. Downward load at the top left corner. Half material.
- `bridge` (canonical, 7/9): Bridge structure. 4 meters wide, 1 meter tall. Bottom edge supported vertically (pin_y). Uniform downward pressure on the top edge. Use 30% material.
- `dual_load` (canonical, 8/9): Cantilever with two loads: one at the upper-right and one at the lower-right, both pushing down. Left edge is fixed. 50% volume fraction.
- `western_clamped_free_tip` (challenge, 8/9): A beam is clamped along the western boundary and pulled downward at the free-end midpoint.
- `eastern_wall_left_load` (challenge, 8/9): Use an eastern wall clamp and apply a downward force at the midpoint of the opposite free side.
- `load_rightward_midspan` (challenge, 8/9): Clamp the left wall and push the free end horizontally to the right at mid-height.
- `multi_load_mixed_direction` (challenge, 8/9): Left wall fixed; one downward force at the upper free corner and one upward force at the lower free corner.
- `void_off_center` (challenge, 6/9): Cantilever with a pipe cutout one third from the clamp and centered vertically.
- `roller_language` (challenge, 8/9): Model a three-unit beam with a vertical restraint at each bottom corner and a downward load at top center.
- `distributed_bottom_support` (challenge, 5/9): A bridge-like span with vertical support along the underside and pressure over the deck.
- `p01_cantilever_wall` (heldout, 8/9): Make a rectangular cantilever; clamp the left wall and put a downward force halfway up the free right edge.
- `p02_mbb_words` (heldout, 7/9): Use the standard MBB setup with left symmetry, a vertical roller at the lower right, and a downward load at the upper left.
- `p03_bridge_deck` (heldout, 6/9): Bridge-like span: support the underside vertically and apply uniform deck pressure downward; use thirty percent material.
- `p05_tall_short_beam` (heldout, 8/9): A short deep beam, taller than it is wide, clamped on the left and loaded downward at the right-side midpoint.
- `p06_two_corner_supports` (heldout, 8/9): Support the two lower corners and load the top center downward in a three-to-one beam.
- `p08_two_down_forces` (heldout, 7/9): Left-clamped beam with two downward forces, one high and one low on the right boundary.
- `p10_slender_beam` (heldout, 8/9): Slender six-to-one cantilever, fixed on the west side, with a downward free-end load.
- `s01_west_clamp` (heldout, 8/9): Clamp the west boundary and push down at the east midpoint.
- `s02_east_clamp` (heldout, 8/9): Clamp the east boundary and push down at the west midpoint.
- `s03_south_support` (heldout, 6/9): Use a southern vertical support and load the northern edge with downward pressure.
- `s04_north_clamp` (heldout, 7/9): Attach the top edge and pull the lower-right point outward.
- `s05_upper_corner` (heldout, 8/9): Left wall fixed; apply a downward point load at the upper free corner.
- `s06_lower_corner` (heldout, 8/9): Left wall fixed; apply an upward point load at the lower free corner.
- `s07_midheight_horizontal` (heldout, 8/9): Left edge clamped, free side pushed to the right at mid-height.
- `s08_bottom_corners_pin` (heldout, 7/9): A three-unit beam with vertical restraints at both bottom corners and a top-center downward load.
- `s09_right_face_pull` (heldout, 6/9): Fix the top of a square bracket and pull the right face at one-quarter height.
- `s10_free_end_tip` (heldout, 8/9): A long six-by-one bar fixed at the western end, loaded downward at the free-end midpoint.
- `m01_upper_lower_down` (heldout, 7/9): Left edge fixed; downward forces at both the upper-right and lower-right points.
- `m02_opposed_vertical` (heldout, 8/9): Left wall fixed; top-right force downward and bottom-right force upward.
- `m04_pressure_plus_tip` (heldout, 5/9): Bottom edge supports vertical motion; apply top pressure and an extra downward point load at midspan.
- `m05_three_point_loads` (heldout, 8/9): Cantilever with three downward point loads equally spaced on the free right edge.
- `m07_mbb_extra_tip` (heldout, 6/9): MBB beam with the standard upper-left downward load and a second small downward load at midspan.
- `m08_shear_pair` (heldout, 4/9): A short deep left-clamped beam with one downward and one rightward load at the free-side midpoint.
- `m09_bridge_side_load` (heldout, 4/9): Bridge span with vertical bottom support, deck pressure, and a small horizontal side load at the right end.
- `m10_split_tip_load` (heldout, 8/9): Six-to-one cantilever with two downward loads bracketing the free-end midpoint.
- `v02_offcenter_void` (heldout, 6/9): Cantilever with a circular cutout one third from the clamp, centered vertically.
- `v04_protected_pad` (heldout, 7/9): Keep a protected solid pad at the loaded right end of a left-clamped beam.
- `v07_bridge_void` (heldout, 4/9): Bridge span with a circular service opening at midspan and top pressure.
- `v08_mbb_void` (heldout, 6/9): MBB beam with a small circular void centered in the domain.
- `a02_under_hole` (heldout, 7/9): Apply force under the pipe hole in a cantilever.
- `a09_pressure_deck` (heldout, 5/9): A bridge with pressure over the deck and supports along the underside.
- `p11_cantilever_tip_synonym` (heldout, 8/9): Design a left-wall fixed rectangular beam and press downward at the free-end midpoint.
- `p12_mbb_support_synonym` (heldout, 7/9): MBB beam: symmetry along the left edge, roller at the lower-right point, load down at the top-left point.
- `p13_bridge_uniform_deck` (heldout, 5/9): Make a simply supported deck with vertical underside restraint and a uniformly downward top load.
- `p15_deep_shear_wall` (heldout, 8/9): Tall short cantilever, west side fixed, downward load at the midpoint of the east side.
- `p16_two_end_supports` (heldout, 5/9): Beam supported vertically at both lower end points with a vertical downward load at the top center.
- `p20_long_narrow_free_load` (heldout, 6/9): Long narrow cantilever fixed at the left end and loaded vertically downward at the free end.
- `s13_top_pressure_bottom_support` (heldout, 6/9): Restrain the lower edge vertically and put a downward distributed load on the upper edge.
- `s15_upper_free_corner_down` (heldout, 8/9): For a left-clamped rectangle, load the upper free corner downward.
- `s16_lower_free_corner_up` (heldout, 8/9): For a left-clamped rectangle, load the lower free corner upward.
- `s17_mid_free_horizontal` (heldout, 8/9): Clamp the west edge and push the east-edge midpoint horizontally outward.
- `s18_bottom_end_rollers` (heldout, 5/9): Give the two bottom ends vertical roller restraints and load the upper midpoint downward.
- `m11_two_right_edge_down` (heldout, 7/9): Left-clamped beam with downward point loads at the upper and lower right-edge locations.
- `m12_vertical_load_pair` (heldout, 8/9): Left-fixed beam with one downward force at the upper free corner and one upward force at the lower free corner.
- `m13_same_point_two_components` (heldout, 6/9): At the right midpoint of a left-clamped beam, apply a downward load and a smaller load pointing left.
- `m14_deck_pressure_midpoint` (heldout, 6/9): Use bottom vertical support, top downward pressure, and an additional downward point force at the top-center.
- `m15_three_free_edge_forces` (heldout, 8/9): Cantilever with three equal downward loads at quarter, half, and three-quarter height on the free side.
- `m16_bracket_pull_and_drop` (heldout, 7/9): Top-fixed bracket with a horizontal lower-right pull and a downward force at the outer corner.
- `m17_mbb_two_down_loads` (heldout, 6/9): MBB setup with the normal upper-left load plus a smaller top-midspan downward point load.
- `m18_deep_beam_two_components` (heldout, 4/9): Short deep beam fixed left, with vertical downward and horizontal rightward loads at the free-side midpoint.
- `m20_two_tip_loads` (heldout, 6/9): Long cantilever with two downward loads placed just above and below the free-end center.
- `v15_opening_and_insert` (heldout, 8/9): Cantilever with both a middle circular void and a protected solid load pad at the free end.
- `v16_rectangular_window` (heldout, 8/9): Cantilever containing a rectangular non-design window in the center region.
- `v17_bridge_service_hole` (heldout, 4/9): Bridge span with a circular service void at midspan under a distributed top load.
- `v18_mbb_central_void` (heldout, 5/9): Standard MBB beam but reserve a small circular void in the domain center.
- `v19_square_bracket_pad` (heldout, 5/9): Top-fixed square bracket with a rectangular protected solid pad at the lower-right pull location.
- `v20_long_bar_root_hole` (heldout, 5/9): Long left-fixed cantilever with a small circular root-side lightening hole.
- `a12_below_opening` (heldout, 7/9): Put the load below the circular opening in a clamped beam.
- `a13_lower_bracket_side` (heldout, 7/9): Pull on the lower right-side area of a top-fixed bracket.
- `a14_base_supports` (heldout, 4/9): Support the base area and apply a force on the far side of the beam.
- `a19_deck_like_load` (heldout, 5/9): Use deck-like loading with support along the underside.
