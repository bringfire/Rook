import importlib.util
from pathlib import Path

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

def test_completion_before_intervention_is_inconclusive_and_no_fourth_video():
    evidence={**installed_fields(),'origin':'installed_google_live','installed_verified':True,'submitted':{'images':1,'videos':3},
        'cases':{'disconnect':{'completed_before_intervention':True}}}
    report=harness().live_acceptance(evidence)
    assert report['cases']['disconnect']['status']=='inconclusive'
    evidence['submitted']['videos']=4
    assert harness().live_acceptance(evidence)['status']=='failed'

def test_live_pass_requires_refresh_playback_and_original_binding_evidence():
    evidence={**installed_fields(),'origin':'installed_google_live','installed_verified':True,'submitted':{'images':1,'videos':3},
        'cases':{'image':{'status':'passed','dimensions_verified':True},
            'completion_refresh':{'status':'passed','refresh_count':1,'same_binding':True,'playback_verified':True,'three_frames_decoded':True,'duration_verified':True},
            'disconnect':{'status':'passed','state':'interrupted','later_google_calls':0,'published':False,'reconnect_resumed':False},
            'restart':{'status':'passed','state':'interrupted','automatic_google_calls':0,'binding_preserved':True,'old_artifacts_accessible':True}}}
    assert harness().live_acceptance(evidence)['status']=='passed'
    evidence['cases']['completion_refresh']['refresh_count']=0
    assert harness().live_acceptance(evidence)['status']=='failed'
