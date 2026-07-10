---
type: Reference
title: "Researcher row-query tool (nhis rows)"
description: "How to inspect raw public-use NHIS rows with `nhis rows`, and how it differs from the verified `nhis analyze` aggregate path."
resource: "https://www.cdc.gov/nchs/nhis/2023nhis.htm"
tags: [nhis-2023, diabetes, tool, reference, researcher]
# extension keys (OKF consumers tolerate unknown fields)
id: references/parquet_query
tool: nhis rows
module: nhis_okf.parquet_query
source: "NHIS 2023 Sample Adult public-use file (adult23.csv)"
---

# Researcher row-query tool (`nhis rows`)

This bundle supports two **deterministic** retrieval modes. The value is deterministic
tools — cited, reproducible numbers — not an LLM guessing a query:

1. **Column-level lookup of verified concepts + trends.** Read the precomputed,
   survey-weighted aggregate straight from a verified concept in
   [variables/](../variables/) (or a cross-year trend). Each figure is already executed,
   design-based, and cited — no computation at read time. This is the path the verified
   product and the grounded agent use, and it is the only path that yields a population
   estimate. Use it whenever you need *the answer*.

2. **Row-level query via `nhis rows`.** A deterministic lookup of a few columns of the
   underlying public-use rows, to build a small table or ground/sanity-check a response
   against the raw records. Use it when you need to *see the underlying data*, not an
   estimate.

## Purpose

`nhis rows` returns selected columns of the individual rows matching a universe
expression, read from the parquet-preferring load path. NHIS public-use files are
de-identified and top-coded so row inspection is their intended use, which is why this
tool is safe here — and only here.

## Usage

```bash
nhis rows --columns "DIBEV_A,DIBINS_A,SEX_A" --universe "DIBEV_A == 1" --limit 5
```

- `--columns` (**required**): comma-separated column names. There is no default — an
  explicit list is mandatory so the tool never dumps every column. At most 12 columns
  (a few columns, never a wide/full-width dump).
- `--universe` (optional): a pandas row filter, e.g. `DIBEV_A == 1`. Omit it to scan all
  sample adults (still capped by `--limit`).
- `--limit` (default 20, hard max 500): bounds the number of rows returned so an
  inspection never becomes a bulk export.

## Caveats — read before using a number from this tool

- **Raw and UNWEIGHTED.** These are individual records. Without the survey weight
  (`WTFA_A`) and the complex-survey design, a count or rate read off them does **not**
  estimate the U.S. population. It is not a population figure.
- **Not verified.** Unlike a compiled concept, row output passes through no
  execution-grounded verification gate. It is exactly the surface where an unweighted
  number could be mistaken for an estimate — hence the loud caveat header on every call.
- **Column caveats.** Non-substantive codes (e.g. 7/8/9 refused/not-ascertained/don't-know,
  or 96–99 on continuous items) appear verbatim; they are not dropped or labeled. Interpret
  raw codes against the variable's registry definition, not at face value.

## From a raw row inspection to a verified aggregate

When you actually need the population figure, switch to the verified, survey-weighted path:

```bash
nhis analyze --variable DIBINS_A --universe "DIBEV_A == 1"
```

`nhis analyze` returns a single survey-weighted estimate with a design-based confidence
interval — never individual rows — and is restricted to variables backed by a verified
concept. That is the number to cite; `nhis rows` is only for inspecting the records behind
it.

## Related

- [index](../index.md)
