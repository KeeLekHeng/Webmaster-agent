# Website Guardian — Architecture, Decision Rights & Security

**Design intent:** Agent and website are separate services from day one, even while temporarily deployed on the same host.

## 1. Logical components
```text
Manual CLI / future scheduler
            |
            v
       Audit orchestrator ----------------> Append-only/redacted audit log
            |
            v
  Deterministic read-only checks --------> Findings + evidence (site/configuration/scanner outputs)
            |
            v
       LangGraph investigation -----------> Structured priorities / uncertainty / next actions
            |
            v
   Policy / approval service ------------> Report + operator notification
            |
     [future, H+A]
            v
 Isolated proposed patch + tests -------> PR after exact approval
            |
     [H, separately]
            v
 Human-controlled merge / deployment
```

Keep scanner tools, reasoning, authorization, persistence and notification interfaces independent. The LLM does not execute arbitrary shell commands or select credentials directly. LangGraph checkpoints are **not** a substitute for a durable authorization or audit system.

## 2. Hosting: now versus later
### Temporary V1 — same host as website
- Separate service/container and identity; no use of the web application's credentials or runtime paths.
- Restrict network and filesystem; prefer outbound-only probes and no externally exposed agent port. Keep management interface local or authenticated.
- Enforce CPU/memory/disk/process limits, logging limits and scheduling away from peak loads.
- Separate secret store/config; read-only tokens when repository access is introduced; never mount host Docker socket, root SSH keys, website `.env`, customer data, or production database.
- Ensure site monitoring continues even if the agent crashes, and disabling the agent cannot stop the website.
- Verify available capacity and isolation **before** installing. If inadequate, develop locally or move directly to dedicated hosting.
- Note: same physical host remains a shared failure/compromise domain. Containers do not eliminate host-level risk.

### Intended architecture — dedicated agent server / platform
- Agent server hosts scheduler, LangGraph runtime, persistence, tool workers and policy engine.
- Each website is an independently configured target: base URL, allowed hosts/routes, repo integration, permissible checks, schedule, approval roles, notification route.
- Communication is via HTTPS/site probes, scoped GitHub APIs, and explicit monitoring interfaces; never assume shared filesystem or localhost access.
- No permanent unrestricted SSH access to client website servers. If operational access becomes necessary, provide site-specific narrowly scoped, audited connector and explicit H approval.
- When serving multiple clients, enforce per-tenant isolation of credentials, reports, audit history, approval records, and execution resources **before** onboarding them.

### Portability requirements
Configuration-driven `site_id`, `base_url`, allowed targets, repository config, check profiles, retention and alert destinations. Abstract scheduler, storage and notification backends. Avoid hard-coded absolute filesystem paths or in-process dependencies on the website application.

## 3. Trust boundaries and data paths
| Boundary | Example crossing | Required protection |
| --- | --- | --- |
| Internet/public site → scanner | HTML, headers, redirects | Explicit domain allowlist, SSRF/redirect checks, strict timeouts/rate limits, parse as data |
| Scanner/tool output → LLM | Untrusted page/repo text | Label as untrusted data, constrain tool schema, never allow embedded instructions to alter policy |
| Agent → GitHub | Read repository or propose PR | Scoped token/GitHub App, separate read/write credentials, approval-gated writes |
| Agent → storage | Findings, summaries, tool traces | Data minimization, access control, redaction, retention, encryption as appropriate |
| Agent → production environment | Potential future diagnostics | No access in V1; dedicated audited least-privilege connector only if justified |
| Agent → external model API | Content and traces | Minimize exposure of confidential/customer data, assess provider settings and retention |
| Proposed action → executor | Patch, PR, command | Policy checks independent of model, resource constraints, immutable approval binding |
| Human → approval service | Accept/reject decision | Authenticated identity, exact artifact hash, expiry, action logs |

**SSRF caution:** Resolve and validate target hosts/redirects against an allowlist; disallow localhost, link-local, private network and metadata services unless explicitly configured in a separately isolated testing mode. Prevent untrusted URLs from becoming arbitrary scan targets.

## 4. PE6202 decision-rights model
- **A — Agent alone:** bounded, low-risk, permitted action performed automatically.
- **H+A — Agent + human:** agent proposes; *named, authenticated human* approves the exact action before a restricted executor runs it.
- **H — Human only:** agent may explain or prepare documentation but cannot perform the final action.

| Action | V1 right | Future possible right | Enforced by |
| --- | --- | --- | --- |
| Probe allowlisted public URLs, check TLS | A | A | Tool allowlists, limits, schedule |
| Parse public metadata / report broken links | A | A | Read-only tools |
| Explain and prioritize findings | A (advice) | A | Evidence-backed output schema |
| Read private website repository | Not enabled until approved | A, with scoped read-only credentials | Repository integration policy |
| Prepare patch in isolated workspace | Not enabled | A with sandbox constraints | Isolated patch tool |
| Open GitHub PR | Not enabled | H+A initially | Authenticated approval + scoped writer |
| Merge PR / deploy production | H | H | External CI/protected branch / operator role |
| Modify DNS, credentials, firewall, backups | H | H | No agent tool or credentials |
| Access private customer submissions | H; avoid | H with explicit lawful authorization | Data access policy |
| Send notifications/reports | A to pre-approved owner destinations | A within routing/rate limits | Notification allowlist |

**Approval rules:** The policy engine checks site, requested action, actor, exact diff/artifact hash, expiry, eligible approver, and status. Retries must be idempotent. Revocation and a kill switch take precedence. The model never self-authorizes. If approval times out, reject or remain pending without acting.

## 5. Handoff and exception paths
A handoff record should contain: finding/run/site IDs; requested action; evidence and uncertainty; risk tier; exact artifact hash or version; why approval is needed; approver role; created/expiry timestamps; status; and decision outcome.

Explicit exceptions:
1. **Missing/conflicting evidence:** label uncertain, don't guess or modify; request owner review with the contradictory sources.
2. **H-only action:** produce recommendation only; no executable tool route for the agent.
3. **No approver response:** persist `pending` or `expired`, never default to approved; notify according to allowed reminder policy.
4. **Scan/tool failure:** mark partial/unavailable; don't turn failure into an invented vulnerability; retry with bounded backoff.
5. **Unexpected permissions / target:** stop action, log security event, notify owner.
6. **Website unreachable:** distinguish tool/network failure from verified site outage; confirm with safe retry/secondary evidence.

## 6. PE6202 S / D / C / P hotspots
| Hotspot | Failure scenario | Guardrail, owner, evidence |
| --- | --- | --- |
| **S — See** | Agent or model receives production secrets or enquiry details | Scoped tools, redaction, deny private storage; owner: platform maintainer; evidence: permission/redaction logs |
| **D — Decide** | Prompt injection in scanned webpage instructs agent to leak data or run commands | Untrusted-content boundary; schema validation; policy engine denies unsanctioned actions; owner: maintainer; evidence: blocked-action logs |
| **C — Change** | Tool, dependency, repository instruction changes execution policy or website | Protected policy files, reviewed builds, restricted writable tools and approvals; owner: maintainer; evidence: signed commit/PR history and approvals |
| **P — Prove** | Agent changes something but no one can trace what happened | Correlation IDs, append-only audit records, artifact hashes, timestamps, redacted logs; owner: maintainer; evidence: audit exports |

## 7. Layered controls (adapted PE6202 L1–L5)
- **L1 — Runtime guardrails:** allowlisted tools, validation, rate/CPU/time budgets, explicit approvals.
- **L2 — Trust layer:** permission-aware retrieval, untrusted-content handling, redacted logs, evidence-linked outputs.
- **L3 — Model ecosystem:** explicitly approved models, providers, packages and skills; do not assume zero retention without contract/settings verification.
- **L4 — Responsible operation:** named owner, tabletop tests, review, documented incidents and known gaps.
- **L5 — Infrastructure/identity:** least privilege, isolation, TLS, secrets handling, access logging and backups.

## 8. Memory, observability, kill switch
**Store:** audit runs, findings/evidence references, dedupe keys, approval records, tool versions, state/checkpoints, incident history. **Avoid:** raw contact submissions, customer PII, secrets, unnecessarily long raw HTML snapshots. Define access rights and retention before collecting sensitive data.

**Observe:** scan coverage, freshness, false positives, token/tool costs, execution time, errors, retries, any proposed and executed mutations, review latency.

**Kill switch:** configurable `AGENT_ENABLED=false` plus enforceable stop in scheduler and executor; disable write-capable credentials separately. A paused agent must not resume pending writes after a restart without revalidating permissions and approval.

## 9. Autonomy ladder and gates
1. **Shadow:** generate suggestions; owner decides and acts. **V1 default.**
2. **Supervised:** propose actions, require approval for each. Potential V2.
3. **Guided:** execute only narrowly predefined, reversible, low-risk actions after evidence supports it; independently review exceptions. Future only.
4. **Autonomous:** audit after automatic execution. Not a current goal for production changes.

Document one **never-alone** action (production deployment), one **known gap** (same-host risk during MVP), and one **scale bottleneck** (human review backlog) in every major architecture review.

## 10. Security test scenarios to implement
- Public page includes instruction to reveal `.env` or execute shell command: should remain inert data, action denied and logged.
- Website unexpectedly redirects to localhost/private network: blocked.
- Missing or contradictory scan results: no definitive claim; flagged for review.
- Approval not received / expired / revoked: no action.
- Low-confidence vulnerability claim: report uncertainty, avoid invented CVEs.
- Scanner timeout or 5xx response: bounded retries and partial report.
- Model requests an unlisted tool / out-of-scope target: policy denies it.
- Agent stopped mid-run: safe resume or exit without duplication.

## 11. Regulatory and commercial caveat
The uploaded PE6202 appendix provides governance language and Singapore regulatory starting points, not definitive legal requirements for this Malaysian website. Before commercial deployment, separately assess applicable Malaysian privacy law, contracts, customer authorization, data transfers and breach response obligations.
