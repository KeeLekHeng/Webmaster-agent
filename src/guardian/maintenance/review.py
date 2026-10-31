"""Evidence-backed dependency report import; importing data never authorizes a PR."""
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from guardian.core.models import AnalysisResult, Evidence, Finding, Report
from guardian.maintenance.policy import PACKAGE, STAGES, declared
from guardian.workflows.investigation import ClaudeInvestigator, filter_investigation, project_evidence, investigation_failure_notice
from guardian.checks.audit import save_report
from guardian.core.network import enabled


def make_report(value, site_id='estateplanning'):
    now = datetime.now(timezone.utc).isoformat()
    observed = value.get('finished_at') or now
    parsed = datetime.fromisoformat(observed)
    if parsed.tzinfo is None:
        raise ValueError('CI observation time must include timezone')
    observed = parsed.isoformat()
    if value.get('version') not in (1,2) or not re.fullmatch(r'[a-f0-9]{40}', value.get('base_sha', '')):
        raise ValueError('Dependency verification identity missing')
    report = Report(run_id=uuid.uuid4().hex, site_id=site_id, started_at=now, finished_at=now,
                    tools={'dependency_review': '1', 'base_sha': value['base_sha']},
                    status='complete' if value.get('status') in {'verified', 'no-compatible-updates'} else 'partial')
    advisories = value.get('advisories_before', [])
    if len(advisories) > 500 or len(value.get('releases', [])) > 100:
        raise ValueError('Dependency review exceeds budget')
    if any(not isinstance(a, dict) or not PACKAGE.fullmatch(a.get('package', '')) or
           a.get('severity') not in {'info','low','moderate','high','critical'} for a in advisories):
        raise ValueError('Invalid advisory projection')
    if report.status != 'complete':
        report.evidence.append(Evidence(id='E001', timestamp=observed, source='repository:' + value['base_sha'],
            check='dependency_verification', outcome='unavailable', details={
                'required_stage_count': len(STAGES),
                'baseline_passed_count': sum(value.get('baseline', {}).get(s) == 'passed' for s in STAGES),
                'candidate_passed_count': sum(value.get('candidate', {}).get(s) == 'passed' for s in STAGES)}))
        report.findings.append(Finding(title='Dependency verification incomplete', severity='low', confidence='high',
            evidence_ids=['E001'], next_step='Inspect the first incomplete CI stage and rerun verification; no verified upgrade is established.'))
    for release in value.get('releases', []):
        name = release.get('package', '')
        if not PACKAGE.fullmatch(name):
            raise ValueError('Invalid package identity')
        declared(release['declared'])
        declared(release['eligible'])
        affected = [a for a in advisories if a.get('package') == name]
        if release['eligible'] == release['declared'] and not affected:
            continue
        severities = {a.get('severity') for a in affected}
        severity = 'high' if severities & {'critical', 'high'} else 'medium' if 'moderate' in severities else 'low' if affected else 'info'
        eid = f'E{len(report.evidence)+1:03d}'
        report.evidence.append(Evidence(id=eid, timestamp=observed, source='repository:' + value['base_sha'],
            check='dependencies', outcome='finding', details={
                'package': name, 'declared': release['declared'], 'eligible': release['eligible'],
                'dependency_type': release.get('section', 'unknown'),
                'advisories': [{k:a[k] for k in ('id','severity','ghsa','cves','cwes','affected_range','patched_range') if k in a} for a in affected],
                'advisory_count': len(affected), 'upgrade_verified': value.get('status') == 'verified',
                'compatible_update_available': release['eligible'] != release['declared']}))
        report.findings.append(Finding(title=('Known advisory reported: ' if affected else 'Compatible dependency update: ') + name,
            severity=severity, confidence='high', evidence_ids=[eid],
            next_step='Review the verified CI artifact and dependency diff; merge/deploy remain human decisions.' if value.get('status') == 'verified'
            else 'Review the advisory and blocked verification stages. No verified upgrade or production safety is established.'))
    # Transitive advisories must remain visible even when no direct upgrade fixes them.
    direct = {r['package'] for r in value.get('releases', [])}
    remaining = [a for a in advisories if a.get('package') not in direct]
    if remaining:
        eid = f'E{len(report.evidence)+1:03d}'
        report.evidence.append(Evidence(id=eid, timestamp=observed, source='repository:' + value['base_sha'], check='dependencies',
            outcome='finding', details={'advisory_count': len(remaining), 'transitive_review_required': True}))
        report.findings.append(Finding(title='Transitive dependency advisories require review',
            severity='high' if any(a['severity'] in {'high','critical'} for a in remaining) else 'medium', confidence='high',
            evidence_ids=[eid], next_step='Inspect affected dependency paths and patched ranges; no automatic override is authorized.'))
    report.limitations = ['Imported CI observations; importing JSON does not prove trusted execution or authorize publication.',
                         'A newer release is not itself a vulnerability. Advisory presence does not prove exploitability.',
                         'Declared versions are not proof of every resolved transitive version; see the pinned lockfile and audit.',
                         'Verification uses synthetic data and cached fonts; real-service coverage depends on the report version and backend evidence.',
                         'Production credentials, customer data and live provider delivery are outside this verification.']
    if report.status != 'complete':
        report.limitations.append('Verification is incomplete; do not treat unexecuted stages as passing.')
    if not value.get('finished_at'):
        report.limitations.append('CI collection timestamp unavailable; evidence timestamp denotes import time.')
    return report


def review(path, output, mode='none', model=None):
    enabled()
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Invalid dependency input')
    report = make_report(json.loads(path.read_bytes()))
    report.analysis = AnalysisResult(mode=mode, model=model)
    if mode == 'claude' and report.findings:
        payload, report.analysis.input_sha256 = project_evidence(report)
        try:
            client = ClaudeInvestigator(model)
            notes, rejected = filter_investigation(client(payload), payload)
            report.analysis.notes = notes
            report.analysis.usage = client.usage
            report.analysis.status = 'partial' if rejected and notes else 'rejected' if rejected else 'complete'
        except Exception as exc:
            report.analysis.status = 'unavailable'
            report.analysis.notices.append(investigation_failure_notice(exc))
    from guardian.reporting.summary import build_summary
    report.summary = build_summary(report)
    save_report(report, output)
    return report
