# Geometric export contract

After all three geometric checks pass, export the physical cam and separate roller-centre pitch curve as polylines. A requested tolerance from 0.0001 through 1 mm bounds the Euclidean distance between each continuous curve and its serialized polyline. More specifically, for every angle within a chord's interval, the same-parameter linear interpolant is within the reported bound; this also bounds the two-sided curve-to-polyline distance.

Numeric inputs use the bounded ASCII fixed-decimal parser documented in `../README.md`. Lexical validation, length, magnitude and fractional-place bounds precede rational construction. Scientific notation and rational literals are unsupported. This includes the tolerance argument.

An export interval never crosses a motion join. The motion is C2, but the physical normal offset may have a second-derivative jump there. Each polynomial segment is checked separately and its endpoints are always emitted. A canonical endpoint cache supplies the actual shared serialized coordinate used by the next interval. Closure uses the zero-angle coordinate at 360°.

Let the pitch curve be `p=R·e_r`, its outward normal be `N`, and the physical curve be `q=p−roller·N`. In radians, use `v=R'`, `a=R''`, `j=R'''`, `S=R²+v²`, `K=R²+2v²−Ra`. The normal's angle is `φ=θ−atan(v/R)`, so:

```text
K' = 2Rv + 3va − Rj
S' = 2v(R+a)
φ' = K/S
φ'' = (K'S − KS') / S²
||p''|| <= |a−R| + 2|v|
||N''|| <= |φ''| + |φ'|²
||q''|| <= ||p''|| + roller·||N''||
```

Bernstein ranges enclose `R,v,a,j` over each whole interval. Division is used only when the radius range is strictly positive; then `S >= R_min² > 0`. Otherwise the interval is refined. All range operations are rational interval operations. For a second-derivative bound `M` in mm/rad² and angular width `Δθ` in radians, the vector interpolation bound is `M·Δθ²/8` in millimetres. The norm is Euclidean. It follows by applying the scalar interpolation remainder to every unit-vector projection, equivalently the Peano-kernel norm bound.

Endpoint sine and cosine use exact rational degree reduction to ±45°, a degree-24 Taylor polynomial, and the Lagrange remainder bound `|θ|²⁵/25!`. Pi comes from the bounded Machin computation and is rounded outward to 34 decimal places. Square roots use scaled integer square roots rounded outward to 32 decimal places. Points are written directly as 12-place decimals, with the maximum endpoint vector error conservatively bounded by the sum of the two coordinate errors. The same decimals supply CSV and SVG; SVG negates y exactly. The stroke width is presentation, not part of the mathematical polyline.

The final chord bound adds the larger endpoint error to `M·Δθ²/8`. Derivative, angle-width, and endpoint-error values are rounded outward before the bound is calculated, and the bound itself is rounded outward. The JSON certificate therefore reconstructs the accepted inequality using compact decimal numbers. It includes every angle interval, both bounds, units, tolerance, and work counts.

A shared limit bounds adaptive interval evaluations and a depth limit bounds refinement. Exhaustion yields `unknown` with no output files. The application computes the full partition and file contents in memory, then makes a complete ZIP before returning a geometry download. No HTTP request selects a filesystem path. The budget is an operation count, not a hard wall-clock deadline; geometric feasibility checks have their own bounded work limit. The application worker has a separate 30-second deadline; timeout kills and reaps it and supplies no geometry download.

This establishes an approximation bound for the stated mathematical model. It does not certify dynamic behaviour, dimensions after cutting, cutter compensation, stress, roller contact under load, or hardware fitness. Native CAD import and real machining have not been exercised.
