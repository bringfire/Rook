"""
GH Binary Parser

Parses compressed .gh files to extract:
1. Component instances (type GUID + instance GUID + name)
2. Wiring patterns (source instance GUID -> target param)
"""

import zlib
import struct
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
import json
import re
from ..runtime_paths import resolve_readable_knowledge_path


@dataclass
class BinaryComponent:
    """A component found in binary .gh file."""
    type_guid: str  # Component type GUID
    instance_guid: str  # This instance's GUID
    name: str
    inputs: list = field(default_factory=list)  # List of (param_name, instance_guid, sources)
    outputs: list = field(default_factory=list)


def bytes_to_guid(b: bytes) -> str:
    """Convert 16 bytes to GUID string."""
    if len(b) != 16:
        return None
    # .NET GUID format: first 3 parts are little-endian
    a = struct.unpack('<I', b[0:4])[0]
    b1 = struct.unpack('<H', b[4:6])[0]
    c = struct.unpack('<H', b[6:8])[0]
    d = b[8:10].hex()
    e = b[10:16].hex()
    return f'{a:08x}-{b1:04x}-{c:04x}-{d}-{e}'


def guid_to_bytes(guid_str: str) -> bytes:
    """Convert GUID string to 16 bytes."""
    parts = guid_str.split('-')
    a = int(parts[0], 16).to_bytes(4, 'little')
    b = int(parts[1], 16).to_bytes(2, 'little')
    c = int(parts[2], 16).to_bytes(2, 'little')
    d = bytes.fromhex(parts[3])
    e = bytes.fromhex(parts[4])
    return a + b + c + d + e


class GHBinaryParser:
    """Parser for binary .gh files."""

    def __init__(self, known_guids: dict[str, str] = None):
        """
        Args:
            known_guids: dict of {type_guid: component_name}
        """
        self.known_guids = known_guids or {}
        self.known_guid_bytes = {guid_to_bytes(g): name for g, name in self.known_guids.items()}

    def decompress(self, path: Path) -> bytes:
        """Decompress a .gh file."""
        with open(path, 'rb') as f:
            data = f.read()
        return zlib.decompress(data, -zlib.MAX_WBITS)

    def parse_file(self, path: Path) -> dict:
        """Parse a .gh file and extract components and wiring."""
        data = self.decompress(path)

        components = self._find_components(data)
        wiring = self._find_wiring(data, components)

        return {
            'path': str(path),
            'components': components,
            'wiring': wiring
        }

    def _find_components(self, data: bytes) -> dict[str, dict]:
        """Find all component instances."""
        components = {}

        # Pattern: b'Object' ... b'GUID' ... [16 bytes] ... b'Name' ... [string]
        # Find all Object markers
        pos = 0
        while True:
            pos = data.find(b'\x06Object', pos)
            if pos == -1:
                break

            # Look for GUID marker nearby
            guid_pos = data.find(b'\x04GUID', pos, pos + 50)
            if guid_pos == -1:
                pos += 1
                continue

            # Skip past the GUID marker and type info to get the 16-byte GUID
            # Pattern: GUID + ff ff ff ff + 09 00 00 00 + [16 bytes]
            guid_data_pos = guid_pos + 4 + 4 + 4  # "GUID" + marker + type
            if guid_data_pos + 16 > len(data):
                pos += 1
                continue

            type_guid_bytes = data[guid_data_pos:guid_data_pos + 16]
            type_guid = bytes_to_guid(type_guid_bytes)

            # Find Name marker
            name_pos = data.find(b'\x04Name', guid_data_pos, guid_data_pos + 50)
            if name_pos == -1:
                pos += 1
                continue

            # Get name string (length-prefixed)
            name_data_pos = name_pos + 4 + 4 + 4  # "Name" + marker + type
            if name_data_pos + 1 > len(data):
                pos += 1
                continue

            name_len = data[name_data_pos]
            name = data[name_data_pos + 1:name_data_pos + 1 + name_len].decode('utf-8', errors='replace')

            # Find InstanceGuid in Container
            inst_pos = data.find(b'\x0cInstanceGuid', name_data_pos, name_data_pos + 200)
            if inst_pos != -1:
                inst_data_pos = inst_pos + 12 + 4 + 4
                if inst_data_pos + 16 <= len(data):
                    instance_guid = bytes_to_guid(data[inst_data_pos:inst_data_pos + 16])
                    components[instance_guid] = {
                        'type_guid': type_guid,
                        'name': name,
                        'known_name': self.known_guids.get(type_guid, name)
                    }

            pos = guid_data_pos + 16

        return components

    def _find_wiring(self, data: bytes, components: dict) -> list[dict]:
        """Find all wiring connections."""
        wiring = []

        # Pattern: param_input ... InstanceGuid ... [16 bytes] ... Source ... [16 bytes]
        pos = 0
        while True:
            pos = data.find(b'param_input', pos)
            if pos == -1:
                break

            # Find the param's InstanceGuid
            inst_pos = data.find(b'\x0cInstanceGuid', pos, pos + 100)
            if inst_pos == -1:
                pos += 1
                continue

            inst_data_pos = inst_pos + 12 + 4 + 4
            if inst_data_pos + 16 > len(data):
                pos += 1
                continue

            param_instance = bytes_to_guid(data[inst_data_pos:inst_data_pos + 16])

            # Find Name of param
            name_pos = data.find(b'\x04Name', inst_data_pos, inst_data_pos + 100)
            param_name = "unknown"
            if name_pos != -1:
                name_data_pos = name_pos + 4 + 4 + 4
                if name_data_pos + 1 < len(data):
                    name_len = data[name_data_pos]
                    if name_data_pos + 1 + name_len <= len(data):
                        param_name = data[name_data_pos + 1:name_data_pos + 1 + name_len].decode('utf-8', errors='replace')

            # Look for Source markers (may be multiple)
            search_start = pos
            search_end = min(pos + 500, len(data))
            source_pos = search_start

            while True:
                source_pos = data.find(b'\x06Source', source_pos, search_end)
                if source_pos == -1:
                    break

                # Check if this is "Source" followed by a GUID (not "SourceCount")
                if data[source_pos:source_pos + 11] == b'\x06Source\x00\x00\x00\x00':
                    # Next should be type marker (09) and then GUID
                    guid_start = source_pos + 11 + 4
                    if guid_start + 16 <= len(data):
                        source_guid = bytes_to_guid(data[guid_start:guid_start + 16])

                        # Find what component this param belongs to
                        # Look backwards for the parent component
                        parent_search = data.rfind(b'\x06Object', max(0, pos - 2000), pos)
                        parent_name = "unknown"
                        if parent_search != -1:
                            # Try to find the component name
                            pname_pos = data.find(b'\x04Name', parent_search, parent_search + 100)
                            if pname_pos != -1:
                                pname_data_pos = pname_pos + 4 + 4 + 4
                                if pname_data_pos + 1 < len(data):
                                    pname_len = data[pname_data_pos]
                                    parent_name = data[pname_data_pos + 1:pname_data_pos + 1 + pname_len].decode('utf-8', errors='replace')

                        # Resolve source component name
                        source_comp = components.get(source_guid, {})
                        source_name = source_comp.get('known_name', source_comp.get('name', 'unknown'))

                        wiring.append({
                            'source_guid': source_guid,
                            'source_name': source_name,
                            'target_name': parent_name,
                            'target_param': param_name
                        })

                source_pos += 1

            pos += 11

        return wiring


def extract_wiring_patterns(repo_path: Path, known_guids: dict) -> dict:
    """Extract wiring patterns from all .gh files in a repo."""
    parser = GHBinaryParser(known_guids)
    gh_files = list(repo_path.rglob('*.gh'))

    all_wiring = defaultdict(lambda: defaultdict(int))
    files_parsed = 0
    errors = 0

    for path in gh_files:
        try:
            result = parser.parse_file(path)
            for wire in result['wiring']:
                src = wire['source_name']
                tgt = wire['target_name']
                param = wire['target_param']
                if src != 'unknown' and tgt != 'unknown':
                    all_wiring[src][(tgt, param)] += 1
            files_parsed += 1
        except Exception as e:
            errors += 1

    # Convert to list format
    wiring_list = []
    for src, targets in all_wiring.items():
        for (tgt, param), count in targets.items():
            wiring_list.append({
                'source': src,
                'target': tgt,
                'param': param,
                'count': count
            })

    return {
        'files_parsed': files_parsed,
        'errors': errors,
        'wiring_patterns': sorted(wiring_list, key=lambda x: x['count'], reverse=True)
    }


if __name__ == '__main__':
    # Load known GUIDs
    training_path = resolve_readable_knowledge_path("gh", "training_patterns.json")
    with open(training_path) as f:
        training = json.load(f)

    known_guids = {c['guid']: c['name'] for c in training['top_components']}

    # Parse generative-design repo
    repo_path = Path(__file__).parent.parent.parent.parent.parent / 'references' / 'generative-design'

    print(f'Parsing .gh files from {repo_path}...')
    result = extract_wiring_patterns(repo_path, known_guids)

    print(f"\nFiles parsed: {result['files_parsed']}")
    print(f"Errors: {result['errors']}")
    print(f"Wiring patterns found: {len(result['wiring_patterns'])}")

    print("\nTop 20 wiring patterns:")
    for w in result['wiring_patterns'][:20]:
        print(f"  {w['source']} -> {w['target']}.{w['param']}: {w['count']}x")
