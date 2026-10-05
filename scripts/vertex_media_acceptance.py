"""Source-only acceptance runner. Automated/memory evidence never substitutes for installed Google evidence.

Use --mode memory after a fresh build; --mode automated rebuilds and runs the scoped regressions.
--mode live validates a sanitized installed-session evidence file, or records not_run without one.
It performs no billed submissions and exposes no production token invalidation endpoint.
"""
from __future__ import annotations
import argparse
import hashlib
import math
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
BUDGET={'images':1,'videos':3}
LIVE_CASES=('image','completion_refresh','disconnect','restart')

def _closed(value, fields):
    return type(value) is dict and set(value) == set(fields.split())

def _sha(value, length=64):
    return type(value) is str and re.fullmatch('[a-f0-9]{'+str(length)+'}',value) is not None

def _number(value):
    return type(value) in (int,float) and math.isfinite(value)

def _utc(value):
    if type(value) is not str or len(value)>32: raise ValueError('invalid timestamp')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.utcoffset() is None or result.utcoffset().total_seconds()!=0: raise ValueError('UTC required')
    return result

def _label(value, prefix):
    return type(value) is str and re.fullmatch(prefix+r'-[0-9]{2}',value) is not None

def _common(row,name):
    start,end=_utc(row['started_utc']),_utc(row['ended_utc'])
    counts=row['request_counts']; states=row['ledger_transitions']
    sync_image=name=='image' and row['execution_path']=='synchronous_vision'
    ledger_ok=states is None if sync_image else (type(states) is list and 3<=len(states)<=64 and states[:2]==['queued','submitting']
        and all(s in ('queued','submitting','polling','downloading','saving','complete','interrupted') for s in states)
        and states[-1]==('complete' if name in ('image','completion_refresh') else 'interrupted')
        and (name=='image' or 'polling' in states))
    return (start<end and _number(row['elapsed_seconds']) and row['elapsed_seconds']>0
        and abs((end-start).total_seconds()-row['elapsed_seconds'])<=1
        and (row['job_label'] is None if sync_image else _label(row['job_label'],'job')) and _label(row['binding_label'],'authorization')
        and (name!='image' or row['execution_path'] in ('synchronous_vision','image_job_manager') and _label(row['request_label'],'request'))
        and (name=='image' or _label(row['operation_label'],'operation'))
        and _closed(counts,'submit poll fetch refresh remote_cancel')
        and all(type(v) is int and v>=0 for v in counts.values()) and counts['submit']==1 and counts['remote_cancel']==0
        and (name=='image' and counts['poll']==counts['fetch']==0 or name!='image' and counts['poll']>=1)
        and ledger_ok)

def _media(artifact,video):
    fields='sha256 byte_count width height '+('resolution aspect_ratio duration_seconds requested_duration_seconds decoded_frames playback' if video else 'requested_width requested_height')
    if not _closed(artifact,fields) or not _sha(artifact['sha256']): return False
    if any(type(artifact[k]) is not int or artifact[k]<=0 for k in ('byte_count','width','height')): return False
    if not video:
        return (artifact['byte_count']<=25*1024*1024 and all(type(artifact[k]) is int for k in ('requested_width','requested_height'))
            and (artifact['width'],artifact['height'])==(artifact['requested_width'],artifact['requested_height']))
    dimensions={'720p':(1280,720),'1080p':(1920,1080)}.get(artifact['resolution'])
    if artifact['aspect_ratio']=='9:16' and dimensions: dimensions=dimensions[::-1]
    return (artifact['aspect_ratio'] in ('16:9','9:16') and dimensions==(artifact['width'],artifact['height'])
        and artifact['byte_count']<=250*1024*1024 and type(artifact['requested_duration_seconds']) is int
        and artifact['requested_duration_seconds'] in (4,6,8) and (artifact['resolution']!='1080p' or artifact['requested_duration_seconds']==8)
        and _number(artifact['duration_seconds']) and abs(artifact['duration_seconds']-artifact['requested_duration_seconds'])<=.5
        and artifact['decoded_frames']==['first','middle','last'] and artifact['playback']=='passed')

def _refresh(row):
    proof=row['refresh_evidence']
    times='first_inflight_poll_utc lease_invalidated_utc google_refresh_utc subsequent_poll_utc completed_utc'
    if not _closed(proof,times+' mode operation_before operation_after binding_before binding_after actual_refresh_count additional_submissions'): return False
    moments=[_utc(row['started_utc']),*[_utc(proof[k]) for k in times.split()],_utc(row['ended_utc'])]
    return (all(a<b for a,b in zip(moments,moments[1:])) and proof['mode']=='forced_in_memory_lease'
        and proof['operation_before']==proof['operation_after']==row['operation_label']
        and proof['binding_before']==proof['binding_after']==row['binding_label']
        and type(proof['actual_refresh_count']) is int and proof['actual_refresh_count']>=1
        and row['request_counts']['refresh']==proof['actual_refresh_count'] and row['request_counts']['poll']>=2
        and row['request_counts']['fetch']==1 and type(proof['additional_submissions']) is int and proof['additional_submissions']==0)

def _case(row,name):
    common='status started_utc ended_utc elapsed_seconds job_label binding_label request_counts ledger_transitions'
    extra={'image':'artifact execution_path request_label','completion_refresh':'operation_label artifact refresh_evidence',
        'disconnect':'operation_label first_inflight_poll_utc intervention_utc later_google_calls published reconnect_resumed new_binding_calls_for_old_job',
        'restart':'operation_label first_inflight_poll_utc intervention_utc automatic_google_calls binding_preserved old_artifacts_accessible'}[name]
    if row.get('completed_before_intervention') is True:
        return 'inconclusive',None
    if not _closed(row,common+' '+extra) or row['status']!='passed' or not _common(row,name): return 'failed',None
    if name=='image': valid=_media(row['artifact'],False)
    elif name=='completion_refresh': valid=_media(row['artifact'],True) and _refresh(row)
    else:
        valid=(_utc(row['started_utc'])<_utc(row['first_inflight_poll_utc'])<_utc(row['intervention_utc'])<_utc(row['ended_utc'])
            and row['request_counts']['fetch']==0)
        if name=='disconnect':
            valid=valid and row['published'] is False and row['reconnect_resumed'] is False and all(type(row[k]) is int and row[k]==0 for k in ('later_google_calls','new_binding_calls_for_old_job'))
        else:
            valid=valid and type(row['automatic_google_calls']) is int and row['automatic_google_calls']==0 and row['binding_preserved'] is True and row['old_artifacts_accessible'] is True
    return ('passed',row) if valid else ('failed',None)

def _legacy_live_acceptance(evidence):
    report={'status':'not_run','budget':dict(BUDGET),'cases':{name:{'status':'not_run'} for name in LIVE_CASES},
        'reason':'Requires installed provenance, firm project, desktop OAuth consent and actual Google execution evidence.'}
    if type(evidence) is not dict or evidence.get('origin')!='installed_google_live' or evidence.get('installed_verified') is not True:
        return report
    submitted=evidence.get('submitted',{})
    if not _closed(submitted,'images videos') or any(type(submitted.get(key)) is not int or submitted[key] > limit or submitted[key] < 0 for key,limit in BUDGET.items()):
        report.update(status='failed',reason='Live submission budget was exceeded or is invalid. No automatic additional submission is authorized.')
        return report
    proof=evidence.get('provenance',{})
    if not (_closed(evidence,'origin installed_verified installed_interpreter_verified oauth_consent_observed provenance submitted gates secret_scan cases')
        and evidence.get('secret_scan')=='passed' and evidence.get('installed_interpreter_verified') is True and evidence.get('oauth_consent_observed') is True
        and _closed(proof,'tested_commit chirp_commit installed_assembly_sha256 patch_sha256 dirty_tree installed_versions image_model image_location video_model video_location project_label account_label')
        and _sha(proof.get('chirp_commit'),40) and type(proof.get('dirty_tree')) is bool
        and _sha(proof.get('tested_commit'),40)
        and _sha(proof.get('installed_assembly_sha256'))
        and _sha(proof.get('patch_sha256'))
        and proof.get('image_model')=='vertex_ai/gemini-3.1-flash-image' and proof.get('image_location')=='global'
        and proof.get('video_model')=='vertex_ai/veo-3.1-fast-generate-001' and proof.get('video_location')=='us-central1'
        and _label(proof.get('project_label'),'pilot-project') and _label(proof.get('account_label'),'pilot-account')
        and _closed(proof.get('installed_versions'),'rook rook-mcp chirp')
        and all(type(v) is str and re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}(?:-[a-z0-9.]+)?',v) for v in proof['installed_versions'].values())):
        return report
    gates=evidence.get('gates')
    if not _closed(gates,'automated memory') or any(not _closed(g,'status tested_commit patch_sha256 assembly_sha256 evidence_sha256')
        or g['status']!='passed' or g['tested_commit']!=proof['tested_commit'] or g['patch_sha256']!=proof['patch_sha256']
        or g['assembly_sha256']!=proof['installed_assembly_sha256'] or not _sha(g['evidence_sha256']) for g in gates.values()): return report
    if type(evidence['cases']) is not dict or set(evidence['cases'])!=set(LIVE_CASES): return report
    report.update(provenance=proof,gates=gates,secret_scan='passed')
    for name in LIVE_CASES:
        row=evidence.get('cases',{}).get(name,{})
        try: status,retained=_case(row,name)
        except (ValueError,TypeError,KeyError,AttributeError): status,retained='failed',None
        # Copy only closed acceptance fields, never provider bodies, account email, tokens or client material.
        report['cases'][name]={'status':status}
        if retained is not None: report['cases'][name]['evidence']=retained
    statuses=[row['status'] for row in report['cases'].values()]
    report['status']='passed' if all(status=='passed' for status in statuses) and submitted==BUDGET else 'inconclusive' if 'inconclusive' in statuses else 'failed'
    report['reason']='Validated closed operator evidence and gate linkage. This validator does not execute or independently observe Google jobs; private source evidence remains outside the repository.'
    return report


def _workforce_proof(proof, evidence):
    fields = 'contract_version adapter exchange principal_labels project_labels runtime_pins runtime_manifest_sha256 authentication_review prerequisites lifecycle sign_in_check poll_refresh billing_attribution'
    if not _closed(proof, fields) or type(proof['contract_version']) is not int or proof['contract_version'] != 2:
        return 'failed'
    if proof['adapter'] != 'msal_public_desktop' or proof['exchange'] != 'google_auth_sts_id_token' or proof['authentication_review'] != 'passed':
        return 'failed'
    labels = proof['principal_labels']
    if type(labels) is not list or len(labels) != 2 or len(set(str(v) for v in labels)) != 2 or not all(_label(v, 'employee') for v in labels):
        return 'failed'
    projects = proof['project_labels']
    if not _closed(projects, 'resource workforce_user quota') or not all(_label(projects[k], 'project') for k in ('resource', 'workforce_user')) or projects['quota'] is not None and not _label(projects['quota'], 'project'):
        return 'failed'
    pins = {'python': '3.11.9', 'msal': '1.39.0', 'google-auth': '2.56.3', 'requests': '2.34.2', 'pyjwt': '2.15.0', 'cryptography': '50.0.1'}
    if proof['runtime_pins'] != pins or not _sha(proof['runtime_manifest_sha256']):
        return 'failed'
    prerequisites = proof['prerequisites']
    if not _closed(prerequisites, 'administrator_setup two_permitted_identities spend_approved installed_payload_verified') or any(type(v) is not bool for v in prerequisites.values()):
        return 'failed'
    if not all(prerequisites.values()):
        return 'not_run'
    lifecycle = proof['lifecycle']
    if not _closed(lifecycle, 'pending_active failed_login_preserved cancel_preserved retirement disconnect identity_continuity switch_old_binding_rejected denied_identity_observed') or any(v != 'passed' for v in lifecycle.values()):
        return 'failed'
    check = proof['sign_in_check']
    if not _closed(check, 'state check_scope entra_refresh_count sts_exchange_count model_calls image_access video_access billing quota'):
        return 'failed'
    if check['state'] != 'signed_in' or check['check_scope'] != 'identity_exchange' or any(check[k] != 'unverified' for k in ('image_access', 'video_access', 'billing', 'quota')) or type(check['model_calls']) is not int or check['model_calls'] != 0:
        return 'failed'
    refresh = proof['poll_refresh']
    if not _closed(refresh, 'entra_refresh_count sts_exchange_count signed_token_altered binding_preserved additional_submissions') or refresh['signed_token_altered'] is not False or refresh['binding_preserved'] is not True or type(refresh['additional_submissions']) is not int or refresh['additional_submissions'] != 0:
        return 'failed'
    if any(type(row[k]) is not int or row[k] < 1 for row in (check, refresh) for k in ('entra_refresh_count', 'sts_exchange_count')):
        return 'failed'
    actual = evidence.get('cases', {}).get('completion_refresh', {}).get('refresh_evidence', {}).get('actual_refresh_count')
    if actual != refresh['sts_exchange_count']:
        return 'failed'
    billing = proof['billing_attribution']
    if not _closed(billing, 'resource workforce_user quota') or any(billing[k] not in ('passed', 'pending', 'failed') for k in ('resource', 'workforce_user')) or billing['quota'] not in (('not_applicable',) if projects['quota'] is None else ('passed', 'pending', 'failed')):
        return 'failed'
    return 'failed' if 'failed' in billing.values() else 'pending' if 'pending' in billing.values() else 'passed'


def live_acceptance(evidence):
    # Preserve the established personal Google result shape exactly. Workforce
    # evidence adds a closed versioned section; never retain an invalid section.
    if type(evidence) is not dict or 'workforce' not in evidence:
        return _legacy_live_acceptance(evidence)
    legacy = {k: v for k, v in evidence.items() if k != 'workforce'}
    report = _legacy_live_acceptance(legacy)
    try:
        status = _workforce_proof(evidence['workforce'], evidence)
    except (ValueError, TypeError, KeyError, AttributeError):
        status = 'failed'
    if status in ('failed', 'not_run'):
        # Drop all provenance/case proof when any workforce field is untrusted.
        report = _legacy_live_acceptance(None)
        report.update(status=status, reason='Workforce evidence is incomplete or invalid. No further submission is authorized.')
    elif report['status'] in ('passed', 'inconclusive'):
        report['workforce'] = evidence['workforce']
        if report['status'] == 'passed' and status == 'pending':
            report.update(status='pending', reason='Media and sign-in evidence validated; private project billing attribution remains pending.')
    return report

def provenance():
    def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
    assembly=ROOT/'src/Rook/bin/Debug/net48/Rook.rhp'
    untracked={}
    for name in git('ls-files','--others','--exclude-standard').decode().splitlines():
        if name.startswith(('src/','scripts/','mcp_server/')):
            path=ROOT/name
            if path.is_file(): untracked[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return {'tested_commit':git('rev-parse','HEAD').decode().strip(),
        'patch_sha256':hashlib.sha256(git('diff','HEAD','--binary')).hexdigest(),
        'untracked_source_sha256':untracked,
        'assembly_sha256':hashlib.sha256(assembly.read_bytes()).hexdigest() if assembly.exists() else None,
        'assembly_modified_utc':datetime.fromtimestamp(assembly.stat().st_mtime,timezone.utc).isoformat() if assembly.exists() else None,
        'image_model':'vertex_ai/gemini-3.1-flash-image','image_location':'global',
        'video_model':'vertex_ai/veo-3.1-fast-generate-001','video_location':'us-central1'}

def command(args,log,env=None):
    with log.open('wb') as output:
        result=subprocess.run(args,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=600)
    return {'status':'passed' if result.returncode==0 else 'failed','exit_code':result.returncode,'log':str(log)}

def memory(output_dir):
    output_dir=output_dir.resolve()
    reports=[]
    for mib,concurrency in ((1,1),(16,1),(64,1),(250,1),(250,2)):
        path=output_dir/f'memory-{mib}-{concurrency}.json'
        env=dict(os.environ,ROOK_VERTEX_MEMORY_OUTPUT=str(path),ROOK_VERTEX_MEMORY_MIB=str(mib),ROOK_VERTEX_MEMORY_CONCURRENT=str(concurrency))
        result=command(['dotnet','test','src/Rook.Tests/Rook.Tests.csproj','--configuration','Debug','--no-build',
            '--filter','FullyQualifiedName~StreamedInlineOutputProcessMemoryProbe','--verbosity','minimal'],output_dir/f'memory-{mib}-{concurrency}.log',env)
        if result['status']!='passed' or not path.exists(): return {'status':'failed','failed_probe':result,'cases':reports}
        reports.append(json.loads(path.read_text(encoding='utf-8')))
    host=subprocess.check_output(['powershell','-NoProfile','-Command',
        'Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json']).decode()
    return {'status':'passed','host_memory_kib':json.loads(host),'cases':reports,
        'limitations':'Synthetic bytes verify bounded parsing/publication, not MP4 playback. Process measurements are specific to this host.'}

def automated(output_dir):
    checks={}
    checks['fresh_build']=command(['dotnet','build','src/Rook/Rook.csproj','--configuration','Debug','--verbosity','minimal'],output_dir/'build.log')
    checks['managed']=command(['dotnet','test','src/Rook.Tests/Rook.Tests.csproj','--configuration','Debug','--filter',
        'FullyQualifiedName~Services.Vision|FullyQualifiedName~Handlers.Vision|FullyQualifiedName~VideoOpHandler|FullyQualifiedName~ImageJobOpHandler|FullyQualifiedName~RookSubsystemRootTests|FullyQualifiedName~UI.Chat|FullyQualifiedName~UI.Vision',
        '--verbosity','minimal'],output_dir/'managed.log')
    files=sorted((ROOT/'mcp_server/tests').glob('test_vertex*.py'))+[ROOT/'mcp_server/tests/test_vision_mcp_tools.py',ROOT/'mcp_server/tests/test_video_mcp_tools.py']
    checks['python']=command([sys.executable,'-m','pytest',*[str(path) for path in files],'-q'],output_dir/'python.log')
    return {'status':'passed' if all(row['status']=='passed' for row in checks.values()) else 'failed','checks':checks,
        'google_calls':0,'note':'Live cases are not_run. A missing external Prime producer fixture is reported as a managed regression prerequisite, not a passing check.'}

def private_evidence_path(path):
    resolved=path.resolve()
    return not any((parent/'.git').exists() for parent in (resolved,*resolved.parents))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('automated','memory','live'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--live-evidence',type=Path)
    args=parser.parse_args()
    if args.mode=='live' and (not private_evidence_path(args.output) or args.live_evidence and not private_evidence_path(args.live_evidence)):
        parser.error('Keep live pilot input and output outside every repository and Git worktree.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report={'automated':{'status':'not_run'},'memory':{'status':'not_run'},'live':live_acceptance(None)}
    if args.mode=='automated': report['automated']=automated(args.output.parent)
    elif args.mode=='memory': report['memory']=memory(args.output.parent)
    else: report['live']=live_acceptance(json.loads(args.live_evidence.read_text(encoding='utf-8')) if args.live_evidence else None)
    report['provenance']=provenance()
    report['recorded_utc']=datetime.now(timezone.utc).isoformat()
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:value['status'] for key,value in report.items() if key in {'automated','memory','live'}}))
    return 1 if report[args.mode]['status']=='failed' else 0

if __name__=='__main__': raise SystemExit(main())
