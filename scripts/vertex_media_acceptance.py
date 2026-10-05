"""Source-only acceptance runner. Automated/memory evidence never substitutes for installed Google evidence.

Use --mode memory after a fresh build; --mode automated rebuilds and runs the scoped regressions.
--mode live validates a sanitized installed-session evidence file, or records not_run without one.
It performs no billed submissions and exposes no production token invalidation endpoint.
"""
from __future__ import annotations
import argparse
import hashlib
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

def live_acceptance(evidence):
    report={'status':'not_run','budget':dict(BUDGET),'cases':{name:{'status':'not_run'} for name in LIVE_CASES},
        'reason':'Requires installed provenance, firm project, desktop OAuth consent and actual Google execution evidence.'}
    if not evidence or evidence.get('origin')!='installed_google_live' or evidence.get('installed_verified') is not True:
        return report
    proof=evidence.get('provenance',{})
    if not (evidence.get('installed_interpreter_verified') is True and evidence.get('oauth_consent_observed') is True
        and re.fullmatch(r'[a-f0-9]{40}',proof.get('tested_commit',''))
        and re.fullmatch(r'[a-f0-9]{64}',proof.get('installed_assembly_sha256',''))
        and re.fullmatch(r'[a-f0-9]{64}',proof.get('patch_sha256',''))
        and proof.get('image_model')=='vertex_ai/gemini-3.1-flash-image' and proof.get('image_location')=='global'
        and proof.get('video_model')=='vertex_ai/veo-3.1-fast-generate-001' and proof.get('video_location')=='us-central1'
        and all(isinstance(proof.get(key),str) and 0<len(proof[key])<=64 and '@' not in proof[key] for key in ('project_label','account_label'))):
        return report
    submitted=evidence.get('submitted',{})
    if any(type(submitted.get(key)) is not int or submitted[key] > limit or submitted[key] < 0 for key,limit in BUDGET.items()):
        report.update(status='failed',reason='Live submission budget was exceeded or is invalid. No automatic additional submission is authorized.')
        return report
    checks={
        'image':lambda row:row.get('dimensions_verified') is True,
        'completion_refresh':lambda row:row.get('refresh_count',0)>=1 and all(row.get(key) is True for key in
            ('same_binding','playback_verified','three_frames_decoded','duration_verified')),
        'disconnect':lambda row:row.get('state')=='interrupted' and row.get('later_google_calls')==0
            and row.get('published') is False and row.get('reconnect_resumed') is False,
        'restart':lambda row:row.get('state')=='interrupted' and row.get('automatic_google_calls')==0
            and row.get('binding_preserved') is True and row.get('old_artifacts_accessible') is True,
    }
    for name in LIVE_CASES:
        row=evidence.get('cases',{}).get(name,{})
        status='inconclusive' if row.get('completed_before_intervention') is True else 'passed' if row.get('status')=='passed' and checks[name](row) else 'failed'
        # Copy only closed acceptance fields, never provider bodies, account email, tokens or client material.
        report['cases'][name]={'status':status}
    statuses=[row['status'] for row in report['cases'].values()]
    report['status']='passed' if all(status=='passed' for status in statuses) and submitted==BUDGET else 'inconclusive' if 'inconclusive' in statuses else 'failed'
    report['reason']='Evaluated supplied installed-session evidence; operator retains original sanitized logs and media provenance.'
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

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('automated','memory','live'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--live-evidence',type=Path)
    args=parser.parse_args()
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
