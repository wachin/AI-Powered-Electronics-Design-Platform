"""
Smart PCB Placement for AI-Powered Electronics Design Platform.

Implements intelligent component placement with:
- Collision avoidance using footprint bounding boxes
- Thermal-aware placement (separate heat-generating components)
- Signal integrity (keep related components close)
- Power domain grouping
- Mechanical constraints (board edge, mounting holes)
"""

import math
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set
from enum import Enum
from src.core.circuit_ir import CircuitIR, Component, ComponentType, Net


class PlacementStrategy(Enum):
    """Placement optimization strategies."""
    COMPACT = "compact"           # Minimize board area
    THERMAL = "thermal"           # Separate heat sources
    SIGNAL_INTEGRITY = "signal"   # Minimize critical trace lengths
    BALANCED = "balanced"         # Weighted combination


@dataclass
class BoundingBox:
    """Axis-aligned bounding box in mm."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    
    @property
    def width(self) -> float:
        return self.x_max - self.x_min
    
    @property
    def height(self) -> float:
        return self.y_max - self.y_min
    
    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x_min + self.x_max) / 2, (self.y_min + self.y_max) / 2)
    
    def contains(self, x: float, y: float) -> bool:
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max
    
    def intersects(self, other: 'BoundingBox', clearance: float = 0) -> bool:
        return not (self.x_max + clearance < other.x_min or
                   other.x_max + clearance < self.x_min or
                   self.y_max + clearance < other.y_min or
                   other.y_max + clearance < self.y_min)
    
    def expand(self, margin: float) -> 'BoundingBox':
        return BoundingBox(
            self.x_min - margin, self.y_min - margin,
            self.x_max + margin, self.y_max + margin
        )
    
    def translate(self, dx: float, dy: float) -> 'BoundingBox':
        return BoundingBox(
            self.x_min + dx, self.y_min + dy,
            self.x_max + dx, self.y_max + dy
        )


@dataclass
class FootprintGeometry:
    """Footprint physical geometry."""
    footprint_name: str
    bbox: BoundingBox
    pins: List[Tuple[str, Tuple[float, float]]]  # (pin_number, (x, y)) relative to center
    height: float = 1.6  # mm
    thermal_pad: bool = False
    power_dissipation: float = 0.0  # Watts
    
    @classmethod
    def from_footprint_name(cls, name: str) -> 'FootprintGeometry':
        """Create geometry from standard footprint name."""
        return cls._parse_footprint(name)
    
    @classmethod
    def _parse_footprint(cls, name: str) -> 'FootprintGeometry':
        """Parse standard footprint name to geometry."""
        name_lower = name.lower()
        
        # Chip components (SOT, SOIC, QFP, QFN, BGA)
        if 'sot-223' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-3.5, -3.5, 3.5, 3.5),
                pins=[('1', (-2.3, 0)), ('2', (0, 2.3)), ('3', (2.3, 0))],
                thermal_pad=True,
                power_dissipation=1.0
            )
        elif 'sot-23' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-1.5, -1.5, 1.5, 1.5),
                pins=[('1', (-1.3, 0)), ('2', (0, 1.3)), ('3', (1.3, 0))],
                power_dissipation=0.3
            )
        elif 'soic-8' in name_lower or 'sop-8' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-2.5, -3.5, 2.5, 3.5),
                pins=[(str(i), (-2.0, -2.5 + (i-1)*1.27)) for i in range(1, 5)] +
                     [(str(i), (2.0, 2.5 - (i-5)*1.27)) for i in range(5, 9)],
                power_dissipation=0.5
            )
        elif 'soic-14' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-2.5, -5.5, 2.5, 5.5),
                power_dissipation=0.5
            )
        elif 'soic-16' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-2.5, -6.5, 2.5, 6.5),
                power_dissipation=0.5
            )
        elif 'tssop' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-2.0, -4.0, 2.0, 4.0),
                power_dissipation=0.3
            )
        elif 'qfn' in name_lower or 'lqfp' in name_lower:
            # Extract pin count
            pin_count = 48
            if '48' in name:
                pin_count = 48
            elif '64' in name:
                pin_count = 64
            elif '100' in name:
                pin_count = 100
            
            size = math.sqrt(pin_count) * 0.5 + 3
            # Generate pins around the perimeter
            pins = []
            pins_per_side = pin_count // 4
            spacing = size / (pins_per_side + 1)
            for side in range(4):
                for i in range(pins_per_side):
                    pin_num = side * pins_per_side + i + 1
                    if side == 0:  # Bottom
                        pins.append((str(pin_num), (-size/2 + (i+1)*spacing, -size/2)))
                    elif side == 1:  # Right
                        pins.append((str(pin_num), (size/2, -size/2 + (i+1)*spacing)))
                    elif side == 2:  # Top
                        pins.append((str(pin_num), (size/2 - (i+1)*spacing, size/2)))
                    else:  # Left
                        pins.append((str(pin_num), (-size/2, size/2 - (i+1)*spacing)))
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-size/2, -size/2, size/2, size/2),
                pins=pins,
                thermal_pad=True,
                power_dissipation=1.5
            )
        elif 'to-220' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-5, -5, 5, 10),
                pins=[('1', (-2.5, 0)), ('2', (0, 0)), ('3', (2.5, 0))],
                thermal_pad=True,
                power_dissipation=5.0
            )
        elif '0805' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-1.0, -0.6, 1.0, 0.6),
                pins=[('1', (-1.0, 0)), ('2', (1.0, 0))],
                power_dissipation=0.125
            )
        elif '0603' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-0.8, -0.4, 0.8, 0.4),
                pins=[('1', (-0.8, 0)), ('2', (0.8, 0))],
                power_dissipation=0.1
            )
        elif '0402' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-0.5, -0.3, 0.5, 0.3),
                pins=[('1', (-0.5, 0)), ('2', (0.5, 0))],
                power_dissipation=0.0625
            )
        elif '1206' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-1.6, -0.8, 1.6, 0.8),
                pins=[('1', (-1.6, 0)), ('2', (1.6, 0))],
                power_dissipation=0.25
            )
        elif 'sma' in name_lower or 'do-214ac' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-2.0, -1.2, 2.0, 1.2),
                pins=[('1', (-2.0, 0)), ('2', (2.0, 0))],
                power_dissipation=1.0
            )
        elif 'sod-123' in name_lower:
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-1.5, -0.8, 1.5, 0.8),
                pins=[('1', (-1.5, 0)), ('2', (1.5, 0))],
                power_dissipation=0.3
            )
        elif 'dip' in name_lower:
            # Generic DIP
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-3.0, -10.0, 3.0, 10.0),
                power_dissipation=0.5
            )
        elif 'crystal' in name_lower or 'hc49' in name_lower or 'xtal' in name_lower:
            # Crystal oscillators
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-5.5, -2.5, 5.5, 2.5),
                pins=[('1', (-5.5, 0)), ('2', (5.5, 0))],
                power_dissipation=0.01
            )
        else:
            # Default generic
            return cls(
                footprint_name=name,
                bbox=BoundingBox(-2.0, -2.0, 2.0, 2.0),
                pins=[('1', (-2.0, 0)), ('2', (2.0, 0))],
                power_dissipation=0.5
            )


@dataclass
class PlacedComponent:
    """Component with assigned position."""
    ref: str
    component: Component
    geometry: FootprintGeometry
    position: Tuple[float, float]  # (x, y) in mm
    rotation: float = 0.0  # degrees
    layer: str = "F.Cu"
    
    @property
    def bbox(self) -> BoundingBox:
        cx, cy = self.position
        g = self.geometry.bbox
        return BoundingBox(
            cx + g.x_min, cy + g.y_min,
            cx + g.x_max, cy + g.y_max
        )
    
    def pin_position(self, pin_number: str) -> Optional[Tuple[float, float]]:
        """Get absolute pin position."""
        for pin_num, (px, py) in self.geometry.pins:
            if pin_num == pin_number:
                cx, cy = self.position
                # Apply rotation
                rad = math.radians(self.rotation)
                rx = px * math.cos(rad) - py * math.sin(rad)
                ry = px * math.sin(rad) + py * math.cos(rad)
                return (cx + rx, cy + ry)
        return None


class SmartPlacer:
    """Smart PCB component placer."""
    
    # Standard clearances (mm)
    MIN_CLEARANCE = 0.5      # Between any components
    THERMAL_CLEARANCE = 10.0 # Between high-power components
    EDGE_CLEARANCE = 5.0     # From board edge
    HIGH_VOLTAGE_CLEARANCE = 2.0
    
    def __init__(
        self,
        circuit: CircuitIR,
        board_width: float = 100.0,
        board_height: float = 80.0,
        strategy: PlacementStrategy = PlacementStrategy.BALANCED
    ):
        self.circuit = circuit
        self.board_width = board_width
        self.board_height = board_height
        self.strategy = strategy
        
        # Placement area (with edge clearance)
        self.placeable_area = BoundingBox(
            self.EDGE_CLEARANCE, self.EDGE_CLEARANCE,
            board_width - self.EDGE_CLEARANCE, board_height - self.EDGE_CLEARANCE
        )
        
        # Component geometries
        self.geometries: Dict[str, FootprintGeometry] = {}
        for ref, comp in circuit.components.items():
            self.geometries[ref] = FootprintGeometry.from_footprint_name(comp.footprint)
        
        # Placed components
        self.placed: Dict[str, PlacedComponent] = {}
        
        # Net connectivity for signal integrity
        self.net_components: Dict[str, List[str]] = {}
        for net_name, net in circuit.nets.items():
            self.net_components[net_name] = [p['ref'] for p in net.connected_pins]
        
        # Power domains
        self.power_nets: Set[str] = set()
        for net_name, net in circuit.nets.items():
            if net.is_power:
                self.power_nets.add(net_name)
    
    def place_all(self) -> Dict[str, PlacedComponent]:
        """Run complete placement algorithm."""
        
        # 1. Identify placement order (priority)
        placement_order = self._determine_placement_order()
        
        # 2. Place each component
        for ref in placement_order:
            if ref not in self.placed:
                self._place_component(ref)
        
        # 3. Post-process: resolve collisions, optimize
        self._resolve_collisions()
        self._optimize_placement()
        
        return self.placed
    
    def _determine_placement_order(self) -> List[str]:
        """Determine optimal placement order based on strategy."""
        components = list(self.circuit.components.keys())
        
        def priority(ref: str) -> Tuple:
            comp = self.circuit.components[ref]
            geo = self.geometries[ref]
            
            # High priority: connectors (fixed position), high-power, critical signals
            is_connector = comp.component_type == ComponentType.CONNECTOR
            is_high_power = geo.power_dissipation > 1.0
            is_thermal = geo.thermal_pad
            is_critical_net = any(
                net in self.power_nets 
                for pin in comp.pins 
                if pin.connected_net and pin.connected_net in self.power_nets
            )
            connectivity = len(comp.pins)
            
            # Priority tuple (lower = higher priority)
            return (
                0 if is_connector else 1,
                0 if is_high_power else 1,
                0 if is_thermal else 1,
                0 if is_critical_net else 1,
                -connectivity  # More pins = higher priority
            )
        
        return sorted(components, key=priority)
    
    def _place_component(self, ref: str) -> PlacedComponent:
        """Place a single component at optimal position."""
        comp = self.circuit.components[ref]
        geo = self.geometries[ref]
        
        # Find candidate positions
        candidates = self._generate_candidates(ref)
        
        # Score each candidate
        best_pos = None
        best_score = float('inf')
        
        for pos, rot in candidates:
            score = self._score_position(ref, pos, rot)
            if score < best_score:
                best_score = score
                best_pos = (pos, rot)
        
        if best_pos is None:
            # Fallback: place at first valid position
            for pos, rot in candidates:
                if self._is_valid_position(ref, pos, rot):
                    best_pos = (pos, rot)
                    break
        
        if best_pos is None:
            # Last resort: center of board
            best_pos = ((self.board_width / 2, self.board_height / 2), 0.0)
        
        pos, rot = best_pos
        placed = PlacedComponent(
            ref=ref,
            component=comp,
            geometry=geo,
            position=pos,
            rotation=rot
        )
        self.placed[ref] = placed
        return placed
    
    def _generate_candidates(self, ref: str) -> List[Tuple[Tuple[float, float], float]]:
        """Generate candidate positions for a component."""
        candidates = []
        geo = self.geometries[ref]
        
        # Grid step based on component size
        step = max(geo.bbox.width, geo.bbox.height) + self.MIN_CLEARANCE
        step = max(step, 5.0)  # Minimum 5mm grid
        
        # Search area - account for bbox extending from center
        # placeable_area is the valid region for bbox, so center must be placed such that
        # center + geo.bbox.x_min >= placeable_area.x_min
        # => center >= placeable_area.x_min - geo.bbox.x_min
        x_start = self.placeable_area.x_min - geo.bbox.x_min
        y_start = self.placeable_area.y_min - geo.bbox.y_min
        x_end = self.placeable_area.x_max - geo.bbox.x_max
        y_end = self.placeable_area.y_max - geo.bbox.y_max
        
        # Rotations to try
        rotations = [0, 90, 180, 270]
        
        # For large components, use coarser grid
        if geo.bbox.width > 20 or geo.bbox.height > 20:
            step = max(step, 10.0)
        
        # Limit candidate count for performance
        max_candidates = 200
        count = 0
        
        x = x_start
        while x <= x_end and count < max_candidates:
            y = y_start
            while y <= y_end and count < max_candidates:
                for rot in rotations:
                    candidates.append(((x, y), rot))
                    count += 1
                y += step
            x += step
        
        return candidates
    
    def _is_valid_position(self, ref: str, pos: Tuple[float, float], rot: float) -> bool:
        """Check if position is valid (no collisions, within bounds)."""
        geo = self.geometries[ref]
        test_bbox = geo.bbox.translate(pos[0], pos[1])
        
        # Check board bounds
        if not self._within_bounds(test_bbox):
            return False
        
        # Check collisions with already placed components
        for other_ref, other in self.placed.items():
            if self._check_collision(ref, test_bbox, other_ref, other.bbox):
                return False
        
        return True
    
    def _within_bounds(self, bbox: BoundingBox) -> bool:
        return (bbox.x_min >= self.placeable_area.x_min and
                bbox.y_min >= self.placeable_area.y_min and
                bbox.x_max <= self.placeable_area.x_max and
                bbox.y_max <= self.placeable_area.y_max)
    
    def _check_collision(self, ref1: str, bbox1: BoundingBox, ref2: str, bbox2: BoundingBox) -> bool:
        """Check if two components collide."""
        clearance = self.MIN_CLEARANCE
        
        # Extra clearance for thermal components
        geo1 = self.geometries[ref1]
        geo2 = self.geometries[ref2]
        if geo1.power_dissipation > 1.0 and geo2.power_dissipation > 1.0:
            clearance = max(clearance, self.THERMAL_CLEARANCE)
        
        return bbox1.intersects(bbox2, clearance)
    
    def _score_position(self, ref: str, pos: Tuple[float, float], rot: float) -> float:
        """Score a candidate position (lower is better)."""
        score = 0.0
        geo = self.geometries[ref]
        test_bbox = geo.bbox.translate(pos[0], pos[1])
        center = test_bbox.center
        
        # Strategy-based scoring
        if self.strategy == PlacementStrategy.COMPACT:
            score += self._score_compact(center)
        elif self.strategy == PlacementStrategy.THERMAL:
            score += self._score_thermal(ref, test_bbox)
        elif self.strategy == PlacementStrategy.SIGNAL_INTEGRITY:
            score += self._score_signal_integrity(ref, center)
        else:  # BALANCED
            score += 0.4 * self._score_compact(center)
            score += 0.3 * self._score_thermal(ref, test_bbox)
            score += 0.3 * self._score_signal_integrity(ref, center)
        
        # Penalty for collisions (should be caught by validation, but just in case)
        for other_ref, other in self.placed.items():
            if self._check_collision(ref, test_bbox, other_ref, other.bbox):
                score += 1000
        
        # Prefer positions near center for routing flexibility
        board_center = (self.board_width / 2, self.board_height / 2)
        dist_to_center = math.hypot(center[0] - board_center[0], center[1] - board_center[1])
        score += 0.1 * dist_to_center
        
        return score
    
    def _score_compact(self, center: Tuple[float, float]) -> float:
        """Score for compact placement (near center)."""
        board_center = (self.board_width / 2, self.board_height / 2)
        return math.hypot(center[0] - board_center[0], center[1] - board_center[1])
    
    def _score_thermal(self, ref: str, bbox: BoundingBox) -> float:
        """Score for thermal management (separate hot components)."""
        score = 0.0
        geo = self.geometries[ref]
        
        if geo.power_dissipation <= 0.5:
            return 0.0
        
        center = bbox.center
        
        # Penalize proximity to other high-power components
        for other_ref, other in self.placed.items():
            other_geo = self.geometries[other_ref]
            if other_geo.power_dissipation > 0.5:
                other_center = other.bbox.center
                dist = math.hypot(center[0] - other_center[0], center[1] - other_center[1])
                if dist < self.THERMAL_CLEARANCE:
                    score += (self.THERMAL_CLEARANCE - dist) * 10
        
        # Prefer edges/corners for heat dissipation
        edge_dist = min(
            center[0] - self.placeable_area.x_min,
            self.placeable_area.x_max - center[0],
            center[1] - self.placeable_area.y_min,
            self.placeable_area.y_max - center[1]
        )
        score -= edge_dist * 0.5  # Prefer edges for thermal
        
        return score
    
    def _score_signal_integrity(self, ref: str, center: Tuple[float, float]) -> float:
        """Score for signal integrity (keep related components close)."""
        score = 0.0
        
        # For each net this component connects to
        for pin in self.circuit.components[ref].pins:
            if not pin.connected_net:
                continue
            net = self.circuit.nets.get(pin.connected_net)
            if not net:
                continue
            
            # Find other components on this net
            for other_pin in net.connected_pins:
                other_ref = other_pin['ref']
                if other_ref == ref or other_ref not in self.placed:
                    continue
                
                other_center = self.placed[other_ref].bbox.center
                dist = math.hypot(center[0] - other_center[0], center[1] - other_center[1])
                
                # Penalize long traces for high-speed/power nets
                if pin.connected_net in self.power_nets:
                    score += dist * 0.5
                else:
                    score += dist * 0.1
        
        return score
    
    def _resolve_collisions(self):
        """Resolve any remaining collisions by nudging components."""
        max_iterations = 50
        
        for _ in range(max_iterations):
            collisions = []
            
            # Find all collisions
            refs = list(self.placed.keys())
            for i, ref1 in enumerate(refs):
                for ref2 in refs[i+1:]:
                    p1 = self.placed[ref1]
                    p2 = self.placed[ref2]
                    if p1.bbox.intersects(p2.bbox, self.MIN_CLEARANCE):
                        collisions.append((ref1, ref2))
            
            if not collisions:
                break
            
            # Resolve each collision
            for ref1, ref2 in collisions:
                self._resolve_pair_collision(ref1, ref2)
    
    def _resolve_pair_collision(self, ref1: str, ref2: str):
        """Resolve collision between two components."""
        p1 = self.placed[ref1]
        p2 = self.placed[ref2]
        
        c1 = p1.bbox.center
        c2 = p2.bbox.center
        
        # Vector from p2 to p1
        dx = c1[0] - c2[0]
        dy = c1[1] - c2[1]
        dist = math.hypot(dx, dy)
        
        if dist == 0:
            dx, dy = 1, 0
            dist = 1
        
        # Required separation
        required = (p1.geometry.bbox.width + p2.geometry.bbox.width) / 2 + self.MIN_CLEARANCE
        required = max(required, (p1.geometry.bbox.height + p2.geometry.bbox.height) / 2 + self.MIN_CLEARANCE)
        
        # Move apart
        if dist < required:
            move = (required - dist) / 2
            nx, ny = dx / dist, dy / dist
            
            # Try moving p1
            new_pos1 = (p1.position[0] + nx * move, p1.position[1] + ny * move)
            if self._is_valid_position(ref1, new_pos1, p1.rotation):
                p1.position = new_pos1
            else:
                # Try moving p2 instead
                new_pos2 = (p2.position[0] - nx * move, p2.position[1] - ny * move)
                if self._is_valid_position(ref2, new_pos2, p2.rotation):
                    p2.position = new_pos2
    
    def _optimize_placement(self):
        """Optimize placement for routing."""
        # Simple optimization: try to align components on grid
        grid_size = 2.54  # 100 mil grid
        
        for ref, placed in self.placed.items():
            # Snap to grid
            x = round(placed.position[0] / grid_size) * grid_size
            y = round(placed.position[1] / grid_size) * grid_size
            
            new_pos = (x, y)
            if self._is_valid_position(ref, new_pos, placed.rotation):
                placed.position = new_pos


def smart_place_components(
    circuit: CircuitIR,
    board_width: float = 100.0,
    board_height: float = 80.0,
    strategy: PlacementStrategy = PlacementStrategy.BALANCED
) -> Dict[str, PlacedComponent]:
    """
    High-level function to place all components intelligently.
    
    Returns dict of ref -> PlacedComponent with positions.
    """
    placer = SmartPlacer(circuit, board_width, board_height, strategy)
    return placer.place_all()


def generate_pcb_with_smart_placement(
    circuit: CircuitIR,
    board_width: float = 100.0,
    board_height: float = 80.0,
    strategy: PlacementStrategy = PlacementStrategy.BALANCED
) -> str:
    """
    Generate KiCad PCB with smart placement.
    
    This replaces the basic grid placement in KiCadGenerator.
    """
    placed = smart_place_components(circuit, board_width, board_height, strategy)
    
    import json
    import uuid
    
    pcb_uuid = str(uuid.uuid4())
    footprints_sexpr = []
    
    for ref, placed in placed.items():
        fp_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{circuit.id}_{ref}_fp"))
        fp_name = placed.geometry.footprint_name
        
        footprints_sexpr.append(f"""  (footprint "{fp_name}"
    (layer "{placed.layer}")
    (at {placed.position[0]:.2f} {placed.position[1]:.2f} {placed.rotation})
    (uuid "{fp_uuid}")
    (property "Reference" "{ref}" (at 0 -2.5 0) (layer "F.SilkS")
      (effects (font (size 1 1) (thickness 0.15)))
    )
    (property "Value" "{placed.component.value}" (at 0 2.5 0) (layer "F.Fab")
      (effects (font (size 1 1) (thickness 0.15)))
    )
  )""")
    
    footprints_block = "\n".join(footprints_sexpr)
    
    return f"""(kicad_pcb
  (version 20240108)
  (generator "ai-electronics-platform")
  (generator_version "1.0.0")
  (general
    (thickness 1.6)
  )
  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (44 "Edge.Cuts" user)
  )
  (setup
    (pad_to_mask_clearance 0.05)
  )
{footprints_block}
  (gr_line (start 50 50) (end {board_width-50} 50) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start {board_width-50} 50) (end {board_width-50} {board_height-50}) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start {board_width-50} {board_height-50}) (end 50 {board_height-50}) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 50 {board_height-50}) (end 50 50) (layer "Edge.Cuts") (width 0.1))
)
"""