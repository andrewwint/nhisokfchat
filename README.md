# nhisokfchat — a grounded health-stats chat on Bedrock AgentCore, with no vector database

Ask a natural-language question about U.S. health survey data and get back a **survey-weighted,
execution-verified figure with its citation and confidence interval** — or a clean refusal when
the answer isn't in the verified corpus. The whole thing deploys as a single **~93 MB AgentCore
CodeZip**. There is no vector store, no chunking service, and no embeddings endpoint.

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
per verified *concept*. Each file here isn't a query recipe or a raw doc; it's an **answer that
already passed execution-grounded verification**: the documented analysis was *run* against the
real CDC NHIS microdata with proper survey weights, and only the concepts whose numbers checked
out were written to the bundle. A statistic that is structurally clean but statistically wrong
(ignores the survey weights, or breaks a skip-pattern) is **quarantined** — it never becomes a
file, so it can never be retrieved.

That upstream curation is what removes the vector database:

```
raw microdata → execution-grounded verification → verified .okf/ markdown → in-process retrieval → LLM
```

**Grounding is enforced by what exists, not by prompt instructions.** The agent's only window
onto the data is `search_verified_okf`, retrieval over the bundle that ships inside the CodeZip.
A quarantined figure is physically absent, so it is unreachable.

## Why AgentCore is the cornerstone

AgentCore Runtime accepts a **direct-code (CodeZip) deployment up to 250 MB compressed**. That
budget is the enabling constraint: it's enough to carry the **entire verified knowledge bundle
plus a pure-Python retrieval engine inside the deployable artifact** — so the "knowledge base"
is the CodeZip itself, not a managed vector cluster you provision, sync, and pay for. Deploy the
zip, and the grounded corpus goes with it. This runtime is retrieval-only (no pandas), ~93 MB.

## Deploy it

Prerequisites: an AWS account with Bedrock (Claude Sonnet) model access, the
[`agentcore` CLI](https://github.com/aws/agentcore-cli) (`npm i -g @aws/agentcore`), Node 20+,
and CDK bootstrapped in your region.

```bash
agentcore deploy                 # build the CodeZip → CloudFormation → AgentCore runtime
agentcore invoke --prompt "..."  # ask the deployed agent
agentcore status                 # runtime ARN + health
agentcore remove all && agentcore deploy   # tear it down
```

The runtime entrypoint (`app/nhisokfchat/main.py`) is a thin shim: it re-exports the reviewed
agent from the vendored `nhis_okf` package and pins it to retrieval-only, grounded mode.

## How it answers (and refuses)

- **Retrieval-only + grounded-or-refuse.** The agent quotes only the survey-weighted figure a
  verified concept carries, cites its concept id (e.g. `[DIBINS_A]`), states the universe/weight
  basis, and refuses rather than guess when nothing matches.
- **Design-based confidence intervals.** Every prevalence carries a Taylor-linearization CI over
  the survey's strata/PSUs (not a naive simple-random-sampling interval).
- **Safety scope.** Public, de-identified, **aggregate** survey data only — not medical advice,
  no individual-level inference. Every figure carries its survey-weighted basis and source.

## What's in the bundle

Verified NHIS 2023 concepts across a diabetes and hypertension slice — e.g. diagnosed-diabetes
prevalence, insulin use *among diagnosed diabetics* (the skip-pattern the verifier gets right),
age at diagnosis, weight/height, hypertension-medication use — plus a cross-year diabetes trend
that survives the 2019 NHIS redesign rename. See `app/nhisokfchat/nhis_okf/okf_bundle/`.

## Layout

```
nhisokfchat/
├── agentcore/            # AgentCore CLI project (agentcore.json + generated cdk/)
└── app/nhisokfchat/
    ├── main.py           # thin entrypoint — re-exports the nhis_okf agent
    ├── nhis_okf/         # the engine (retrieval + the grounded agent)
    │   └── okf_bundle/   # the verified OKF bundle (ships in the CodeZip)
    └── pyproject.toml    # retrieval-only deps (no pandas)
```

## Where this comes from

This is the clean, deployable version. Development, the execution-grounded **verifier**, the full
weighted-statistics engine, the test suite, and the change history live in the lab repo:
[nhis-okf-compiler](https://github.com/andrewwint/nhis-okf-compiler). The verified bundle here is
compiled there and vendored in.
