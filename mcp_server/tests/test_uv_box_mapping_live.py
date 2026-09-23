"""Renderer-independent box mapping, checked against stored Rhino mappings.

Set ROOK_UV_TEST_PORT explicitly. Fixtures live in a private headless document;
the user's active document, selection, units and renderer are not changed.
Run validation tests first against an old build: its mapping command can block.
"""
import json
import math
import os
import uuid

import httpx
import pytest

pytestmark = pytest.mark.requires_rhino


@pytest.fixture(scope="module")
def client():
    port = os.environ.get("ROOK_UV_TEST_PORT")
    if not port:
        pytest.skip("Set ROOK_UV_TEST_PORT to an explicitly chosen test runtime")
    with httpx.Client(base_url=f"http://127.0.0.1:{int(port)}", timeout=15) as c:
        assert c.get("/ping").is_success
        yield c


def execute(client, code):
    result = client.post("/execute", json={"code": code}).json()
    assert result.get("success"), result
    data = result["data"]
    assert not data.get("stderr"), data
    return json.loads(data["output"].strip().splitlines()[-1])


@pytest.fixture
def scene(client):
    key = "rook_uv_test_" + uuid.uuid4().hex
    data = execute(client, f'''
import Rhino, System, math, json
import scriptcontext as sc
d = Rhino.RhinoDoc.CreateHeadless(None)
sc.sticky[{key!r}] = d
d.ModelUnitSystem = Rhino.UnitSystem.Meters
p = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(10,20,30), Rhino.Geometry.Vector3d.XAxis, Rhino.Geometry.Vector3d.YAxis)
p.Rotate(math.radians(33), Rhino.Geometry.Vector3d.ZAxis)
box = Rhino.Geometry.Box(p, Rhino.Geometry.Interval(-4,4), Rhino.Geometry.Interval(-1,1), Rhino.Geometry.Interval(-0.5,0.5))
bid = d.Objects.AddBrep(box.ToBrep())
mid = d.Objects.AddMesh(Rhino.Geometry.Mesh.CreateFromBox(box, 1, 1, 1))
keep = Rhino.Render.TextureMapping.CreateBoxMapping(Rhino.Geometry.Plane.WorldXY, Rhino.Geometry.Interval(0,7), Rhino.Geometry.Interval(0,7), Rhino.Geometry.Interval(0,7), True)
for oid in [bid,mid]: d.Objects.FindId(oid).SetTextureMapping(7,keep)
print(json.dumps({{"serial":d.RuntimeSerialNumber,"ids":[str(bid),str(mid)]}}))
''')
    data["key"] = key
    yield data
    execute(client, f"import scriptcontext as sc, json\nsc.sticky.pop({key!r}).Dispose()\nprint(json.dumps(True))")


def post(client, scene, **fields):
    body = {"ids": scene["ids"], "documentSerialNumber": scene["serial"], **fields}
    return client.post("/material/uv-box", json=body).json()


def mapping(client, scene, index=0, channel=1):
    return execute(client, f'''
import Rhino, System, json
import scriptcontext as sc
d = sc.sticky[{scene['key']!r}]
o = d.Objects.FindId(System.Guid({scene['ids'][index]!r}))
m = o.GetTextureMapping({channel})
if m is None:
 print(json.dumps(None))
else:
 ok,p,x,y,z = m.TryGetMappingBox()
 print(json.dumps({{"ok":ok,"type":str(m.MappingType),"origin":[p.OriginX,p.OriginY,p.OriginZ],"x":[p.XAxis.X,p.XAxis.Y,p.XAxis.Z],"y":[p.YAxis.X,p.YAxis.Y,p.YAxis.Z],"size":[x.Length,y.Length,z.Length],"id":str(m.Id)}}))
''')


@pytest.mark.parametrize("fields", [
    {"channel": 0}, {"channel": -1}, {"channel": 1.5},
    {"channel": 4294967297}, {"channel": 18446744073709551615},
    {"scale": "large"}, {"scale": 0}, {"scale": -2},
    {"repeat": [1, 0, 1]}, {"repeat": [1, 2]},
    {"frame": {"x_axis": [1, 0, 0], "y_axis": [1, 0, 0]}},
    {"frame": {"x_axis": [0, 0, 0], "y_axis": [0, 1, 0]}},
])
def test_rejects_bad_request_before_mapping(client, scene, fields):
    # No existing objects are passed on purpose: validation must precede iteration
    # and this regression safely fails on the old interactive implementation.
    result = post(client, scene, ids=[str(uuid.uuid4())], **fields)
    assert result.get("success") is False, result
    assert mapping(client, scene) is None


@pytest.mark.parametrize("index", [0, 1], ids=["brep", "mesh"])
def test_fixed_repeat_follows_rotated_geometry_and_preserves_channels(client, scene, index):
    before = mapping(client, scene, index, 7)
    result = post(client, scene, ids=[scene["ids"][index]], scale=2.5, channel=3)
    assert result.get("success"), result
    assert result["data"]["mapped_count"] == 1
    actual = mapping(client, scene, index, 3)
    assert actual["type"] == "BoxMapping"
    assert actual["size"] == pytest.approx([2.5, 2.5, 2.5])
    assert actual["origin"] == pytest.approx([10, 20, 30])
    assert actual["x"] == pytest.approx([math.cos(math.radians(33)), math.sin(math.radians(33)), 0])
    assert mapping(client, scene, index, 7) == before
    assert mapping(client, scene, index, 1) is None
    dims = result["data"]["objects"][0]["dimensions"]
    assert dims == pytest.approx([8, 2, 1])


def test_explicit_frame_and_rectangular_repeat(client, scene):
    result = post(client, scene, repeat=[2, 3, 4], frame={
        "origin": [100, 200, 300], "x_axis": [0, 0, 1], "y_axis": [1, 0, 0]})
    assert result.get("success"), result
    assert result["data"]["mapped_count"] == 2
    # Dimensions/coverage must be measured in the requested mapping frame.
    c, s = math.cos(math.radians(33)), math.sin(math.radians(33))
    for obj in result["data"]["objects"]:
        assert obj["dimensions"] == pytest.approx([1, 8*c + 2*s, 8*s + 2*c])
    for i in [0, 1]:
        actual = mapping(client, scene, i)
        assert actual["size"] == pytest.approx([2, 3, 4])
        assert actual["origin"] == pytest.approx([100, 200, 300])
        assert actual["x"] == pytest.approx([0, 0, 1])
        assert actual["y"] == pytest.approx([1, 0, 0])


@pytest.mark.parametrize("units,want", [("Millimeters",1000), ("Meters",1), ("Feet",1/0.3048), ("Yards",1/0.9144)])
def test_default_repeat_is_one_meter(client, scene, units, want):
    execute(client, f"import Rhino,json,scriptcontext as sc\nsc.sticky[{scene['key']!r}].ModelUnitSystem = Rhino.UnitSystem.{units}\nprint(json.dumps(True))")
    result = post(client, scene)
    assert result.get("success"), result
    assert mapping(client, scene)["size"] == pytest.approx([want]*3)


def test_missing_object_is_not_counted_as_mapped(client, scene):
    missing = str(uuid.uuid4())
    result = post(client, scene, ids=[scene["ids"][0], missing], scale=2)
    assert result.get("success"), result
    assert result["data"]["mapped_count"] == 1
    assert result["data"]["objects"][1]["error"]


def test_reapplying_replaces_only_requested_channel(client, scene):
    keep = mapping(client, scene, channel=7)
    assert post(client, scene, scale=2)["data"]["mapped_count"] == 2
    assert post(client, scene, scale=4)["data"]["mapped_count"] == 2
    assert mapping(client, scene)["size"] == pytest.approx([4]*3)
    assert mapping(client, scene, channel=7) == keep


def test_unitless_document_requires_explicit_repeat(client, scene):
    execute(client, f"import Rhino,System,json,scriptcontext as sc\nsc.sticky[{scene['key']!r}].ModelUnitSystem = System.Enum.Parse(Rhino.UnitSystem, 'None')\nprint(json.dumps(True))")
    assert post(client, scene).get("success") is False
    assert post(client, scene, repeat=[2,3,4])["data"]["mapped_count"] == 2
    assert mapping(client, scene)["size"] == pytest.approx([2,3,4])


def test_planar_shared_assignment_preserves_box_channel(client, scene):
    keep = mapping(client, scene, channel=7)
    result = client.post("/material/uv-planar", json={
        "ids": scene["ids"], "documentSerialNumber": scene["serial"],
        "scale": 3, "channel": 2, "plane": "world_yz"}).json()
    assert result.get("success"), result
    assert result["data"]["mapped_count"] == 2
    actual = execute(client, f'''
import Rhino, System, json, scriptcontext as sc
d = sc.sticky[{scene['key']!r}]
m = d.Objects.FindId(System.Guid({scene['ids'][0]!r})).GetTextureMapping(2)
ok,p,x,y,z = m.TryGetMappingPlane()
print(json.dumps({{"ok":ok,"type":str(m.MappingType),"x":[p.XAxis.X,p.XAxis.Y,p.XAxis.Z],"size":[x.Length,y.Length,z.Length]}}))
''')
    assert actual["ok"]
    assert actual["type"] == "PlaneMapping"
    assert actual["x"] == pytest.approx([0,1,0])
    assert actual["size"] == pytest.approx([3]*3)
    assert mapping(client, scene, channel=7) == keep


def test_oversized_channel_cannot_replace_channel_one(client, scene):
    assert post(client, scene, scale=2)["data"]["mapped_count"] == 2
    keep = mapping(client, scene)
    result = post(client, scene, scale=9, channel=4294967297)
    assert result.get("success") is False
    assert mapping(client, scene) == keep
