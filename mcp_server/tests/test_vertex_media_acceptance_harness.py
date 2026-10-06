import importlib.util
from copy import deepcopy
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[2]/'scripts/vertex_media_acceptance.py'

def installed_fields():
    return {'installed_interpreter_verified':True,'oauth_consent_observed':True,
        'provenance':{'tested_commit':'a'*40,'installed_assembly_sha256':'b'*64,'patch_sha256':'c'*64,
            'image_model':'vertex_ai/gemini-3.1-flash-image','image_location':'global',
            'video_model':'vertex_ai/veo-3.1-fast-generate-001','video_location':'us-central1',
            'project_label':'pilot-project','account_label':'pilot-account'}}

def harness():
    spec=importlib.util.spec_from_file_location('vertex_acceptance',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def test_default_live_budget_and_missing_prerequisites_are_explicit():
    module=harness()
    report=module.live_acceptance(None)
    assert report['budget']=={'images':1,'videos':3}
    assert report['status']=='not_run'
    assert all(case['status']=='not_run' for case in report['cases'].values())

def test_mock_evidence_cannot_be_live_acceptance():
    report=harness().live_acceptance({'origin':'mock','cases':{'image':{'status':'passed'}}})
    assert report['status']=='not_run'

def test_live_input_and_output_paths_cannot_be_in_any_checkout(tmp_path):
    repo=tmp_path/'checkout'; repo.mkdir(); (repo/'.git').write_text('gitdir: elsewhere',encoding='utf-8')
    assert not harness().private_evidence_path(repo/'ignored'/'pilot.json')
    assert not harness().private_evidence_path(path.parent/'pilot.json')
    assert harness().private_evidence_path(tmp_path/'private'/'pilot.json')

def test_completion_before_intervention_is_inconclusive_and_no_fourth_video():
    evidence=complete_evidence()
    evidence['cases']['disconnect']['completed_before_intervention']=True
    report=harness().live_acceptance(evidence)
    assert report['cases']['disconnect']['status']=='inconclusive'
    evidence['submitted']['videos']=4
    assert harness().live_acceptance(evidence)['status']!='passed'

def test_old_boolean_only_evidence_cannot_establish_live_acceptance():
    evidence={**installed_fields(),'origin':'installed_google_live','installed_verified':True,'submitted':{'images':1,'videos':3},
        'cases':{'image':{'status':'passed','dimensions_verified':True},
            'completion_refresh':{'status':'passed','refresh_count':1,'same_binding':True,'playback_verified':True,'three_frames_decoded':True,'duration_verified':True},
            'disconnect':{'status':'passed','state':'interrupted','later_google_calls':0,'published':False,'reconnect_resumed':False},
            'restart':{'status':'passed','state':'interrupted','automatic_google_calls':0,'binding_preserved':True,'old_artifacts_accessible':True}}}
    assert harness().live_acceptance(evidence)['status']!='passed'
    evidence['cases']['completion_refresh']['refresh_count']=0
    assert harness().live_acceptance(evidence)['status']!='passed'

def complete_evidence():
    evidence={**installed_fields(),'origin':'installed_google_live','installed_verified':True,'submitted':{'images':1,'videos':3},'secret_scan':'passed'}
    proof=evidence['provenance']; proof.update(chirp_commit='d'*40,dirty_tree=False,installed_versions={'rook':'1.0.0','rook-mcp':'1.0.0','chirp':'1.0.0'})
    proof['project_label']='pilot-project-01'; proof['account_label']='pilot-account-01'
    evidence['gates']={name:{'status':'passed','tested_commit':proof['tested_commit'],'patch_sha256':proof['patch_sha256'],
        'assembly_sha256':proof['installed_assembly_sha256'],'evidence_sha256':'e'*64} for name in ('automated','memory')}
    def row(n,state):
        return {'status':'passed','started_utc':'2026-10-05T12:00:00Z','ended_utc':'2026-10-05T12:01:00Z','elapsed_seconds':60,
            'job_label':f'job-{n:02}','operation_label':f'operation-{n:02}','binding_label':'authorization-01',
            'request_counts':{'submit':1,'poll':2,'fetch':int(state=='complete'),'refresh':int(n==2),'remote_cancel':0},
            'ledger_transitions':['queued','submitting','polling',state]}
    image=row(1,'complete'); image.pop('operation_label'); image['request_counts'].update(poll=0,fetch=0)
    image['ledger_transitions']=['queued','submitting','complete']; image['execution_path']='image_job_manager'; image['request_label']='request-01'
    image['artifact']={'sha256':'f'*64,'byte_count':2000,'width':1024,'height':1024,'requested_width':1024,'requested_height':1024}
    completion=row(2,'complete')
    completion['artifact']={'sha256':'f'*64,'byte_count':3000,'width':1280,'height':720,'resolution':'720p','aspect_ratio':'16:9',
        'duration_seconds':4.1,'requested_duration_seconds':4,'decoded_frames':['first','middle','last'],'playback':'passed'}
    completion['refresh_evidence']={'mode':'forced_in_memory_lease','first_inflight_poll_utc':'2026-10-05T12:00:05Z',
        'lease_invalidated_utc':'2026-10-05T12:00:10Z','google_refresh_utc':'2026-10-05T12:00:15Z',
        'subsequent_poll_utc':'2026-10-05T12:00:20Z','completed_utc':'2026-10-05T12:00:50Z',
        'operation_before':'operation-02','operation_after':'operation-02','binding_before':'authorization-01','binding_after':'authorization-01',
        'actual_refresh_count':1,'additional_submissions':0}
    disconnect=row(3,'interrupted'); disconnect.update(first_inflight_poll_utc='2026-10-05T12:00:05Z',intervention_utc='2026-10-05T12:00:10Z',
        later_google_calls=0,published=False,reconnect_resumed=False,new_binding_calls_for_old_job=0)
    restart=row(4,'interrupted'); restart.update(first_inflight_poll_utc='2026-10-05T12:00:05Z',intervention_utc='2026-10-05T12:00:10Z',
        automatic_google_calls=0,binding_preserved=True,old_artifacts_accessible=True)
    evidence['cases']={'image':image,'completion_refresh':completion,'disconnect':disconnect,'restart':restart}
    return evidence

def test_closed_measured_evidence_retains_proof_and_matches_gates():
    evidence=complete_evidence(); report=harness().live_acceptance(evidence)
    assert report['status']=='passed'
    assert report['cases']['completion_refresh']['evidence']==evidence['cases']['completion_refresh']
    assert report['provenance']==evidence['provenance']

def test_normal_synchronous_panel_image_requires_no_invented_job_ledger():
    evidence=complete_evidence(); image=evidence['cases']['image']
    image.update(execution_path='synchronous_vision',job_label=None,ledger_transitions=None)
    assert harness().live_acceptance(evidence)['status']=='passed'
    image['ledger_transitions']=['queued','submitting','complete']
    assert harness().live_acceptance(evidence)['status']!='passed'

@pytest.mark.parametrize('mutation',[
    lambda e:e['cases']['completion_refresh']['refresh_evidence'].pop('lease_invalidated_utc'),
    lambda e:e['cases']['completion_refresh']['refresh_evidence'].update(mode='natural_expiry'),
    lambda e:e['cases']['completion_refresh']['refresh_evidence'].update(operation_after='operation-03'),
    lambda e:e['cases']['completion_refresh']['refresh_evidence'].update(additional_submissions=1),
    lambda e:e['cases']['completion_refresh']['refresh_evidence'].update(google_refresh_utc='2026-10-05T12:00:04Z'),
    lambda e:e['cases']['completion_refresh']['artifact'].update(duration_seconds=5),
    lambda e:e['cases']['completion_refresh']['artifact'].update(width=720),
    lambda e:e['cases']['image']['artifact'].pop('sha256'),
    lambda e:e['cases']['disconnect'].pop('first_inflight_poll_utc'),
    lambda e:e['gates']['automated'].update(status='failed'),
    lambda e:e['gates']['memory'].update(tested_commit='b'*40),
    lambda e:e['provenance'].update(account_label='someone@example.com'),
    lambda e:e['cases']['restart'].update(raw_response='secret-sentinel'),
    lambda e:e.update(secret_scan='failed'),
    lambda e:e['provenance'].update(tested_commit=123),
    lambda e:e['cases']['image'].update(artifact=None),
    lambda e:e['cases']['completion_refresh']['refresh_evidence'].update(actual_refresh_count=True),
])
def test_incomplete_or_inconsistent_proof_never_passes(mutation):
    evidence=deepcopy(complete_evidence()); mutation(evidence)
    report=harness().live_acceptance(evidence)
    assert report['status']!='passed'
    assert 'secret-sentinel' not in str(report)


def workforce_evidence():
    evidence = complete_evidence()
    evidence['workforce'] = {
        'contract_version': 2, 'adapter': 'msal_public_desktop', 'exchange': 'google_auth_sts_id_token',
        'principal_labels': ['employee-01', 'employee-02'],
        'project_labels': {'resource': 'project-01', 'workforce_user': 'project-02', 'quota': 'project-03'},
        'runtime_pins': {'python': '3.11.9', 'msal': '1.39.0', 'google-auth': '2.56.3', 'requests': '2.34.2', 'pyjwt': '2.15.0', 'cryptography': '50.0.1'},
        'runtime_manifest_sha256': '1'*64, 'authentication_review': 'passed',
        'prerequisites': {'administrator_setup': True, 'two_permitted_identities': True, 'spend_approved': True, 'installed_payload_verified': True},
        'lifecycle': {key: 'passed' for key in ('pending_active', 'failed_login_preserved', 'cancel_preserved', 'retirement', 'disconnect', 'identity_continuity', 'switch_old_binding_rejected', 'denied_identity_observed')},
        'sign_in_check': {'state': 'signed_in', 'check_scope': 'identity_exchange', 'entra_refresh_count': 1, 'sts_exchange_count': 1, 'model_calls': 0, 'image_access': 'unverified', 'video_access': 'unverified', 'billing': 'unverified', 'quota': 'unverified'},
        'poll_refresh': {'entra_refresh_count': 1, 'sts_exchange_count': 1, 'signed_token_altered': False, 'binding_preserved': True, 'additional_submissions': 0},
        'billing_attribution': {'resource': 'passed', 'workforce_user': 'passed', 'quota': 'passed'},
    }
    context = {'operation_label':'operation-02', 'binding_label':'authorization-01', 'principal_label':'employee-01',
        'account_label':'pilot-account-01', 'project_label':'pilot-project-01', 'resource_project_label':'project-01',
        'workforce_user_project_label':'project-02', 'quota_project_label':'project-03'}
    evidence['workforce']['generation_context'] = context
    evidence['workforce']['poll_refresh']['events'] = [
        {**context, 'kind':kind, 'utc':utc, 'source_evidence_sha256':'a'*64}
        for kind, utc in [('entra_refresh','2026-10-05T12:00:12Z'), ('sts_exchange','2026-10-05T12:00:15Z'), ('poll','2026-10-05T12:00:20Z')]]
    return evidence


@pytest.mark.parametrize('change', ['principal', 'projects', 'operation', 'binding', 'reorder', 'timestamp', 'entra-count', 'sts-count', 'missing-events', 'provenance'])
def test_workforce_refresh_requires_correlated_ordered_events(change):
    evidence = workforce_evidence(); proof = evidence['workforce']
    assert harness().live_acceptance(evidence)['status'] == 'passed'
    if change == 'principal': proof['poll_refresh']['events'][0]['principal_label'] = 'employee-02'
    if change == 'projects': proof['project_labels']['resource'] = 'project-04'
    if change == 'operation': proof['poll_refresh']['events'][1]['operation_label'] = 'operation-03'
    if change == 'binding': proof['poll_refresh']['events'][2]['binding_label'] = 'authorization-02'
    if change == 'reorder': proof['poll_refresh']['events'].reverse()
    if change == 'timestamp': proof['poll_refresh']['events'][0]['utc'] = '2026-10-05T12:00:25Z'
    if change == 'entra-count': proof['poll_refresh']['entra_refresh_count'] = 99
    if change == 'sts-count': proof['poll_refresh']['sts_exchange_count'] = 99
    if change == 'missing-events': proof['poll_refresh'].pop('events')
    if change == 'provenance': proof['generation_context']['account_label'] = 'pilot-account-02'
    assert harness().live_acceptance(evidence)['status'] == 'failed'


@pytest.mark.parametrize('installed', [False, True])
def test_workforce_budget_failure_precedes_missing_prerequisites(installed):
    evidence = workforce_evidence()
    evidence['workforce'].pop('generation_context')
    evidence['workforce']['poll_refresh'].pop('events')
    evidence['installed_verified'] = installed
    evidence['workforce']['prerequisites']['spend_approved'] = False
    evidence['submitted']['videos'] = 4
    report = harness().live_acceptance(evidence)
    assert report['status'] == 'failed'
    assert 'budget' in report['reason'].lower()


@pytest.mark.parametrize('entra_count', [1, 99])
def test_old_uncorrelated_workforce_counts_cannot_qualify(entra_count):
    evidence = workforce_evidence()
    evidence['workforce'].pop('generation_context')
    evidence['workforce']['poll_refresh'].pop('events')
    evidence['workforce']['poll_refresh']['entra_refresh_count'] = entra_count
    assert harness().live_acceptance(evidence)['status'] == 'failed'


def test_cli_budget_violation_exits_nonzero_without_spend_approval(tmp_path):
    import json
    import subprocess
    import sys
    evidence = workforce_evidence()
    evidence['workforce'].pop('generation_context'); evidence['workforce']['poll_refresh'].pop('events')
    evidence['workforce']['prerequisites']['spend_approved'] = False
    evidence['submitted']['videos'] = 4
    source = tmp_path/'synthetic-evidence.json'; output = tmp_path/'synthetic-result.json'
    source.write_text(json.dumps(evidence), encoding='utf-8')
    result = subprocess.run([sys.executable, str(path), '--mode', 'live', '--live-evidence', str(source), '--output', str(output)], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(output.read_text(encoding='utf-8'))['live']['status'] == 'failed'


def test_workforce_evidence_requires_real_refresh_and_project_attribution():
    evidence = workforce_evidence()
    assert harness().live_acceptance(evidence)['status'] == 'passed'
    for key in ('entra_refresh_count', 'sts_exchange_count'):
        changed = deepcopy(evidence); changed['workforce']['poll_refresh'][key] = 0
        assert harness().live_acceptance(changed)['status'] != 'passed'
    changed = deepcopy(evidence); changed['workforce']['billing_attribution']['quota'] = 'pending'
    report = harness().live_acceptance(changed)
    assert report['status'] == 'pending' and report['workforce']['billing_attribution']['quota'] == 'pending'


def test_inconclusive_intervention_is_not_pass():
    evidence = workforce_evidence()
    evidence['cases']['restart']['completed_before_intervention'] = True
    assert harness().live_acceptance(evidence)['status'] == 'inconclusive'


def test_workforce_optional_quota_is_explicitly_not_applicable():
    evidence = workforce_evidence()
    evidence['workforce']['project_labels']['quota'] = None
    evidence['workforce']['generation_context']['quota_project_label'] = None
    for event in evidence['workforce']['poll_refresh']['events']: event['quota_project_label'] = None
    evidence['workforce']['billing_attribution']['quota'] = 'not_applicable'
    assert harness().live_acceptance(evidence)['status'] == 'passed'
    evidence['workforce']['billing_attribution']['quota'] = 'passed'
    assert harness().live_acceptance(evidence)['status'] != 'passed'


@pytest.mark.parametrize('key', ['administrator_setup', 'two_permitted_identities', 'spend_approved', 'installed_payload_verified'])
def test_missing_live_prerequisites_cannot_be_pass(key):
    evidence = workforce_evidence(); evidence['workforce']['prerequisites'][key] = False
    assert harness().live_acceptance(evidence)['status'] == 'not_run'


@pytest.mark.parametrize('mutate', [
    lambda w: w['principal_labels'].append('private-sentinel@example.com'),
    lambda w: w['project_labels'].update(resource='actual-private-sentinel'),
    lambda w: w.update(assertion='private-sentinel'),
    lambda w: w['lifecycle'].update(raw_response='private-sentinel'),
    lambda w: w['sign_in_check'].update(image_access='verified'),
    lambda w: w['poll_refresh'].update(signed_token_altered=True),
    lambda w: w['runtime_pins'].update(msal='1.38.0'),
    lambda w: w.update(authentication_review='pending'),
])
def test_private_sentinels_rejected(mutate):
    evidence = workforce_evidence(); mutate(evidence['workforce'])
    report = harness().live_acceptance(evidence)
    assert report['status'] != 'passed' and 'private-sentinel' not in str(report)
