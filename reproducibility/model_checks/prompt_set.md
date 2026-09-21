# Fixed Prompt Set for Live Multi-Model Runs

Use these prompts without editing across all model conditions.

## Canonical Prompts

M1. Configure a 2:1 cantilever beam with the left edge fixed, a downward point
load at the midpoint of the right edge, and 50 percent material.

M2. Configure a 3:1 MBB beam with symmetry on the left edge, a vertical roller
support at the bottom-right corner, a downward load at the top-left corner, and
50 percent material.

M3. Configure a cantilever beam with the left edge fixed, a downward load at
the right-edge midpoint, a circular pipe hole at the center with radius 0.15,
and 40 percent material.

## Challenge Prompts

M4. Make a long bridge-like domain, about 6:1, with supports at both bottom
ends and a distributed downward load along the top.

M5. Configure an L-bracket with the top edge attached to a wall and a horizontal
load on the lower part of the right edge.

M6. Put a downward force near the right side under the hole, with the left edge
fixed.

M7. Configure a short deep cantilever, fixed on the left wall, with two downward
loads at the upper and lower right corners.

M8. Configure a normalized multi-load mounting bracket in a 4.0 by 1.5 design
envelope. Clamp the left mounting edge. Add two bolt-clearance holes near the
mount, a protected solid pad at the far right, and combined downward and
backward loads at the protected pad. Use 35 percent material.

## Invalid or Warning Prompts

M9. Configure a cantilever with only a load and no support.

M10. Configure a steel bracket in millimeters with a 3 kN real service load
using default material values.
