## 2024-05-24 - [Combine openpyxl Iterations for Styling]
**Learning:** In openpyxl, running `iter_rows` to set baseline cell styles and then immediately running `iter_cols` over the same region to conditionally format specific columns is a severe anti-pattern. This double-pass over the cells introduces massive overhead due to the constant creation and evaluation of `StyleProxy` objects.
**Action:** When applying styles in openpyxl, always consolidate formatting into a single O(N) pass. Compute the column index during the `iter_rows` loop and apply column-specific rules inline, eliminating the need to ever invoke `iter_cols` on the same worksheet area.
## 2026-03-23 - [Optimizing pandas NaNs in scalar row loops]
**Learning:** Calling `pd.isna()` inside Python inner loops (e.g. while iterating through rows using `to_dict('index').items()`) adds massive overhead due to Pandas internal array-based type checking.
**Action:** For scalar values in tight loops, use native Python inline checks: `val != val or val is None`. This leverages the property that IEEE 754 `NaN != NaN` evaluates to `True`, achieving the exact same result as `pd.isna` for standard types but much faster.
