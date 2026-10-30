"""Prepare Linux reference images from an explicitly checked-out approved base.

This is a manual CI setup aid. Its output cannot authorize dependency publishing.
"""
import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from backend import Backend
from sandbox import Sandbox, CheckFailure, browser_summary, export
from font_fixtures import font_fixture

REFERENCE=re.compile(r'tests/e2e/[a-z0-9_-]+\.visual\.spec\.ts-snapshots/[a-z0-9_-]+-linux\.png')


def snapshot(root):
    result={}
    for path in root.rglob('*'):
        parts=path.relative_to(root).parts
        if any(p in {'node_modules','.next','test-results','playwright-report'} for p in parts):continue
        if path.is_symlink():raise ValueError('Unsafe source link')
        if path.is_file() and path.name not in {'next-env.d.ts','tsconfig.tsbuildinfo'}:
            result[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser=argparse.ArgumentParser()
    for option in ('repository','image','output'):parser.add_argument('--'+option,required=True)
    args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    report={'purpose':'visual-reference-preparation-only','status':'blocked','files':{},
            'publishing_authority':False,'requires_owner_review':True}
    backend=None
    try:
        with tempfile.TemporaryDirectory(prefix='guardian-visual-base-') as temporary:
            root=Path(temporary);source=root/'source';source.mkdir()
            report['baseline_sha']=export(args.repository,source)
            before=snapshot(source)
            fixtures=root/'fixtures';font_fixture(fixtures)
            sandbox=Sandbox(args.image,fixtures,Path(__file__).resolve().parent)
            sandbox.install(source,True)
            backend=Backend(sandbox,source)
            with backend:
                sandbox.backend=backend
                sandbox.run(source,['bash','/trusted/check.sh','build'],timeout=1200)
                if snapshot(source)!=before:raise ValueError('Build modified baseline source')
                sandbox.run(source,['node','/trusted/real-backend.cjs'],timeout=180)
                report['phase']='visual-reference-capture'
                try:
                    sandbox.run(source,['pnpm','exec','playwright','test','--config=/trusted/browser.config.ts',
                        '--update-snapshots=all','--retries=0','--workers=2',r'\.visual\.spec\.ts$'],timeout=1200)
                    report['capture']='complete'
                except CheckFailure as exc:
                    exc.stage='visual-reference-capture';exc.browser_summary=browser_summary(source)
                    report['capture_diagnostic']=exc.diagnostics();report['capture']='partial'
                after=snapshot(source)
                changed={p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)}
                if not 1<=len(changed)<=80 or any(p in before or not REFERENCE.fullmatch(p) for p in changed):
                    raise ValueError('Capture changed more than new Linux references')
                total=0
                for name in sorted(changed):
                    path=source/name
                    if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):raise ValueError('Unsafe reference path')
                    raw=path.read_bytes();total+=len(raw)
                    if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw)>10*1024*1024 or total>100*1024*1024:
                        raise ValueError('Reference budget/type')
                    target=output/'files'/name;target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(raw);report['files'][name]=hashlib.sha256(raw).hexdigest()
                report['phase']='contact-diagnostic'
                try:
                    sandbox.run(source,['pnpm','exec','playwright','test','--config=/trusted/browser.config.ts',
                        '--update-snapshots=none','--retries=0','--workers=1','--project=desktop-chromium',
                        '--grep','uses current contact details and one closing banner','whatsapp-widget.spec.ts'],timeout=180)
                    report['contact_diagnostic']='passed'
                except CheckFailure as exc:
                    exc.stage='contact-diagnostic';exc.browser_summary=browser_summary(source)
                    report['contact_diagnostic']=exc.diagnostics()
                report['phase']='complete'
            if report.get('capture')=='complete' and report.get('contact_diagnostic')=='passed':
                report['status']='captured-needs-owner-review'
    except Exception as exc:
        report['failure_kind']=type(exc).__name__
        if isinstance(exc,CheckFailure):report['diagnostics']=exc.diagnostics()
    finally:
        if backend is not None:report['backend']=backend.evidence
        (output/'capture.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('purpose','status','phase','baseline_sha','failure_kind')}))
    return 0 if report['status']=='captured-needs-owner-review' else 1


if __name__=='__main__':raise SystemExit(main())
