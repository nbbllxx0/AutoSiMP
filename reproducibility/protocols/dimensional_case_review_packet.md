# Dimensional Bracket Review Candidate

## Purpose

This packet adds a dimensional candidate case for future independent
engineering review. It is intended to make the review actionable by specifying
units, material assumptions, load cases, and acceptance criteria.

It is not reported as validated engineering evidence in the manuscript.

## Candidate Component Class

- Small robotics mounting-bracket surrogate.
- Two-dimensional topology-optimization abstraction of a flat plate-like arm.
- Fixed left mounting edge, two bolt-clearance voids near the mount, and a
  protected motor pad at the distal end.

## Dimensional Inputs

The machine-readable source of truth is `dimensional_bracket_case.json`.

Key assumptions:

- Design envelope: 120 mm by 45 mm by 6 mm.
- Material assumption: aluminum 6061-T6 with nominal elastic modulus 69 GPa,
  Poisson ratio 0.33, and nominal yield strength 276 MPa.
- Loads at the motor-pad center:
  - LC1: 35 N downward.
  - LC2: 15 N backward.
  - LC3: combined 15 N backward and 35 N downward.
- Bolt-clearance holes: two 3.6 mm radius circular voids near the mount.
- Protected motor pad: 109.5 mm to 120 mm in x and 16.5 mm to 28.5 mm in y.

These values are candidate assumptions for review. They must be checked
against an intended application, supplier material data, fastener details,
load spectra, manufacturing process, and safety standard before any design use.

## Mapping to the Manuscript Case

The dimensional envelope maps to the normalized manuscript bracket by a
30 mm per normalized-unit scale:

- 120 mm by 45 mm maps to 4.0 by 1.5.
- Motor-pad load point (120 mm, 22.5 mm) maps to (4.0, 0.75).
- Bolt-clearance centers (16.5 mm, 13.5 mm) and (16.5 mm, 31.5 mm) map to
  (0.55, 0.45) and (0.55, 1.05).
- Bolt radius 3.6 mm maps to 0.12.
- Motor pad maps to x = 3.65 to 4.0 and y = 0.55 to 0.95.

## Review Questions

An independent reviewer should answer:

- Are the dimensional load magnitudes plausible for the stated illustrative
  bracket class?
- Is the fixed-edge surrogate appropriate for the intended mounting interface?
- Is a point-load representation at the motor pad acceptable for workflow
  evidence, or should the load be distributed over a pad/contact region?
- Are the bolt-clearance void and protected motor-pad assumptions
  interpretable?
- What additional real engineering requirements are missing?
- Should the manuscript continue to describe this case only as workflow
  evidence?

## Required Missing Items Before Certification

At minimum, a certified engineering case would require:

- application-specific load spectra and safety factors;
- fastener preload, contact, and mounting stiffness assumptions;
- material certificate or supplier-specific allowables;
- manufacturing constraints and minimum feature-size rules;
- stress, buckling, fatigue, and displacement checks in a validated FEA model;
- independent review sign-off under an applicable design standard.

## Reporting Boundary

This packet supports future review readiness. Until a qualified independent
reviewer completes `review_signoff_template.md`, the manuscript must not claim
engineering validation, safety, or suitability for a real component.
