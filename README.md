# nhisokfchat — a grounded health-stats chat on Bedrock AgentCore, with no vector database

Ask a natural-language question about U.S. health survey data and get back a **survey-weighted,
execution-verified figure with its citation and confidence interval** — or a clean refusal when
the answer isn't in the verified corpus. The whole thing deploys as a single **AgentCore
CodeZip** (well under the 250 MB limit). There is no vector store, no chunking service, and no
embeddings endpoint.

```
$ agentcore invoke --prompt "What share of U.S. adults with diagnosed diabetes take insulin?"
> 31.96% (95% CI 30.08–33.84%) of U.S. adults with diagnosed diabetes currently take
> insulin [DIBINS_A]. Survey-weighted, NHIS 2023. (Not medical advice.)

$ agentcore invoke --prompt "What is the prevalence of asthma among US adults?"
> I cannot answer this from the verified bundle — there is no asthma concept, and I don't
> invent numbers. (See CDC NCHS for authoritative asthma statistics.)
```

More real transcripts in [docs/SAMPLE.md](docs/SAMPLE.md).

## The idea: OKF + AgentCore

**OKF (Open Knowledge Format)** is a directory of markdown files with YAML frontmatter — one
per verified _concept_. Each file here isn't a query recipe or a raw doc; it's an **answer that
already passed execution-grounded verification**: the documented analysis was _run_ against the
real CDC NHIS microdata with proper survey weights, and only the concepts whose numbers checked
out were written to the bundle. A statistic that is structurally clean but statistically wrong
(ignores the survey weights, or breaks a skip-pattern) is **quarantined** — it never becomes a
file, so it can never be retrieved.

That upstream curation is what removes the vector database:

```
raw microdata → execution-grounded verification → verified .okf/ markdown → in-process retrieval → LLM
```

**Grounding is enforced by what exists, not by prompt instructions.** The agent has two
aggregate-only windows onto the data: `tool_search_okf` (retrieval over the bundle that
ships inside the CodeZip) and `tool_analyze_rows` (a survey-weighted computation, restricted
to verified variables, over a slim NHIS parquet shipped beside the code). A quarantined figure is
physically absent from the bundle, so it is unreachable; there is no raw-row tool at all.

## Why AgentCore is the cornerstone

AgentCore Runtime accepts a **direct-code (CodeZip) deployment up to 250 MB compressed**. That
budget is the enabling constraint: it's enough to carry the **entire verified knowledge bundle,
the retrieval engine, and a slim NHIS parquet for query-time weighted computation inside the
deployable artifact** — so the "knowledge base" is the CodeZip itself, not a managed vector
cluster you provision, sync, and pay for. Deploy the zip, and the grounded corpus goes with it.

## Deploy it

Prerequisites: an AWS account with Bedrock (Claude Sonnet) model access, the
[`agentcore` CLI](https://github.com/aws/agentcore-cli) (`npm i -g @aws/agentcore`), Node 20+,
and CDK bootstrapped in your region.

```bash
agentcore deploy                           # build the CodeZip → CloudFormation → AgentCore runtime
agentcore invoke --prompt "..."            # ask the deployed agent
agentcore status                           # runtime ARN + health
agentcore remove all && agentcore deploy   # tear it down
```

The runtime entrypoint (`app/nhisokfchat/main.py`) is the whole deployed surface: it defines
the `BedrockAgentCoreApp`, wraps the two aggregate-only tools, and builds the Strands agent;
its `invoke` parses the incoming question and runs that agent — whose two tools read only the
verified bundle and the slim parquet — falling back to a cited extractive answer when Bedrock
is unavailable.

## The two tools

- **`tool_search_okf`** — retrieval over the verified OKF bundle. Answers from a precomputed
  concept, cites the concept id (e.g. `[DIBINS_A]`), quotes the figure + design-based CI.
- **`tool_analyze_rows`** — a deterministic, survey-weighted computation (percentage/mean/
  quantile + design-based CI) for an _ad-hoc subgroup_ a concept does not already carry. It is
  restricted to **verified variables only**, returns **aggregate cells only — never raw rows**,
  and its agent-supplied `universe` filter passes an **allow-list validator** (`COLUMN <op>
NUMBER` joined by `& | ( )` over known columns) before any `df.eval` — so the injection sink is
  closed. It refuses rather than guessing.

There is **no raw-row tool** in the deploy: individual-record inspection is a deliberately
local-only capability that never ships here.

## How it answers (and refuses)

- **Aggregate-only + grounded-or-refuse.** The agent quotes only survey-weighted figures — a
  verified concept's or a freshly computed subgroup's — cites the source, states the
  universe/weight basis, and refuses rather than guess when nothing matches or the variable is
  not verified.
- **Design-based confidence intervals.** Every prevalence carries a Taylor-linearization CI over
  the survey's strata/PSUs (not a naive simple-random-sampling interval).
- **Safety scope.** Public, de-identified, **aggregate** survey data only — not medical advice,
  no individual-level inference. Every figure carries its survey-weighted basis and source.

## What's in the bundle

Four verified NHIS 2023 diabetes concepts: diagnosed-diabetes prevalence (`DIBEV_A`), insulin
use _among diagnosed diabetics_ (`DIBINS_A` — the skip-pattern the verifier gets right),
prediabetes (`PREDIB_A`), and age at diagnosis (`DIBAGETC_A`). See
`app/nhisokfchat/nhis_okf/okf_bundle/`.

## Layout

```
nhisokfchat/
├── agentcore/            # AgentCore CLI project (agentcore.json + generated cdk/)
└── app/nhisokfchat/
    ├── main.py           # the AgentCore entrypoint: BedrockAgentCoreApp + the two @tool wrappers + the Strands agent
    ├── nhis_okf/         # the serve-path (two aggregate tools — nothing else ships)
    │   ├── chat.py           # the agent's brain: system prompt + the two tool-logic functions
    │   ├── helpers.py        # plumbing: retrieval, answer formatting, microdata loader, universe gate, model builder
    │   ├── retrieval.py      # in-process TF-IDF retrieval over the verified bundle
    │   ├── analysis.py       # the survey-weighted engine + the universe allow-list validator
    │   ├── registry.py       # ground-truth variable metadata (weights, universes, valid codes)
    │   ├── config.py         # bundle/microdata/model/region resolution
    │   ├── __init__.py
    │   ├── okf_bundle/       # the verified OKF bundle (ships in the CodeZip)
    │   └── microdata/        # slim NHIS 2023 parquet (only the verified + design columns)
    └── pyproject.toml    # retrieval + aggregate-compute deps (sklearn + pandas/pyarrow)
```

**Aggregate-only is physical, not just configured.** The deployed surface is `main.py` plus the
`nhis_okf` modules the two-tool serve-path imports. The build-time modules (`compiler`, `verify`,
`trends`, `concepts`, `cli`) and — critically — the raw-row tool (`parquet_query`) are simply
**absent** from the CodeZip, so the deployed artifact has **no row path** and both tools return
aggregates only. The one query-time `df.eval` (in `analysis`) is reachable only through
`tool_analyze_rows`, whose agent-supplied universe must first pass the allow-list validator —
so the injection sink is closed by construction, not by prompt. (The full weighted-statistics
engine and the local raw-row tool live in the lab repo.)

## Where this comes from

This is the clean, deployable version. Development, the execution-grounded **verifier**, the full
weighted-statistics engine, the test suite, and the change history live in the lab repo:
[nhis-okf-compiler](https://github.com/andrewwint/nhis-okf-compiler). The verified bundle here is
compiled there and vendored in.
