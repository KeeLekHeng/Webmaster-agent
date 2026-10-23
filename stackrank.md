# Website Guardian stack rank

Ranked remaining work. Update this file rather than creating another TODO or
milestone backlog. Rankings guide implementation order; they do not authorize
production changes, deletion, new credentials or additional scheduled jobs.

| Rank | Work | Status / completion evidence |
| --- | --- | --- |
| 1 | Trial verified dependency maintenance and richer AI review | SIS CI bootstrap merged. First real run passed install/lint/types/unit; build exposed incompatible cached font fixture. Isolated fix/retest in progress; Guardian Actions secrets and dependency trial pending. [Setup](docs/dependency-maintenance-setup.md) |
| 2 | Verify the first automatic weekly digest and missed-run behavior | Pending Monday execution; inspect task results, stage records and owner delivery |
| 3 | Deploy and trial manual retention | Preview/apply implemented and tested locally: 90-day eligible detail, 13 months numeric observations; protected references and offline checks. VPS upgrade pending; no automatic deletion enabled. [Operations](docs/retention.md) |
| 4 | Improve speed comparison coverage | Evaluate sample frequency; current weekly sampling is below the stronger regression threshold |
| 5 | Corroborate SEO actions with scoped page/query evidence | Keep confidence explicit and content changes human-reviewed |
| 6 | Move Guardian to a dedicated VPS | Temporary host cutover verified; owner confirmed bot reply. Keep reusable deployment sources and migrate fresh state later: [deployment guide](docs/vps.md) |
| 7 | Split the technical guide into a routed context library | Planned; structure and acceptance criteria below |
| 8 | Validate demand for a maintenance service | Before multi-tenancy, billing or dashboards |

## Documentation library refactor

The current [technical guide](docs/TECHNICAL_GUIDE.md) is the existing consolidated
reference. Splitting it is a follow-up task, not completed by adding this backlog.

Make `docs/TECHNICAL_GUIDE.md` a short router/index. It should explain which page
answers each question and link to focused topic pages, rather than repeating their
contents. Suggested topics are architecture, security, configuration, audits/SEO,
Google authorization, Telegram, scheduling, repository approvals, storage/retention,
and discovery/deployment. These are topic pages, not new milestone diaries.

### Rules for splitting and linking

1. Keep every new/refactored documentation Markdown page at **300 lines maximum**,
   including headings, tables and code blocks. The existing long guide is the
   migration target; do not claim that it already satisfies this limit.
2. Split by responsibility at section boundaries. If a topic still exceeds 300
   lines, recursively split it into narrower subtopics and make its parent a small
   router. Avoid arbitrary numbered chunks or a long chain of “next page” links.
3. Each router entry states its purpose and prerequisites. Every child page links
   back to its parent/index and directly to relevant related topics. Use relative
   paths and stable section anchors.
4. Give each fact/procedure one canonical home. Summaries should link to details,
   preserving safety controls, commands, caveats and historical provenance.
5. Agents start with `AGENTS.md`, then the technical router, and read only relevant
   topic pages plus linked prerequisites. Security/authorization prerequisites
   must be read before dependent operational work. Expand context as needed.
6. Whenever a page moves or splits, update inbound links, parent/child links,
   README, AGENTS and relevant OpenSpec references in the same change. Remove the
   superseded duplicate after its content and references have migrated.
7. Before completion, check page line counts, local link targets and section anchors,
   router coverage and orphaned pages. Keep OpenSpec artifacts in their required
   workflow structure; do not split schemas mechanically. Generated reports are
   runtime artifacts, not documentation-library pages.

Completion means all migrated technical pages are within the limit, discoverable
from the router, linked to their parent, free of stale links and duplicate source
material, and preserve the current operational/security instructions.

## Context entry points

- [Agent instructions](AGENTS.md)
- [Current technical guide / future router](docs/TECHNICAL_GUIDE.md)
- [OpenSpec change records](openspec/changes/)
