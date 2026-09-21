# Post-Solve Retry Recovery Summary

- Cases: 12
- Initial iteration budget: 10
- Retry iteration floor: 80
- Failure injection: uniform_gray_density
- Initial failures: 12/12
- Recovered after retry: 12/12
- Final passed: 12/12
- Mean attempts: 2.00

## Per Case
- cantilever_basic: first=False failures=grayness; final=True attempts=2
- mbb_beam: first=False failures=grayness; final=True attempts=2
- bridge: first=False failures=grayness,convergence; final=True attempts=2
- cantilever_with_hole: first=False failures=grayness; final=True attempts=2
- deep_beam_shear: first=False failures=grayness; final=True attempts=2
- simply_supported_center: first=False failures=grayness; final=True attempts=2
- cantilever_low_vf: first=False failures=grayness; final=True attempts=2
- dual_load: first=False failures=grayness; final=True attempts=2
- lbracket: first=False failures=grayness; final=True attempts=2
- high_aspect: first=False failures=grayness; final=True attempts=2
- retry_rect_void_cantilever: first=False failures=grayness; final=True attempts=2
- retry_void_and_pad_cantilever: first=False failures=grayness; final=True attempts=2
