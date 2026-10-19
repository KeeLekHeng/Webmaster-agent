# Website Guardian — Project Blueprint

**Status:** Milestones 1–4 implemented locally, with the first owner-approved PR published. Scheduled operation and external notifications remain disabled; publishing is manual and approval-gated, with no merge/deployment operation. **Initial site:** `https://estateplanning.com.my/`. **Owner:** Repository maintainer. **Last updated:** 2026-10-19.

## 1. Why we are building this
The owner maintains a family business website infrequently and wants a dependable, low-overhead way to detect and investigate website maintenance problems. The project is simultaneously (a) a hands-on agent engineering project using LangGraph and (b) an experiment in whether an AI-assisted website-care service would help small businesses. Commercial demand is **not validated**.

### Intended outcome
A Website Guardian can periodically run objective checks, explain important findings with evidence, track change over time, propose safe next steps, and request human involvement before higher-risk actions. Initially, it should **observe and advise**, not autonomously maintain production.

### What this is not
Not a general chatbot, OpenClaw clone, autonomous system administrator, guaranteed vulnerability scanner, legal/compliance adviser, or substitute for backups and professional security review.

## 2. Scope by stage
| Stage | Capabilities | Explicit exclusions |
| --- | --- | --- |
| V0: Discovery | Confirm stack/deployment/repo access, inventory existing tools, evaluate host isolation and resources | No production changes, no credential reads |
| V1: Read-only Guardian | Manual audit; health, TLS, basic internal links and metadata; existing approved scanner results if available; structured findings and report; saved audit history | No code pushes, production tests, write access, unattended remediation |
| V1.5: Scheduled observation | Safe scheduled audits, deduplicated findings, notifications, audit comparison, stop switch | No silent auto-fixing |
| V2: Assisted remediation | Read-only repository inspection, scoped dependency analysis, isolated patch proposal/testing, approval workflow and PRs after authorization | No agent-driven merge or production deploy |
| V3: Growth intelligence | Performance + technical SEO, optional Search Console/analytics, approved business-relevant recommendations | No invented traffic or conversion conclusions |
| Future: Service | Multiple websites, separate customer credentials, audit segregation, subscriptions/service delivery after pilots | Multi-tenancy not required for V1 |

## 3. First target: useful audit, not number of findings
A successful first run:
- Collects **real** evidence for selected checks of `estateplanning.com.my`.
- Produces a human-readable report including checks passed, findings (possibly zero), evidence links, timestamp, severity, confidence, actionable next steps, and limitations.
- Records history to compare subsequent audits.
- Leaves the live website, repository, data and server configuration unchanged.

Never force an arbitrary number of vulnerabilities/findings merely to meet a demo target.

## 4. Early capabilities and value
1. **Reliability:** uptime/reachability, redirect behavior, TLS expiry, failed links, basic public-page availability.
2. **Technical hygiene:** framework/dependency inventory from source (once approved); package alerts, existing CI/test failures, security configuration review.
3. **Technical SEO:** titles, descriptions, canonical, robots/sitemap, response codes; later Search Console when explicitly integrated.
4. **Performance:** Lighthouse/PageSpeed measurements, repeatable baselines and regression explanation.
5. **Business-critical flows:** monitor availability of contact endpoints safely; later test form delivery only with pre-authorized synthetic accounts and cleanup plan.
6. **Change management:** explain findings, propose bounded fixes, prepare reviewable patches after future authorization.
7. **Reporting:** concise weekly summary, severity trends, known issue tracking, and escalation.

**Agent-value test:** If a deterministic tool can do it reliably, use that tool. Use the LLM to decide *which evidence to examine*, synthesize relationships, explain trade-offs, and propose next steps.

## 5. Guiding principles
- Gradual autonomy: observe → investigate → prepare fix → execute only specifically approved actions.
- A/H+A/H decision rights enforced in server-side code and credentials, not in prompts.
- Independent operation: agent is not part of the website's runtime or database.
- Temporary same-host installation is a deployment compromise, not an architectural dependency.
- Minimal access, inspectable audit logs, human override, safe failure.
- Human in control of production; explicit accountable approval and evidence for decisions.
- Prefer portable interfaces over vendor lock-in; LangGraph is an orchestration choice, not the product's value proposition.
- Investigate commercial demand through pilots; don't build SaaS billing/multi-tenancy prematurely.

## 6. Important assumptions to verify
| Assumption | Status / how to verify |
| --- | --- |
| The source is in a separate private GitHub repository | User-reported; verify repo identity, access scope and default branch |
| Codex currently has SSH / repository access | User-reported; confirm exact read/write permissions, do not infer authorization |
| The existing hosting environment can support an agent | Unknown; inspect CPU/RAM, process isolation, outbound network, backups and deployment model |
| The site uses a specific framework/package manager | Unknown; inspect source before choosing scanners |
| Search Console/analytics are configured | Unknown; verify without requesting unnecessary data |
| Contact form delivery is functional | Unknown; don't test with live submissions until approved |
| SMEs will pay for maintenance | Hypothesis; validate with interviews and service pilots |

## 7. Success measures
**Technical:** successful scheduled/manual scans, reproducible findings, low false positives, no unauthorized changes, clear source provenance, timely detection, safe error handling. Set numeric thresholds after a baseline rather than inventing them.

**Operator:** owner can understand the top actionable issues in minutes, approve/reject changes when introduced, and stop operation at any time.

**Business (later):** customer-reported usefulness, avoided outages/missed leads, time saved, willingness to pay; distinguish measured effects from estimates.

## 8. Repository documents
- [`ARCHITECTURE_AND_SECURITY.md`](ARCHITECTURE_AND_SECURITY.md): systems, trust boundaries, handoff, policies, hosting migration.
- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md): milestones, acceptance tests, and Codex instructions.
- Root [`AGENTS.md`](../AGENTS.md): instructions and safety requirements for coding agents.
- `DISCOVERY.md` to be produced after a read-only codebase inspection.

## 9. Origin of governance concepts
Adapted from the user's *PE6202 Group Project 2 — Appendix*, especially Appendix A's A / H+A / H, five systems, S/D/C/P trust hotspots, L1–L5 security layers, exceptions, autonomy ladder and test requirements. These are **design heuristics**, not a compliance certification. The appendix includes Singapore-specific regulatory references; Malaysian legal obligations require separate verification before commercialization.
