# Reflection (≤1 page)

**Which fault types were hardest to catch, and why?**

The subtle statistical faults were the hardest because their values can sit near
normal clean-stream variation. A strict published 3-sigma boundary had excellent
precision but missed several subtle cases on the public stream. Missing-upstream
lineage was also less direct than schema or type violations: the returned graph
still contained an upstream edge, so checking only for an empty list was not
enough. I therefore combined the documented limits with graph invariants and
used an inner, approximately 2.5-sigma range for the statistical checks most
likely to contain subtle drift.

**What would you change about your cost/coverage tradeoff, if you had another pass?**

I chose one metered call per event. This gives complete signal coverage and fits
the private budget (about 300 credits for 200 events against a 320-credit
budget), although the same policy slightly exceeds the smaller public budget.
With another pass, I would collect more clean history per source, feature view,
and corpus, then replace the fixed inner thresholds with robust rolling
quantiles. That could adapt to legitimate source-specific variance and recover
some precision without dropping coverage. I would keep the exact contract and
lineage checks because they are inexpensive and produced strong, interpretable
signals.
