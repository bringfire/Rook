"""
GH Training Data Extractor

Parses .ghx files from the GrasshopperHowtos repository to extract:
1. Component usage patterns (which components are used together)
2. Wiring patterns (how components connect)
3. Slider configurations (typical min/max/value ranges)
4. Recipe patterns (component sequences for common tasks)

This data enhances our gh_knowledge.py tiered knowledge store.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import json
from collections import defaultdict
from ..runtime_paths import resolve_writable_knowledge_path


@dataclass
class GHParameter:
    """A component parameter (input or output)."""
    name: str
    nickname: str
    instance_guid: str
    source_count: int = 0
    sources: list[str] = field(default_factory=list)


@dataclass
class GHSlider:
    """Slider configuration."""
    min_val: float
    max_val: float
    value: float
    digits: int


@dataclass
class GHComponent:
    """A Grasshopper component instance."""
    guid: str  # Component type GUID
    name: str
    nickname: str
    instance_guid: str
    inputs: list[GHParameter] = field(default_factory=list)
    outputs: list[GHParameter] = field(default_factory=list)
    slider: Optional[GHSlider] = None
    position: tuple[float, float] = (0, 0)
    hidden: bool = False


@dataclass
class GHDefinition:
    """A complete Grasshopper definition."""
    name: str
    path: Path
    components: list[GHComponent] = field(default_factory=list)

    def get_component_by_instance(self, instance_guid: str) -> Optional[GHComponent]:
        """Find component by instance GUID."""
        for comp in self.components:
            if comp.instance_guid == instance_guid:
                return comp
            for inp in comp.inputs:
                if inp.instance_guid == instance_guid:
                    return comp
            for out in comp.outputs:
                if out.instance_guid == instance_guid:
                    return comp
        return None


class GHXParser:
    """Parser for .ghx (Grasshopper XML) files."""

    def parse_file(self, path: Path) -> GHDefinition:
        """Parse a .ghx file into a GHDefinition."""
        tree = ET.parse(path)
        root = tree.getroot()

        definition = GHDefinition(name=path.stem, path=path)

        # Find DefinitionObjects chunk
        for chunk in root.iter('chunk'):
            if chunk.get('name') == 'DefinitionObjects':
                self._parse_objects(chunk, definition)
                break

        return definition

    def _parse_objects(self, objects_chunk: ET.Element, definition: GHDefinition):
        """Parse all objects in the definition."""
        for obj_chunk in objects_chunk.findall("chunks/chunk[@name='Object']"):
            component = self._parse_component(obj_chunk)
            if component:
                definition.components.append(component)

    def _parse_component(self, obj_chunk: ET.Element) -> Optional[GHComponent]:
        """Parse a single component."""
        items = obj_chunk.find('items')
        if items is None:
            return None

        guid = self._get_item_value(items, 'GUID')
        name = self._get_item_value(items, 'Name')

        if not guid or not name:
            return None

        # Parse container
        container = obj_chunk.find("chunks/chunk[@name='Container']")
        if container is None:
            return None

        container_items = container.find('items')
        instance_guid = self._get_item_value(container_items, 'InstanceGuid')
        nickname = self._get_item_value(container_items, 'NickName') or name
        hidden = self._get_item_value(container_items, 'Hidden') == 'true'

        component = GHComponent(
            guid=guid,
            name=name,
            nickname=nickname,
            instance_guid=instance_guid,
            hidden=hidden
        )

        # Parse attributes for position
        attrs = container.find("chunks/chunk[@name='Attributes']")
        if attrs is not None:
            bounds = attrs.find("items/item[@name='Bounds']")
            if bounds is not None:
                x = bounds.find('X')
                y = bounds.find('Y')
                if x is not None and y is not None:
                    component.position = (float(x.text), float(y.text))

        # Parse slider if present
        slider_chunk = container.find("chunks/chunk[@name='Slider']")
        if slider_chunk is not None:
            component.slider = self._parse_slider(slider_chunk)

        # Parse input and output parameters
        chunks_elem = container.find("chunks")
        if chunks_elem is not None:
            for param_chunk in chunks_elem.findall("chunk"):
                chunk_name = param_chunk.get('name', '')
                if chunk_name.startswith('param_input'):
                    param = self._parse_parameter(param_chunk)
                    if param and param.instance_guid not in [p.instance_guid for p in component.inputs]:
                        component.inputs.append(param)
                elif chunk_name.startswith('param_output'):
                    param = self._parse_parameter(param_chunk)
                    if param and param.instance_guid not in [p.instance_guid for p in component.outputs]:
                        component.outputs.append(param)

        return component

    def _parse_slider(self, slider_chunk: ET.Element) -> GHSlider:
        """Parse slider configuration."""
        items = slider_chunk.find('items')
        return GHSlider(
            min_val=float(self._get_item_value(items, 'Min') or 0),
            max_val=float(self._get_item_value(items, 'Max') or 100),
            value=float(self._get_item_value(items, 'Value') or 0),
            digits=int(self._get_item_value(items, 'Digits') or 0)
        )

    def _parse_parameter(self, param_chunk: ET.Element) -> Optional[GHParameter]:
        """Parse a parameter (input or output)."""
        items = param_chunk.find('items')
        if items is None:
            return None

        name = self._get_item_value(items, 'Name')
        nickname = self._get_item_value(items, 'NickName') or name
        instance_guid = self._get_item_value(items, 'InstanceGuid')
        source_count = int(self._get_item_value(items, 'SourceCount') or 0)

        if not name or not instance_guid:
            return None

        param = GHParameter(
            name=name,
            nickname=nickname,
            instance_guid=instance_guid,
            source_count=source_count
        )

        # Parse source GUIDs
        for i in range(source_count):
            source = self._get_item_value(items, f'Source', index=i)
            if source:
                param.sources.append(source)

        return param

    def _get_item_value(self, items: ET.Element, name: str, index: int = None) -> Optional[str]:
        """Get value of an item by name."""
        if items is None:
            return None

        if index is not None:
            item = items.find(f"item[@name='{name}'][@index='{index}']")
        else:
            item = items.find(f"item[@name='{name}']")

        if item is None:
            return None

        # Check for nested value (like ARGB)
        if len(item) > 0:
            return item[0].text if item[0].text else None
        return item.text


class TrainingDataExtractor:
    """Extract training patterns from parsed definitions."""

    def __init__(self):
        self.parser = GHXParser()
        self.component_usage = defaultdict(int)  # GUID -> count
        self.component_names = {}  # GUID -> name
        self.wiring_patterns = defaultdict(lambda: defaultdict(int))  # (src_name, dst_name) -> count
        self.slider_configs = defaultdict(list)  # component_context -> [SliderConfig]
        self.recipes = []  # List of (definition_name, component_sequence)

    def process_directory(self, root_dir: Path):
        """Process all .ghx files in directory tree."""
        ghx_files = list(root_dir.rglob("*.ghx"))
        print(f"Found {len(ghx_files)} .ghx files")

        for ghx_path in ghx_files:
            try:
                definition = self.parser.parse_file(ghx_path)
                self._extract_patterns(definition)
            except Exception as e:
                print(f"Error parsing {ghx_path}: {e}")

    def _extract_patterns(self, definition: GHDefinition):
        """Extract all patterns from a definition."""
        # Component usage
        for comp in definition.components:
            self.component_usage[comp.guid] += 1
            self.component_names[comp.guid] = comp.name

            # Slider configs
            if comp.slider:
                context = self._get_slider_context(comp, definition)
                self.slider_configs[context].append({
                    'min': comp.slider.min_val,
                    'max': comp.slider.max_val,
                    'value': comp.slider.value,
                    'digits': comp.slider.digits,
                    'definition': definition.name
                })

        # Wiring patterns
        for comp in definition.components:
            for inp in comp.inputs:
                for source_guid in inp.sources:
                    source_comp = definition.get_component_by_instance(source_guid)
                    if source_comp:
                        key = (source_comp.name, comp.name, inp.name)
                        self.wiring_patterns[source_comp.name][(comp.name, inp.name)] += 1

        # Recipe (ordered component sequence by x position)
        sorted_comps = sorted(definition.components, key=lambda c: c.position[0])
        recipe = [comp.name for comp in sorted_comps if not comp.hidden]
        self.recipes.append({
            'name': definition.name,
            'components': recipe,
            'component_count': len(recipe)
        })

    def _get_slider_context(self, slider_comp: GHComponent, definition: GHDefinition) -> str:
        """Determine what a slider is being used for based on connections."""
        for comp in definition.components:
            for inp in comp.inputs:
                if slider_comp.instance_guid in inp.sources:
                    return f"{comp.name}.{inp.name}"
        return "standalone"

    def generate_report(self) -> dict:
        """Generate training data report."""
        # Top components
        top_components = sorted(
            self.component_usage.items(),
            key=lambda x: x[1],
            reverse=True
        )[:50]

        # Common wiring patterns
        wiring_flat = []
        for src_name, targets in self.wiring_patterns.items():
            for (dst_name, param_name), count in targets.items():
                wiring_flat.append({
                    'source': src_name,
                    'target': dst_name,
                    'param': param_name,
                    'count': count
                })
        common_wiring = sorted(wiring_flat, key=lambda x: x['count'], reverse=True)[:100]

        # Slider statistics
        slider_stats = {}
        for context, configs in self.slider_configs.items():
            if len(configs) >= 2:  # Only include if we have multiple examples
                values = [c['value'] for c in configs]
                mins = [c['min'] for c in configs]
                maxs = [c['max'] for c in configs]
                slider_stats[context] = {
                    'count': len(configs),
                    'typical_min': sum(mins) / len(mins),
                    'typical_max': sum(maxs) / len(maxs),
                    'typical_value': sum(values) / len(values)
                }

        return {
            'summary': {
                'definitions_parsed': len(self.recipes),
                'unique_components': len(self.component_usage),
                'total_component_instances': sum(self.component_usage.values()),
                'wiring_patterns': len(wiring_flat)
            },
            'top_components': [
                {'guid': guid, 'name': self.component_names.get(guid, 'Unknown'), 'count': count}
                for guid, count in top_components
            ],
            'common_wiring': common_wiring,
            'slider_configurations': slider_stats,
            'recipes': sorted(self.recipes, key=lambda r: r['component_count'])[:20]
        }

    def save_report(self, output_path: Path):
        """Save training report to JSON."""
        report = self.generate_report()
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Saved training report to {output_path}")


def main():
    """Extract training data from GrasshopperHowtos."""
    repo_path = Path(__file__).parent.parent.parent.parent.parent / "references" / "GrasshopperHowtos"

    if not repo_path.exists():
        print(f"Repository not found at {repo_path}")
        return

    extractor = TrainingDataExtractor()
    extractor.process_directory(repo_path)

    output_path = resolve_writable_knowledge_path("gh", "training_patterns.json")
    extractor.save_report(output_path)

    # Print summary
    report = extractor.generate_report()
    print("\n=== Training Data Summary ===")
    print(f"Definitions parsed: {report['summary']['definitions_parsed']}")
    print(f"Unique components: {report['summary']['unique_components']}")
    print(f"Total component instances: {report['summary']['total_component_instances']}")
    print(f"\nTop 10 components:")
    for comp in report['top_components'][:10]:
        print(f"  {comp['name']}: {comp['count']} uses")


if __name__ == "__main__":
    main()
