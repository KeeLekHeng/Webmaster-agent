import json
from pathlib import Path
import pytest

from guardian.maintenance import repairs, runner
from guardian.maintenance.sandbox import CheckFailure, Sandbox as RealSandbox
from guardian.maintenance.policy import STAGES, digest
from guardian.maintenance.publisher import publish
from tests.maintenance.test_runner import Sandbox, registry
from tests.maintenance.test_publisher import API, fingerprint
from tests.maintenance.backend_helpers import backend_proof

PATH = 'src/components/public/Card.tsx'
SOURCE = b'import { Old } from "react";\nexport const Card = () => <Old />;\n'
UPDATES = [{'package':'react','before':'19.0.0','after':'19.0.1','section':'dependencies'}]


def plan(**overrides):
    return {'explanation':'Rename the removed display export while preserving its local alias.',
            'edits':[{'kind':'rename_import','path':PATH,'module':'react','old':'Old','new':'New','line':1,**overrides}]}


@pytest.fixture
def parser(monkeypatch):
    # Development fixture only. Production uses an independently installed pinned parser.
    location = Path(__file__).resolve().parents[2].parent/'sisweb/node_modules/typescript'
    if not location.exists():
        pytest.skip('Reviewed TypeScript parser is unavailable locally')
    monkeypatch.setenv('GUARDIAN_TYPESCRIPT_PATH',str(location))


def test_actual_ast_replay_preserves_alias_and_does_not_execute_source(parser):
    source = SOURCE + b'throw new Error("THIS MUST NEVER EXECUTE");\n'
    result = repairs.replay(plan(),{PATH:source},UPDATES)
    assert result[PATH] == source.replace(b'{ Old }',b'{ New as Old }')
    assert repairs.diff_budget({PATH:source},result)==2


@pytest.mark.parametrize('override',[
    {'path':'src/app/api/contact/route.ts'}, {'path':'src/components/public/AuthCard.tsx'},
    {'path':'src/components/public/../Card.tsx'}, {'module':'node:fs'},
    {'new':'dangerouslySetInnerHTML'}, {'new':'onClick'}, {'new':'__proto__'},
    {'new':'validate'}, {'new':'Old'}, {'new':'New;process.exit()'},
])
def test_unsafe_recipes_rejected(override):
    with pytest.raises(ValueError): repairs.validate(plan(**override),UPDATES)


def test_diagnostic_anchor_and_changed_dependency_required():
    with pytest.raises(ValueError): repairs.validate(plan(),[{'package':'example'}])
    with pytest.raises(ValueError): repairs.validate(plan(),UPDATES,[{'path':PATH,'line':2}])
    assert repairs.diagnostics(f'{PATH}(1,10): error TS2305: Export removed.\nsecret raw output'.encode()) == [
        {'path':PATH,'line':1,'column':10,'code':'TS2305','message':'Export removed.'}]
    assert repairs.diagnostics(b'src/app/api/a.ts(1,1): error TS2339: Missing.')==[]


def test_ast_rejects_ambiguous_and_shadowed_targets(parser):
    with pytest.raises(ValueError): repairs.replay(plan(line=2),{PATH:SOURCE},UPDATES)
    member = plan(kind='rename_member',binding='React',old='old',new='new',line=2)
    source = b'import * as React from "react";\nfunction f(React: any) { return React.old; }\n'
    with pytest.raises(ValueError): repairs.replay(member,{PATH:source},UPDATES)


def test_member_and_jsx_transform_only_imported_bindings(parser):
    member = b'import * as React from "react";\nexport const value = React.old;\n'
    result = repairs.replay(plan(kind='rename_member',binding='React',old='old',new='new',line=2),{PATH:member},UPDATES)
    assert result[PATH]==member.replace(b'React.old',b'React.new')
    jsx=b'import Link from "next/link";\nexport const Card = () => <Link old="text" />;\n'
    result=repairs.replay(plan(kind='rename_jsx_prop',binding='Link',module='next/link',old='old',new='new',line=2),
                         {PATH:jsx},[{'package':'next'}])
    assert result[PATH]==jsx.replace(b' old=',b' new=')
    with pytest.raises(ValueError):
        repairs.replay(plan(kind='rename_jsx_prop',binding='Local',module='next/link',old='old',new='new',line=2),
                       {PATH:jsx},[{'package':'next'}])


def test_failed_checks_cannot_modify_source_before_repair(tmp_path,monkeypatch):
    (tmp_path/'file.ts').write_text('original')
    sandbox=RealSandbox('sha256:'+'a'*64,tmp_path,tmp_path)
    def mutate(*args,**kwargs):
        (tmp_path/'file.ts').write_text('tampered')
        raise CheckFailure(b'compiler output')
    monkeypatch.setattr(sandbox,'run',mutate)
    with pytest.raises(ValueError,match='changed website source'): sandbox._checks(tmp_path,{})


def test_one_repair_restarts_full_checks_from_pristine_source(tmp_path,monkeypatch,parser):
    def export(repo,path):
        (path/'package.json').write_text(json.dumps({'packageManager':'pnpm@10.18.2','dependencies':{'react':'19.0.0'}}))
        (path/'pnpm-lock.yaml').write_text('old lock')
        (path/PATH).parent.mkdir(parents=True)
        (path/PATH).write_bytes(SOURCE)
        return 'a'*40
    monkeypatch.setattr(runner,'export',export)
    class RepairSandbox(Sandbox):
        attempts=0
        def checks(self,path,result):
            if path.name=='candidate':
                self.attempts+=1
                if self.attempts==1:
                    result['lint']='passed'
                    raise CheckFailure(f'{PATH}(1,10): error TS2305: Missing export.'.encode(),'typecheck')
                assert (path/PATH).read_bytes()==SOURCE.replace(b'{ Old }',b'{ New as Old }')
                assert result=={'install':'passed'}
            super().checks(path,result)
    report=runner.run('unused',tmp_path/'out','sha256:'+'a'*64,sandbox_factory=RepairSandbox,
        registry=lambda name:{'versions':{'19.0.1':{}},'time':{'19.0.1':'2020-01-01T00:00:00Z'}},
        fixtures=lambda p:{},repair_model='fake',planner=lambda *args:plan())
    assert report['status']=='verified',report
    assert report['candidate']=={s:'passed' for s in STAGES}
    assert report['repair_changed_lines']==2
    assert report['files'][PATH]['before_sha256']==digest(SOURCE)
    assert (tmp_path/'out'/PATH).exists()


def test_repair_model_receives_bounded_untrusted_source(tmp_path):
    path=tmp_path/PATH;path.parent.mkdir(parents=True);path.write_bytes(SOURCE)
    observed=[]
    problems=[{'path':PATH,'line':1}]
    value=repairs.propose(tmp_path,problems,UPDATES,'fake',investigator=lambda payload:observed.append(payload) or plan())
    assert value.edits[0].path==PATH
    assert observed[0]['untrusted_source'][PATH]==SOURCE.decode()
    path.write_text('sk-ant-synthetic')
    with pytest.raises(ValueError): repairs.propose(tmp_path,problems,UPDATES,'fake',investigator=lambda p:plan())


@pytest.mark.parametrize('tamper',[False,True])
def test_publisher_replays_recipe_before_any_write(tmp_path,parser,tamper):
    old=json.dumps({'packageManager':'pnpm@10.18.2','dependencies':{'react':'19.0.0'}}).encode()
    new=old.replace(b'19.0.0',b'19.0.1')
    originals={'package.json':old,'pnpm-lock.yaml':b'old',PATH:SOURCE}
    candidates={'package.json':new,'pnpm-lock.yaml':b'new',
                PATH:SOURCE.replace(b'{ Old }',b'{ New as Old }')+(b'console.log("extra");' if tamper else b'')}
    from guardian.maintenance.policy import changes
    report={'version':2,'backend':{k:backend_proof() for k in ('baseline','candidate')},'base_sha':'a'*40,'status':'verified','security_not_worsened':True,
            'advisories_before':[],'advisories_after':[],
            'baseline':{s:'passed' for s in STAGES},'candidate':{s:'passed' for s in STAGES},
            'updates':changes(old,new),'repair_plan':plan(),'repair_changed_lines':2,
            'files':{n:{'before_sha256':digest(originals[n]),'after_sha256':digest(data)} for n,data in candidates.items()}}
    for name,data in candidates.items():
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    (tmp_path/'verification.json').write_text(json.dumps(report))
    class NestedAPI(API):
        def originals(self,revision,paths=None): return {**self.original,'tree_sha':'b'*40}
    api=NestedAPI(originals)
    if tamper:
        with pytest.raises(ValueError,match='independently reproduced'):
            publish(tmp_path,fingerprint(tmp_path),api,enabled=True)
        assert not any(method=='POST' for method,_,_ in api.calls)
    else:
        assert publish(tmp_path,fingerprint(tmp_path),api,enabled=True)['status']=='published'
        tree=next(data for method,p,data in api.calls if p=='/git/trees')
        assert {e['path'] for e in tree['tree']}==set(candidates)


def test_only_one_repair_attempt_and_no_publishable_failed_artifacts(tmp_path,monkeypatch,parser):
    def export(repo,path):
        (path/'package.json').write_text(json.dumps({'packageManager':'pnpm@10.18.2','dependencies':{'react':'19.0.0'}}))
        (path/'pnpm-lock.yaml').write_text('old lock')
        (path/PATH).parent.mkdir(parents=True);(path/PATH).write_bytes(SOURCE)
        return 'a'*40
    monkeypatch.setattr(runner,'export',export)
    class AlwaysFails(Sandbox):
        def checks(self,path,result):
            if path.name=='candidate':
                raise CheckFailure(f'{PATH}(1,1): error TS2305: Missing export.'.encode(),'typecheck')
            super().checks(path,result)
    calls=[]
    report=runner.run('unused',tmp_path/'out','sha256:'+'a'*64,sandbox_factory=AlwaysFails,
        registry=lambda name:{'versions':{'19.0.1':{}},'time':{'19.0.1':'2020-01-01T00:00:00Z'}},fixtures=lambda p:{},
        repair_model='fake',planner=lambda *args:calls.append(True) or plan())
    assert len(calls)==1 and report['status']=='blocked'
    assert not (tmp_path/'out'/PATH).exists()
    assert not (tmp_path/'out'/'package.json').exists()
