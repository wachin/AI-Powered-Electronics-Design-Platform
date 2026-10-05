"""
KiCad PCB to glTF Exporter for 3D Visualization.

Exports KiCad PCB designs to glTF 2.0 format for web-based 3D visualization.
"""

import json
import struct
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from src.core.circuit_ir import CircuitIR, Component, ComponentType


@dataclass
class GLTFNode:
    name: str
    mesh: Optional[int] = None
    translation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    children: List[int] = field(default_factory=list)


@dataclass
class GLTFMesh:
    primitives: List[Dict[str, Any]]


@dataclass
class GLTFMaterial:
    name: str
    pbrMetallicRoughness: Dict[str, Any] = field(default_factory=lambda: {
        "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
        "metallicFactor": 0.5,
        "roughnessFactor": 0.5
    })


@dataclass
class GLTFAccessor:
    bufferView: int
    componentType: int = 5126  # FLOAT
    count: int = 0
    type: str = "VEC3"
    min: Optional[List[float]] = None
    max: Optional[List[float]] = None


@dataclass
class GLTFBufferView:
    buffer: int
    byteOffset: int = 0
    byteLength: int = 0
    target: Optional[int] = None  # 34962 = ARRAY_BUFFER, 34963 = ELEMENT_ARRAY_BUFFER


class GLTFExporter:
    """Exports KiCad PCB to glTF 2.0 format."""

    def __init__(self, circuit: CircuitIR):
        self.circuit = circuit
        self.nodes: List[GLTFNode] = []
        self.meshes: List[GLTFMesh] = []
        self.materials: List[GLTFMaterial] = []
        self.accessors: List[GLTFAccessor] = []
        self.bufferViews: List[GLTFBufferView] = []
        self.buffers: List[Dict[str, Any]] = []
        self.bufferData: bytearray = bytearray()

        # Standard materials
        self._create_standard_materials()

    def _create_standard_materials(self):
        """Create standard PCB materials."""
        # FR4 board material (green)
        self.materials.append(GLTFMaterial(
            name="FR4",
            pbrMetallicRoughness={
                "baseColorFactor": [0.1, 0.35, 0.15, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.4
            }
        ))
        # Copper traces
        self.materials.append(GLTFMaterial(
            name="Copper",
            pbrMetallicRoughness={
                "baseColorFactor": [0.85, 0.55, 0.15, 1.0],
                "metallicFactor": 1.0,
                "roughnessFactor": 0.2
            }
        ))
        # Component bodies (black plastic)
        self.materials.append(GLTFMaterial(
            name="Plastic",
            pbrMetallicRoughness={
                "baseColorFactor": [0.05, 0.05, 0.05, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.3
            }
        ))
        # Silkscreen (white)
        self.materials.append(GLTFMaterial(
            name="Silkscreen",
            pbrMetallicRoughness={
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.8
            }
        ))
        # Solder mask (green)
        self.materials.append(GLTFMaterial(
            name="SolderMask",
            pbrMetallicRoughness={
                "baseColorFactor": [0.0, 0.4, 0.1, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.5
            }
        ))
        # Gold pads
        self.materials.append(GLTFMaterial(
            name="Gold",
            pbrMetallicRoughness={
                "baseColorFactor": [1.0, 0.85, 0.1, 1.0],
                "metallicFactor": 1.0,
                "roughnessFactor": 0.1
            }
        ))

    def _create_box_geometry(self, width: float, height: float, depth: float) -> Dict[str, Any]:
        """Create box mesh with positions, normals, UVs."""
        w, h, d = width / 2, height / 2, depth / 2
        
        # Vertices (8 corners)
        positions = [
            -w, -h, -d,  w, -h, -d,  w,  h, -d, -w,  h, -d,  # bottom
            -w, -h,  d,  w, -h,  d,  w,  h,  d, -w,  h,  d,   # top
        ]
        
        # Indices for 12 triangles (2 per face)
        indices = [
            0, 1, 2,  0, 2, 3,    # bottom
            4, 5, 6,  4, 6, 7,    # top
            0, 1, 5,  0, 5, 4,    # front
            2, 3, 7,  2, 7, 6,    # back
            0, 3, 7,  0, 7, 4,    # left
            1, 2, 6,  1, 6, 5     # right
        ]
        
        # Normals
        normals = [
            0, 0, -1,  0, 0, -1,  0, 0, -1,  0, 0, -1,   # bottom
            0, 0, 1,   0, 0, 1,   0, 0, 1,   0, 0, 1,    # top
            0, -1, 0,  0, -1, 0,  0, -1, 0,  0, -1, 0,   # front
            0, 1, 0,   0, 1, 0,   0, 1, 0,   0, 1, 0,    # back
            -1, 0, 0,  -1, 0, 0,  -1, 0, 0,  -1, 0, 0,   # left
            1, 0, 0,   1, 0, 0,   1, 0, 0,   1, 0, 0     # right
        ]
        
        # UVs
        uvs = [
            0, 0,  1, 0,  1, 1,  0, 1,   # bottom
            0, 0,  1, 0,  1, 1,  0, 1,   # top
            0, 0,  1, 0,  1, 1,  0, 1,   # front
            0, 0,  1, 0,  1, 1,  0, 1,   # back
            0, 0,  1, 0,  1, 1,  0, 1,   # left
            0, 0,  1, 0,  1, 1,  0, 1    # right
        ]
        
        return {
            "positions": positions,
            "indices": indices,
            "normals": normals,
            "uvs": uvs
        }

    def _add_buffer_data(self, data: List[float], component_type: int = 5126) -> tuple:
        """Add data to buffer and return (accessor_index, buffer_view_index)."""
        # Convert to bytes
        if component_type == 5126:  # FLOAT
            byte_data = struct.pack(f'<{len(data)}f', *data)
        elif component_type == 5123:  # UNSIGNED_SHORT
            byte_data = struct.pack(f'<{len(data)}H', *data)
        else:
            raise ValueError(f"Unsupported component type: {component_type}")
        
        byte_offset = len(self.bufferData)
        self.bufferData.extend(byte_data)
        byte_length = len(byte_data)
        
        # Create buffer view
        buffer_view_idx = len(self.bufferViews)
        self.bufferViews.append(GLTFBufferView(
            buffer=0,
            byteOffset=byte_offset,
            byteLength=byte_length,
            target=34962  # ARRAY_BUFFER
        ))
        
        # Create accessor
        accessor_idx = len(self.accessors)
        count = len(data) // 3 if component_type == 5126 else len(data)
        self.accessors.append(GLTFAccessor(
            bufferView=buffer_view_idx,
            componentType=component_type,
            count=count,
            type="VEC3" if component_type == 5126 else "SCALAR"
        ))
        
        return accessor_idx, buffer_view_idx

    def _add_index_buffer(self, indices: List[int]) -> int:
        """Add index buffer and return accessor index."""
        byte_data = struct.pack(f'<{len(indices)}H', *indices)
        byte_offset = len(self.bufferData)
        self.bufferData.extend(byte_data)
        byte_length = len(byte_data)
        
        # Buffer view for element array
        buffer_view_idx = len(self.bufferViews)
        self.bufferViews.append(GLTFBufferView(
            buffer=0,
            byteOffset=byte_offset,
            byteLength=byte_length,
            target=34963  # ELEMENT_ARRAY_BUFFER
        ))
        
        accessor_idx = len(self.accessors)
        self.accessors.append(GLTFAccessor(
            bufferView=buffer_view_idx,
            componentType=5123,  # UNSIGNED_SHORT
            count=len(indices),
            type="SCALAR"
        ))
        
        return accessor_idx

    def add_board(self, width: float, height: float, thickness: float = 1.6) -> int:
        """Add PCB board as a node."""
        geom = self._create_box_geometry(width, height, thickness)
        
        # Add buffers
        pos_acc, pos_bv = self._add_buffer_data(geom["positions"])
        norm_acc, norm_bv = self._add_buffer_data(geom["normals"])
        uv_acc, uv_bv = self._add_buffer_data(geom["uvs"])
        idx_acc = self._add_index_buffer(geom["indices"])
        
        # Create mesh primitive
        primitive = {
            "attributes": {
                "POSITION": pos_acc,
                "NORMAL": norm_acc,
                "TEXCOORD_0": uv_acc
            },
            "indices": idx_acc,
            "material": 0  # FR4 material
        }
        
        mesh_idx = len(self.meshes)
        self.meshes.append(GLTFMesh(primitives=[primitive]))
        
        # Create node
        node_idx = len(self.nodes)
        self.nodes.append(GLTFNode(
            name="PCB_Board",
            mesh=mesh_idx,
            translation=[0, 0, 0]
        ))
        
        return node_idx

    def add_component(self, component: Component, footprint_map: Dict[str, Dict]) -> int:
        """Add a component as a 3D model."""
        footprint = footprint_map.get(component.footprint, {})
        pkg = component.footprint.lower()
        
        # Determine dimensions from footprint
        if 'sot-223' in pkg:
            dims = (6.5, 7.0, 1.8)
        elif 'sot-23' in pkg:
            dims = (2.9, 2.8, 1.2)
        elif 'soic' in pkg or 'sop' in pkg:
            dims = (10.3, 7.5, 2.0)
        elif 'qfn' in pkg or 'lqfp' in pkg:
            dims = (12, 12, 1.5)
        elif 'to-220' in pkg:
            dims = (15, 10, 4.5)
        elif '0805' in pkg:
            dims = (2.0, 1.25, 0.6)
        elif '0603' in pkg:
            dims = (1.6, 0.8, 0.5)
        elif '0402' in pkg:
            dims = (1.0, 0.5, 0.4)
        else:
            dims = (5, 5, 2)
        
        geom = self._create_box_geometry(*dims)
        
        pos_acc, pos_bv = self._add_buffer_data(geom["positions"])
        norm_acc, norm_bv = self._add_buffer_data(geom["normals"])
        uv_acc, uv_bv = self._add_buffer_data(geom["uvs"])
        idx_acc = self._add_index_buffer(geom["indices"])
        
        primitive = {
            "attributes": {
                "POSITION": pos_acc,
                "NORMAL": norm_acc,
                "TEXCOORD_0": uv_acc
            },
            "indices": idx_acc,
            "material": 2  # Plastic material
        }
        
        mesh_idx = len(self.meshes)
        self.meshes.append(GLTFMesh(primitives=[primitive]))
        
        node_idx = len(self.nodes)
        pos = component.position or [0, 0]
        rot = component.rotation or 0
        
        # Convert rotation to quaternion
        import math
        q = [0, 0, math.sin(math.radians(rot) / 2), math.cos(math.radians(rot) / 2)]
        
        self.nodes.append(GLTFNode(
            name=component.ref,
            mesh=len(self.meshes) - 1,
            translation=[pos[0], pos[1], dims[2] / 2 + 0.8],
            rotation=q,
            scale=[1, 1, 1]
        ))
        
        return node_idx

    def export_gltf(self, output_path: Path, board_width: float = 100, board_height: float = 80) -> None:
        """Export complete glTF file."""
        import math
        
        # Add board
        self.add_board(board_width, board_height)
        
        # Add components
        footprint_map = {}
        for ref, comp in self.circuit.components.items():
            self.add_component(comp, {})
        
        # Build glTF JSON
        gltf = {
            "asset": {
                "version": "2.0",
                "generator": "AI Electronics Design Platform"
            },
            "scene": 0,
            "scenes": [{
                "nodes": list(range(len(self.nodes)))
            }],
            "nodes": [
                {
                    "name": node.name,
                    "mesh": node.mesh,
                    "translation": node.translation,
                    "rotation": node.rotation,
                    "scale": node.scale,
                    "children": node.children
                }
                for node in self.nodes
            ],
            "meshes": [
                {"primitives": mesh.primitives}
                for mesh in self.meshes
            ],
            "materials": [
                {
                    "name": mat.name,
                    "pbrMetallicRoughness": mat.pbrMetallicRoughness
                }
                for mat in self.materials
            ],
            "meshes": [
                {"primitives": mesh.primitives}
                for mesh in self.meshes
            ],
            "accessors": [
                {
                    "bufferView": acc.bufferView,
                    "componentType": acc.componentType,
                    "count": acc.count,
                    "type": acc.type,
                    "min": acc.min,
                    "max": acc.max
                }
                for acc in self.accessors
            ],
            "bufferViews": [
                {
                    "buffer": bv.buffer,
                    "byteOffset": bv.byteOffset,
                    "byteLength": bv.byteLength,
                    "target": bv.target
                }
                for bv in self.bufferViews
            ],
            "buffers": [{
                "byteLength": len(self.bufferData)
            }]
        }
        
        # Write JSON
        json_path = output_path.with_suffix('.gltf')
        with open(json_path, 'w') as f:
            json.dump(gltf, f, indent=2)
        
        # Write binary buffer
        bin_path = output_path.with_suffix('.bin')
        with open(bin_path, 'wb') as f:
            f.write(self.bufferData)
        
        print(f"Exported glTF: {json_path} + {bin_path}")


def export_pcb_gltf(circuit: CircuitIR, output_path: Path, board_width: float = 100, board_height: float = 80) -> None:
    """Convenience function to export circuit to glTF."""
    exporter = GLTFExporter(circuit)
    exporter.export_gltf(output_path, board_width, board_height)


# CLI
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python gltf_exporter.py <circuit_json> <output.gltf> [width] [height]")
        sys.exit(1)
    
    circuit_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    width = float(sys.argv[3]) if len(sys.argv) > 3 else 100
    height = float(sys.argv[4]) if len(sys.argv) > 4 else 80
    
    # Load circuit from JSON (assuming CircuitIR format)
    with open(circuit_path) as f:
        data = json.load(f)
    
    # Create CircuitIR from data (simplified)
    circuit = CircuitIR(name=data.get("name", "Board"))
    # ... populate circuit from data ...
    
    export_pcb_gltf(circuit, Path("output"), width, height)