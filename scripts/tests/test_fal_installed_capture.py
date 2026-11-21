import importlib.util
from pathlib import Path
import pytest
spec = importlib.util.spec_from_file_location('fal_capture', Path(__file__).resolve().parents[1] / 'verification' / 'capture-fal-installed-mcp.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)

def test_actual_installed_discovery_and_status_tool_names_are_admitted():
    capture.admit([{'name':name,'arguments':{}} for name in ('rhino_image_models','rhino_video_models','rhino_image_status','rhino_video_status')])

@pytest.mark.parametrize('name',['rhino_generate_image','rhino_render_video','rhino_render','rhino_image_cancel'])
def test_no_cost_capture_rejects_paid_or_mutating_requests(name):
    with pytest.raises(ValueError): capture.admit([{'name':name,'arguments':{}}])

def test_report_preserves_exact_scalars_without_transport_sources():
    safe = capture.sanitize({'seed':9007199254740991,'strength':0.123456,'audio':False,'api_key':'secret','media':['https://v3.fal.media/private','data:image/png;base64,AAAA']})
    assert safe['seed']==9007199254740991 and safe['strength']==0.123456 and safe['audio'] is False
    assert 'api_key' not in safe
    assert all(set(item)=={'redacted_sha256'} for item in safe['media'])
