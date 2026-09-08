import math
import random
import sys
from collections import defaultdict
from dataclasses import dataclass

import pygame

# ============================================================
# Artificial-life style battle simulation
# ------------------------------------------------------------
# 1000 vs 1000 agents by default.
# Each agent uses only local information:
#   - search nearby enemies
#   - approach a target
#   - avoid crowding
#   - retreat when locally outnumbered / badly wounded
#   - attack when in range
# A spatial grid keeps neighbor searches much cheaper than O(N^2).
# ============================================================

BATTLE_VIEW_WIDTH = 600
BATTLE_VIEW_HEIGHT = 600
LOGICAL_WORLD_WIDTH = BATTLE_VIEW_WIDTH
LOGICAL_WORLD_HEIGHT = BATTLE_VIEW_HEIGHT

# Compatibility aliases point at the logical simulation world; the view size is
# still represented separately by BATTLE_VIEW_WIDTH/BATTLE_VIEW_HEIGHT.
WORLD_WIDTH = LOGICAL_WORLD_WIDTH
WORLD_HEIGHT = LOGICAL_WORLD_HEIGHT

PANEL_WIDTH = 220
BOTTOM_PANEL_HEIGHT = 150
WIDTH = PANEL_WIDTH * 2 + BATTLE_VIEW_WIDTH
HEIGHT = BATTLE_VIEW_HEIGHT + BOTTOM_PANEL_HEIGHT
FPS = 60

TEAM_SIZE = 1000
TEAM_RED = 0
TEAM_BLUE = 1

TACTICAL_TURN_SECONDS = 1.0
ORDER_DURATION_TURNS = 5.0
MANEUVER_COMMANDS = (
    "LEFT_ADVANCE",
    "RIGHT_ADVANCE",
    "CENTER_BREAK",
    "ENCIRCLE",
)
STANCE_COMMANDS = ("CHARGE", "DEFENSE")
INITIAL_FORMATION_NAMES = ("THREE_BAND", "SINGLE_BLOCK")
FORMATION_LATERAL_SPACING = LOGICAL_WORLD_HEIGHT * 0.22
FORMATION_TOLERANCE = 12.0
FORMATION_CORRECTION_STRENGTH = 0.8
FORMATION_MAX_CORRECTION = 1.5
FORMATION_COMBAT_STRENGTH = 0.35
FORMATION_ANCHOR_RESPONSE = 4.0
FORMATION_ORIGIN_ADVANCE_SPEED = 24.0
FORMATION_ADVANCE_DISTANCE = LOGICAL_WORLD_WIDTH * (110.0 / 700.0)
FORMATION_ENCIRCLE_FORWARD_DISTANCE = LOGICAL_WORLD_WIDTH * (85.0 / 700.0)
FORMATION_ENCIRCLE_LATERAL_DISTANCE = LOGICAL_WORLD_HEIGHT * (55.0 / 552.0)
FORMATION_ENGAGEMENT_GAP = 120.0
INITIAL_ARMY_X_RATIO = 130.0 / 700.0
HOME_X_RATIO = 65.0 / 700.0

BACKGROUND = (22, 25, 29)
RED = (225, 80, 76)
BLUE = (72, 145, 230)
RED_DARK = (120, 42, 40)
BLUE_DARK = (37, 78, 130)
RED_RETREAT = (255, 160, 60)
BLUE_RETREAT = (100, 200, 255)
WHITE = (235, 235, 235)
GRAY = (135, 140, 145)
GRID_COLOR = (38, 42, 48)

CELL_SIZE = 20
SEPARATION_RADIUS = 5.0
MELEE_RANGE = 3.0

DEFAULT_PERCEPTION_RADIUS = 64.0
LOCAL_BALANCE_RADIUS = 24.0
ENCIRCLEMENT_SECTORS = 8
ESCAPE_DIRECTION_SAMPLES = 16
MIN_ENEMIES_PER_ENCIRCLEMENT_SECTOR = 2
REAR_PRESSURE = 0.30
SIDE_PRESSURE = 0.15
FRONT_REAR_BONUS = 0.20
BOTH_SIDES_BONUS = 0.20
ENCIRCLEMENT_RETREAT_THRESHOLD = 0.55
ENCIRCLEMENT_COURAGE_THRESHOLD = 0.72

SIM_SPEED = 1.0

PARAMETER_NAMES = (
    ("HP", "max_hp"),
    ("MOVE SPEED", "speed"),
    ("ATTACK POWER", "damage"),
    ("ATTACK INTERVAL", "attack_interval"),
    ("ARMOR", "armor"),
    ("PERCEPTION", "perception"),
    ("AGGRESSION", "aggression"),
    ("COURAGE", "courage"),
)

PARAMETER_STEPS = {
    "max_hp": 5.0,
    "speed": 1.0,
    "damage": 1.0,
    "attack_interval": 0.05,
    "armor": 0.01,
    "perception": 5.0,
    "aggression": 0.05,
    "courage": 0.05,
}

@dataclass(frozen=True)
class FormationUnitSpec:
    unit_id: str
    population_ratio: float
    base_forward_offset: float
    base_lateral_offset: float


@dataclass(frozen=True)
class FormationDefinition:
    name: str
    units: tuple


@dataclass
class FormationUnitState:
    unit_id: str
    base_offset_local: pygame.Vector2
    current_offset_local: pygame.Vector2
    target_offset_local: pygame.Vector2


THREE_BAND_FORMATION = FormationDefinition(
    name="THREE_BAND",
    units=(
        FormationUnitSpec("UNIT_0", 0.30, 0.0, -1.0),
        FormationUnitSpec("UNIT_1", 0.40, 0.0, 0.0),
        FormationUnitSpec("UNIT_2", 0.30, 0.0, 1.0),
    ),
)
SINGLE_BLOCK_FORMATION = FormationDefinition(
    name="SINGLE_BLOCK",
    units=(FormationUnitSpec("UNIT_0", 1.0, 0.0, 0.0),),
)
FORMATION_DEFINITIONS = {
    THREE_BAND_FORMATION.name: THREE_BAND_FORMATION,
    SINGLE_BLOCK_FORMATION.name: SINGLE_BLOCK_FORMATION,
}


@dataclass
class TeamConfig:
    values: dict


@dataclass
class LocalSituation:
    allies: int
    enemies: int
    enemy_direction_count: int
    encirclement_ratio: float
    front_enemies: int
    rear_enemies: int
    left_enemies: int
    right_enemies: int
    encirclement_pressure: float


@dataclass
class CommonConfig:
    red_team_size: int = TEAM_SIZE
    blue_team_size: int = TEAM_SIZE
    cell_size: int = CELL_SIZE
    separation_radius: float = SEPARATION_RADIUS
    melee_range: float = MELEE_RANGE
    local_balance_radius: float = LOCAL_BALANCE_RADIUS


DEFAULT_TEAM_VALUES = {
    "max_hp": (80.0, 120.0),
    "speed": (34.0, 52.0),
    "damage": (8.0, 15.0),
    "attack_interval": (0.45, 0.75),
    "armor": (0.05, 0.25),
    "perception": (DEFAULT_PERCEPTION_RADIUS * 0.8, DEFAULT_PERCEPTION_RADIUS * 1.2),
    "aggression": (0.35, 1.0),
    "courage": (0.25, 1.0),
}


def clamp(value, low, high):
    return max(low, min(high, value))


def world_to_view(pos: pygame.Vector2) -> pygame.Vector2:
    return pygame.Vector2(
        pos.x * (BATTLE_VIEW_WIDTH / LOGICAL_WORLD_WIDTH),
        pos.y * (BATTLE_VIEW_HEIGHT / LOGICAL_WORLD_HEIGHT),
    )


def view_to_world(pos: pygame.Vector2) -> pygame.Vector2:
    return pygame.Vector2(
        pos.x * (LOGICAL_WORLD_WIDTH / BATTLE_VIEW_WIDTH),
        pos.y * (LOGICAL_WORLD_HEIGHT / BATTLE_VIEW_HEIGHT),
    )


def safe_normalize(v: pygame.Vector2) -> pygame.Vector2:
    if v.length_squared() < 1e-9:
        return pygame.Vector2()
    return v.normalize()


def _calculate_encirclement_pressure(front_enemies, rear_enemies, left_enemies, right_enemies):
    front_active = front_enemies >= MIN_ENEMIES_PER_ENCIRCLEMENT_SECTOR
    rear_active = rear_enemies >= MIN_ENEMIES_PER_ENCIRCLEMENT_SECTOR
    left_active = left_enemies >= MIN_ENEMIES_PER_ENCIRCLEMENT_SECTOR
    right_active = right_enemies >= MIN_ENEMIES_PER_ENCIRCLEMENT_SECTOR

    pressure = 0.0
    if rear_active:
        pressure += REAR_PRESSURE
    if left_active:
        pressure += SIDE_PRESSURE
    if right_active:
        pressure += SIDE_PRESSURE
    if front_active and rear_active:
        pressure += FRONT_REAR_BONUS
    if left_active and right_active:
        pressure += BOTH_SIDES_BONUS
    return clamp(pressure, 0.0, 1.0)


class Agent:
    __slots__ = (
        "team",
        "pos",
        "vel",
        "alive",
        "hp",
        "max_hp",
        "speed",
        "damage",
        "attack_interval",
        "attack_cooldown",
        "armor",
        "perception",
        "aggression",
        "courage",
        "target",
        "retarget_timer",
        "radius",
        "retreating",
        "forward",
        "formation_unit_id",
        "formation_slot_local",
    )

    def __init__(self, team: int, x: float, y: float, config: TeamConfig):
        self.team = team
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2()
        self.alive = True
        self.forward = pygame.Vector2(1.0, 0.0) if team == TEAM_RED else pygame.Vector2(-1.0, 0.0)

        # Slightly different traits give the population a more "life-like"
        # character and create local variation without scripting individuals.
        values = config.values
        self.max_hp = random.uniform(*values["max_hp"])
        self.hp = self.max_hp
        self.speed = random.uniform(*values["speed"])
        self.damage = random.uniform(*values["damage"])
        self.attack_interval = random.uniform(*values["attack_interval"])
        self.attack_cooldown = random.random() * self.attack_interval
        self.armor = clamp(random.uniform(*values["armor"]), 0.0, 0.95)
        self.perception = random.uniform(*values["perception"])
        self.aggression = random.uniform(*values["aggression"])
        self.courage = random.uniform(*values["courage"])
        self.target = None
        self.retarget_timer = random.uniform(0.05, 0.35)
        self.radius = 2
        self.retreating = False
        self.formation_unit_id = None
        self.formation_slot_local = pygame.Vector2()

    def _directional_damage_multiplier(self, incoming_dir: pygame.Vector2 | None) -> float:
        if incoming_dir is None or incoming_dir.length_squared() <= 1e-9:
            return 1.0

        incoming_norm = safe_normalize(incoming_dir)
        forward = safe_normalize(self.forward)
        dot = forward.dot(incoming_norm)
        if dot > 0.5:
            return 0.5
        if dot < -0.5:
            return 1.5
        return 1.0

    def calculate_received_damage(
        self,
        amount: float,
        incoming_dir: pygame.Vector2 | None,
        incoming_multiplier: float = 1.0,
    ) -> float:
        if not self.alive:
            return 0.0

        total_multiplier = incoming_multiplier * self._directional_damage_multiplier(incoming_dir)

        armor_value = clamp(self.armor, 0.0, 0.95)
        armor_multiplier = 1.0 - armor_value
        total_multiplier *= armor_multiplier

        return max(0.0, amount * total_multiplier)

    def apply_damage(self, amount: float):
        if not self.alive:
            return
        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            self.target = None
            self.vel.xy = 0, 0

    def take_damage(self, amount: float, incoming_dir: pygame.Vector2 | None = None, incoming_multiplier: float = 1.0):
        if not self.alive:
            return
        self.apply_damage(self.calculate_received_damage(amount, incoming_dir, incoming_multiplier))


class SpatialGrid:
    def __init__(self, cell_size: int):
        self.cell_size = cell_size
        self.cells = defaultdict(list)

    def clear(self):
        self.cells.clear()

    def key(self, pos: pygame.Vector2):
        return int(pos.x // self.cell_size), int(pos.y // self.cell_size)

    def rebuild(self, agents):
        self.clear()
        for agent in agents:
            if agent.alive:
                self.cells[self.key(agent.pos)].append(agent)

    def nearby(self, pos: pygame.Vector2, radius: float):
        cx, cy = self.key(pos)
        cell_r = int(math.ceil(radius / self.cell_size))
        for gx in range(cx - cell_r, cx + cell_r + 1):
            for gy in range(cy - cell_r, cy + cell_r + 1):
                yield from self.cells.get((gx, gy), ())


class BattleSimulation:
    def __init__(self, red_config, blue_config, common_config):
        self.red_config = red_config
        self.blue_config = blue_config
        self.common_config = common_config
        self.grid = SpatialGrid(common_config.cell_size)
        self.agents = []
        self.dead_positions = []
        self.team_maneuver = {TEAM_RED: None, TEAM_BLUE: None}
        self.team_stance = {TEAM_RED: None, TEAM_BLUE: None}
        self.maneuver_turns_remaining = {TEAM_RED: 0.0, TEAM_BLUE: 0.0}
        self.stance_turns_remaining = {TEAM_RED: 0.0, TEAM_BLUE: 0.0}
        self.team_formation_units = {TEAM_RED: {}, TEAM_BLUE: {}}
        self.team_formation_origin = {TEAM_RED: pygame.Vector2(), TEAM_BLUE: pygame.Vector2()}
        self.initial_formation = "THREE_BAND"
        self.elapsed = 0.0
        self.reset()

    def _clear_team_orders(self):
        self.team_maneuver = {TEAM_RED: None, TEAM_BLUE: None}
        self.team_stance = {TEAM_RED: None, TEAM_BLUE: None}
        self.maneuver_turns_remaining = {TEAM_RED: 0.0, TEAM_BLUE: 0.0}
        self.stance_turns_remaining = {TEAM_RED: 0.0, TEAM_BLUE: 0.0}

    def _formation_definition(self, formation_name=None):
        return FORMATION_DEFINITIONS.get(formation_name or self.initial_formation, THREE_BAND_FORMATION)

    def _army_basis(self, team):
        forward = pygame.Vector2(1.0, 0.0) if team == TEAM_RED else pygame.Vector2(-1.0, 0.0)
        return forward, forward.rotate(90.0)

    def _initialize_formation_units(self, team, formation_name):
        definition = self._formation_definition(formation_name)
        states = {}
        for spec in definition.units:
            base = pygame.Vector2(
                spec.base_forward_offset,
                spec.base_lateral_offset * FORMATION_LATERAL_SPACING,
            )
            states[spec.unit_id] = FormationUnitState(spec.unit_id, base, base.copy(), base.copy())
        self.team_formation_units[team] = states

    def _formation_weights(self, team):
        states = list(self.team_formation_units[team].values())
        if not states:
            return {}
        laterals = [state.base_offset_local.y for state in states]
        center = (min(laterals) + max(laterals)) * 0.5
        half_span = max(abs(value - center) for value in laterals)
        weights = {}
        for state in states:
            normalized = 0.0 if half_span <= 1e-9 else clamp((state.base_offset_local.y - center) / half_span, -1.0, 1.0)
            weights[state.unit_id] = normalized
        return weights

    def _update_formation_targets(self):
        for team, states in self.team_formation_units.items():
            maneuver = self.team_maneuver.get(team)
            normalized_lateral = self._formation_weights(team)
            for state in states.values():
                base = state.base_offset_local
                target = base.copy()
                lateral = normalized_lateral.get(state.unit_id, 0.0)
                if maneuver == "LEFT_ADVANCE":
                    target.x += max(0.0, -lateral) * FORMATION_ADVANCE_DISTANCE
                elif maneuver == "RIGHT_ADVANCE":
                    target.x += max(0.0, lateral) * FORMATION_ADVANCE_DISTANCE
                elif maneuver == "CENTER_BREAK":
                    target.x += max(0.0, 1.0 - abs(lateral)) * FORMATION_ADVANCE_DISTANCE
                elif maneuver == "ENCIRCLE":
                    flank = abs(lateral)
                    target.x += flank * FORMATION_ENCIRCLE_FORWARD_DISTANCE
                    target.y += lateral * FORMATION_ENCIRCLE_LATERAL_DISTANCE
                state.target_offset_local = target

    def _update_formation_state(self, dt):
        response = clamp(FORMATION_ANCHOR_RESPONSE * dt, 0.0, 1.0)
        for states in self.team_formation_units.values():
            for state in states.values():
                state.current_offset_local = state.current_offset_local.lerp(state.target_offset_local, response)

    def _update_formation_origins(self, dt):
        red_origin = self.team_formation_origin[TEAM_RED]
        blue_origin = self.team_formation_origin[TEAM_BLUE]
        minimum_gap = FORMATION_ENGAGEMENT_GAP
        for team, opposing_origin in ((TEAM_RED, blue_origin), (TEAM_BLUE, red_origin)):
            origin = self.team_formation_origin[team]
            forward, _ = self._army_basis(team)
            remaining = (opposing_origin.x - origin.x) * forward.x
            if remaining <= minimum_gap:
                continue
            origin += forward * min(FORMATION_ORIGIN_ADVANCE_SPEED * dt, remaining - minimum_gap)
            self.team_formation_origin[team] = origin

    def _formation_anchor_for(self, team, unit_id, formation_origin=None):
        state = self.team_formation_units.get(team, {}).get(unit_id)
        if state is None:
            return formation_origin if formation_origin is not None else self.team_formation_origin[team]
        if formation_origin is None:
            formation_origin = self.team_formation_origin[team]
        forward, right = self._army_basis(team)
        return formation_origin + forward * state.current_offset_local.x + right * state.current_offset_local.y

    def _formation_vector_for_agent(self, agent, local_enemies):
        if agent.retreating or agent.formation_unit_id is None:
            return pygame.Vector2()
        anchor = self._formation_anchor_for(agent.team, agent.formation_unit_id)
        forward, right = self._army_basis(agent.team)
        desired = anchor + forward * agent.formation_slot_local.x + right * agent.formation_slot_local.y
        error = desired - agent.pos
        distance = error.length()
        if distance <= FORMATION_TOLERANCE:
            return pygame.Vector2()
        strength = min(FORMATION_MAX_CORRECTION, (distance - FORMATION_TOLERANCE) * 0.04 * FORMATION_CORRECTION_STRENGTH)
        if agent.target is not None and agent.target.alive:
            if agent.pos.distance_squared_to(agent.target.pos) <= (self.common_config.melee_range * 3.0) ** 2:
                strength *= FORMATION_COMBAT_STRENGTH
        elif local_enemies > 0:
            strength *= 0.7
        return safe_normalize(error) * strength

    def _activate_maneuver(self, team: int, command: str | None):
        if command not in MANEUVER_COMMANDS and command is not None:
            return
        if command is None:
            self.team_maneuver[team] = None
            self.maneuver_turns_remaining[team] = 0.0
            return
        self.team_maneuver[team] = command
        self.maneuver_turns_remaining[team] = ORDER_DURATION_TURNS

    def _activate_stance(self, team: int, stance: str | None):
        if stance not in STANCE_COMMANDS and stance is not None:
            return
        if stance is None:
            self.team_stance[team] = None
            self.stance_turns_remaining[team] = 0.0
            return
        self.team_stance[team] = stance
        self.stance_turns_remaining[team] = ORDER_DURATION_TURNS

    def _update_order_timers(self, dt: float):
        if TACTICAL_TURN_SECONDS <= 0.0:
            return
        turn_delta = dt / TACTICAL_TURN_SECONDS
        for team in (TEAM_RED, TEAM_BLUE):
            if self.team_maneuver[team] is not None:
                self.maneuver_turns_remaining[team] -= turn_delta
                if self.maneuver_turns_remaining[team] <= 0.0:
                    self.team_maneuver[team] = None
                    self.maneuver_turns_remaining[team] = 0.0
            if self.team_stance[team] is not None:
                self.stance_turns_remaining[team] -= turn_delta
                if self.stance_turns_remaining[team] <= 0.0:
                    self.team_stance[team] = None
                    self.stance_turns_remaining[team] = 0.0

    def _team_offensive_multiplier(self, team: int, is_outgoing: bool):
        stance = self.team_stance.get(team)
        if stance == "CHARGE":
            return 1.25 if is_outgoing else 1.20
        if stance == "DEFENSE":
            return 0.80 if is_outgoing else 0.75
        return 1.0

    def _effective_damage_multiplier(self, team: int, is_outgoing: bool):
        return self._team_offensive_multiplier(team, is_outgoing)

    def reset(self):
        self.grid = SpatialGrid(self.common_config.cell_size)
        self.agents.clear()
        self.dead_positions.clear()
        self.team_formation_units = {TEAM_RED: {}, TEAM_BLUE: {}}
        self.team_formation_origin = {TEAM_RED: pygame.Vector2(), TEAM_BLUE: pygame.Vector2()}
        self._clear_team_orders()
        self.elapsed = 0.0
        self._spawn_army(
            TEAM_RED,
            center_x=LOGICAL_WORLD_WIDTH * INITIAL_ARMY_X_RATIO,
            center_y=LOGICAL_WORLD_HEIGHT / 2,
            facing=1,
            team_size=self.common_config.red_team_size,
            formation_name=self.initial_formation,
        )
        self._spawn_army(
            TEAM_BLUE,
            center_x=LOGICAL_WORLD_WIDTH * (1.0 - INITIAL_ARMY_X_RATIO),
            center_y=LOGICAL_WORLD_HEIGHT / 2,
            facing=-1,
            team_size=self.common_config.blue_team_size,
            formation_name=self.initial_formation,
        )
        self.grid.rebuild(self.agents)

    def _band_counts_for_total(self, total: int):
        return self._formation_counts(total, THREE_BAND_FORMATION.units)

    def _formation_counts(self, total, unit_specs):
        counts = [int(round(total * spec.population_ratio)) for spec in unit_specs]
        while sum(counts) < total:
            counts[max(range(len(counts)), key=lambda index: unit_specs[index].population_ratio)] += 1
        while sum(counts) > total:
            for index in reversed(range(len(counts))):
                if counts[index] > 0:
                    counts[index] -= 1
                    break
        return counts

    def _spawn_formation(self, team, center_x, center_y, facing, team_size, formation_name):
        definition = self._formation_definition(formation_name)
        self._initialize_formation_units(team, definition.name)
        center = pygame.Vector2(center_x, center_y)
        self.team_formation_origin[team] = center.copy()
        forward, right = self._army_basis(team)
        counts = self._formation_counts(team_size, definition.units)
        config = self.red_config if team == TEAM_RED else self.blue_config
        spacing_x = 6.0
        spacing_y = 6.0
        for spec, unit_count in zip(definition.units, counts):
            if unit_count <= 0:
                continue
            unit_state = self.team_formation_units[team][spec.unit_id]
            anchor = center + forward * unit_state.base_offset_local.x + right * unit_state.base_offset_local.y
            cols = max(3, min(25, math.ceil(math.sqrt(unit_count))))
            rows = math.ceil(unit_count / cols)
            for row in range(rows):
                for col in range(cols):
                    if (row * cols + col) >= unit_count:
                        continue
                    local_forward = -(row - rows / 2) * spacing_x + random.uniform(-0.5, 0.5)
                    local_lateral = (col - cols / 2) * spacing_y + random.uniform(-0.5, 0.5)
                    position = anchor + forward * local_forward + right * local_lateral
                    agent = Agent(team, position.x, position.y, config)
                    agent.formation_unit_id = spec.unit_id
                    agent.formation_slot_local = pygame.Vector2(local_forward, local_lateral)
                    self.agents.append(agent)

    def _spawn_single_block_formation(self, team, center_x, center_y, facing, team_size):
        self._spawn_formation(team, center_x, center_y, facing, team_size, "SINGLE_BLOCK")

    def _spawn_three_band_formation(self, team, center_x, center_y, facing, team_size):
        self._spawn_formation(team, center_x, center_y, facing, team_size, "THREE_BAND")

    def _spawn_army(self, team, center_x, center_y, facing, team_size, formation_name=None):
        formation_name = formation_name or self.initial_formation
        self._spawn_formation(team, center_x, center_y, facing, team_size, formation_name)

    def alive_counts(self):
        red = 0
        blue = 0
        for a in self.agents:
            if a.alive:
                if a.team == TEAM_RED:
                    red += 1
                else:
                    blue += 1
        return red, blue

    def update(self, dt: float):
        self.elapsed += dt
        self._update_order_timers(dt)
        self.grid.rebuild(self.agents)

        # Enemy centers are only a coarse strategic bias. Individual decisions
        # still come from local sensing.
        self._update_formation_origins(dt)
        self._update_formation_targets()
        self._update_formation_state(dt)

        for agent in self.agents:
            if not agent.alive:
                continue

            agent.attack_cooldown = max(0.0, agent.attack_cooldown - dt)
            agent.retarget_timer -= dt

            if agent.retarget_timer <= 0.0:
                agent.target = self._acquire_target(agent)
                # Stagger retargeting so all 2000 agents do not search together.
                agent.retarget_timer = random.uniform(0.18, 0.42)

            local_state = self._local_tactical_state(agent)
            move = self._movement_vector(
                agent,
                self.team_formation_origin[TEAM_RED],
                self.team_formation_origin[TEAM_BLUE],
                local_state.allies,
                local_state.enemies,
                local_state,
            )

            if move.length_squared() > 1e-9:
                desired = safe_normalize(move) * agent.speed
                # Smooth acceleration instead of instant direction changes.
                response = clamp(7.0 * dt, 0.0, 1.0)
                agent.vel = agent.vel.lerp(desired, response)
            else:
                agent.vel *= max(0.0, 1.0 - 8.0 * dt)

            if agent.vel.length_squared() > 1e-6:
                agent.forward = agent.vel.normalize()

            agent.pos += agent.vel * dt
            agent.pos.x = clamp(agent.pos.x, 8, LOGICAL_WORLD_WIDTH - 8)
            agent.pos.y = clamp(agent.pos.y, 8, LOGICAL_WORLD_HEIGHT - 8)

        # Resolve combat in a second pass so every agent decides against the same
        # world state before any damage is applied. This removes per-frame update
        # order bias from sequential attack resolution.
        attack_events = []
        for agent in self.agents:
            if not agent.alive:
                continue
            self._collect_attack_event(agent, attack_events)

        resolved_targets = defaultdict(list)
        for attacker, target, incoming_dir, incoming_multiplier in attack_events:
            if not attacker.alive or not target.alive:
                continue
            resolved_targets[target].append((attacker, incoming_dir, incoming_multiplier))

        for target, hits in resolved_targets.items():
            if not target.alive:
                continue

            total_damage = 0.0
            for attacker, incoming_dir, incoming_multiplier in hits:
                # Attack intent is fixed before damage application. A unit that dies
                # earlier in the same frame must still resolve the hits it already
                # committed to, otherwise the update order can bias the result.
                final_damage = attacker.damage * random.uniform(0.82, 1.18) * self._team_offensive_multiplier(attacker.team, True)
                total_damage += target.calculate_received_damage(final_damage, incoming_dir, incoming_multiplier)
                attacker.attack_cooldown = attacker.attack_interval

            if total_damage <= 0.0:
                continue

            target.apply_damage(total_damage)

        # Save a tiny visual record of deaths, then forget dead agents' targets.
        # We do not remove objects from self.agents so references stay stable.
        # Corpses are capped to prevent unbounded rendering work.
        for a in self.agents:
            if not a.alive and getattr(a, "_death_recorded", False):
                pass

    def _team_centers(self):
        rx = ry = bx = by = 0.0
        rc = bc = 0
        for a in self.agents:
            if not a.alive:
                continue
            if a.team == TEAM_RED:
                rx += a.pos.x
                ry += a.pos.y
                rc += 1
            else:
                bx += a.pos.x
                by += a.pos.y
                bc += 1

        red_center = pygame.Vector2(rx / rc, ry / rc) if rc else pygame.Vector2(LOGICAL_WORLD_WIDTH * 0.25, LOGICAL_WORLD_HEIGHT / 2)
        blue_center = pygame.Vector2(bx / bc, by / bc) if bc else pygame.Vector2(LOGICAL_WORLD_WIDTH * 0.75, LOGICAL_WORLD_HEIGHT / 2)
        return red_center, blue_center

    def _acquire_target(self, agent: Agent):
        best = None
        best_d2 = agent.perception * agent.perception

        for other in self.grid.nearby(agent.pos, agent.perception):
            if not other.alive or other.team == agent.team:
                continue
            d2 = agent.pos.distance_squared_to(other.pos)
            if d2 < best_d2:
                best_d2 = d2
                best = other
        return best

    def _local_tactical_state(self, agent: Agent, enemy_list=None):
        allies = 0
        enemies = []
        local_radius = self.common_config.local_balance_radius
        r2 = local_radius * local_radius
        agent_pos = agent.pos
        agent_forward = safe_normalize(agent.forward)
        if agent_forward.length_squared() < 1e-9:
            agent_forward = pygame.Vector2(1.0, 0.0)
        forward_angle = math.atan2(agent_forward.y, agent_forward.x)
        sector_step = (2.0 * math.pi) / ENCIRCLEMENT_SECTORS

        if enemy_list is None:
            nearby = self.grid.nearby(agent_pos, local_radius)
            for other in nearby:
                if other is agent or not other.alive:
                    continue
                if agent_pos.distance_squared_to(other.pos) > r2:
                    continue
                if other.team == agent.team:
                    allies += 1
                else:
                    enemies.append(other)
        else:
            enemies = list(enemy_list)
            nearby = self.grid.nearby(agent_pos, local_radius)
            for other in nearby:
                if other is agent or not other.alive:
                    continue
                if agent_pos.distance_squared_to(other.pos) > r2:
                    continue
                if other.team == agent.team:
                    allies += 1

        sector_counts = [0] * ENCIRCLEMENT_SECTORS
        front_enemies = rear_enemies = left_enemies = right_enemies = 0
        for enemy in enemies:
            rel = enemy.pos - agent_pos
            rel_length_sq = rel.length_squared()
            if rel_length_sq <= 1e-9:
                continue
            enemy_dir = rel / math.sqrt(rel_length_sq)
            forward_dot = agent_forward.dot(enemy_dir)
            if forward_dot > 0.5:
                front_enemies += 1
            elif forward_dot < -0.5:
                rear_enemies += 1
            elif agent_forward.x * enemy_dir.y - agent_forward.y * enemy_dir.x >= 0.0:
                left_enemies += 1
            else:
                right_enemies += 1
            relative_angle = math.atan2(rel.y, rel.x) - forward_angle
            sector = int((relative_angle + math.pi) / sector_step) % ENCIRCLEMENT_SECTORS
            sector_counts[sector] += 1

        enemy_direction_count = sum(
            1 for count in sector_counts if count >= MIN_ENEMIES_PER_ENCIRCLEMENT_SECTOR
        )
        encirclement_ratio = enemy_direction_count / float(ENCIRCLEMENT_SECTORS)
        encirclement_pressure = _calculate_encirclement_pressure(
            front_enemies, rear_enemies, left_enemies, right_enemies
        )
        return LocalSituation(
            allies,
            len(enemies),
            enemy_direction_count,
            encirclement_ratio,
            front_enemies,
            rear_enemies,
            left_enemies,
            right_enemies,
            encirclement_pressure,
        )

    def _local_balance(self, agent: Agent):
        local_state = self._local_tactical_state(agent)
        return local_state.allies, local_state.enemies

    def _calculate_escape_direction(self, agent: Agent):
        nearby_enemies = []
        agent_pos = agent.pos
        search_radius = self.common_config.local_balance_radius * 2.0
        r2 = search_radius * search_radius
        for other in self.grid.nearby(agent_pos, search_radius):
            if other is agent or not other.alive or other.team == agent.team:
                continue
            if agent_pos.distance_squared_to(other.pos) > r2:
                continue
            nearby_enemies.append(other)

        home_x = LOGICAL_WORLD_WIDTH * HOME_X_RATIO if agent.team == TEAM_RED else LOGICAL_WORLD_WIDTH * (1.0 - HOME_X_RATIO)
        home_target = pygame.Vector2(home_x, LOGICAL_WORLD_HEIGHT / 2.0)
        home_dir = safe_normalize(home_target - agent_pos)
        if not nearby_enemies:
            return home_dir if home_dir.length_squared() > 0.0 else safe_normalize(agent.forward)

        best_dir = pygame.Vector2(1.0, 0.0)
        best_score = None
        base_forward = safe_normalize(agent.forward)
        if base_forward.length_squared() < 1e-9:
            base_forward = pygame.Vector2(1.0, 0.0)
        home_bias = 0.12 if home_dir.length_squared() > 1e-9 else 0.0

        for index in range(ESCAPE_DIRECTION_SAMPLES):
            angle = (360.0 / ESCAPE_DIRECTION_SAMPLES) * index
            candidate = safe_normalize(base_forward.rotate(angle))
            danger = 0.0
            for enemy in nearby_enemies:
                enemy_vec = enemy.pos - agent_pos
                dist = enemy_vec.length()
                if dist <= 1e-9:
                    continue
                enemy_dir = safe_normalize(enemy_vec)
                alignment = max(0.0, candidate.dot(enemy_dir))
                if alignment > 0.0:
                    proximity_weight = 1.0 + 30.0 / (dist + 10.0)
                    danger += alignment * proximity_weight
            if home_bias > 0.0:
                danger -= max(0.0, candidate.dot(home_dir)) * home_bias
            if best_score is None or danger < best_score:
                best_score = danger
                best_dir = candidate

        return best_dir if best_dir.length_squared() > 0.0 else home_dir

    def _movement_vector(
        self,
        agent,
        red_center,
        blue_center,
        local_allies,
        local_enemies,
        local_state=None,
    ):
        separation = pygame.Vector2()
        separation_radius = self.common_config.separation_radius
        sep_r2 = separation_radius * separation_radius

        for other in self.grid.nearby(agent.pos, separation_radius):
            if other is agent or not other.alive:
                continue
            delta = agent.pos - other.pos
            d2 = delta.length_squared()
            if 0 < d2 < sep_r2:
                # Stronger repulsion at short distance.
                separation += delta / d2

        target_vec = pygame.Vector2()
        if agent.target is not None and agent.target.alive:
            delta = agent.target.pos - agent.pos
            dist = delta.length()
            if dist > self.common_config.melee_range * 0.85:
                target_vec = safe_normalize(delta)
            else:
                target_vec = pygame.Vector2()

        # Low-courage agents retreat if locally overwhelmed, but multi-direction
        # pressure makes retreat far easier even without a large raw number gap.
        hp_ratio = agent.hp / agent.max_hp
        local_state = self._local_tactical_state(agent) if local_state is None else local_state
        encirclement_pressure = local_state.encirclement_pressure
        outnumbered = local_enemies > max(2, local_allies * 1.55)
        badly_hurt = hp_ratio < (0.18 + (1.0 - agent.courage) * 0.22)
        effective_courage_threshold = 0.55 + encirclement_pressure * 0.25
        retreat = (
            (outnumbered and agent.courage < effective_courage_threshold)
            or badly_hurt
            or (
                encirclement_pressure >= ENCIRCLEMENT_RETREAT_THRESHOLD
                and agent.courage < ENCIRCLEMENT_COURAGE_THRESHOLD
            )
        )

        if retreat:
            target_vec = self._calculate_escape_direction(agent)

        # mark agent retreating state for rendering
        agent.retreating = retreat

        # Small deterministic-ish lateral variation to prevent one-dimensional
        # collisions and create a more organic front.
        lateral = pygame.Vector2(-target_vec.y, target_vec.x)
        wave = math.sin(agent.pos.x * 0.018 + agent.pos.y * 0.013 + self.elapsed * 1.2)

        return (
            target_vec * (1.0 + 0.8 * agent.aggression)
            + separation * 105.0
            + lateral * wave * 0.18
            + self._formation_vector_for_agent(agent, local_enemies)
        )

    def _collect_attack_event(self, agent: Agent, attack_events: list):
        target = agent.target
        if target is None or not target.alive:
            return

        attack_range = self.common_config.melee_range + agent.radius + target.radius
        if agent.pos.distance_squared_to(target.pos) > attack_range * attack_range:
            return

        agent.vel *= 0.55
        if agent.attack_cooldown > 0.0:
            return

        # The incoming direction is from the target toward the attacker,
        # as seen by the defender, so it matches the defender's forward.
        incoming_dir = agent.pos - target.pos
        target_multiplier = self._team_offensive_multiplier(target.team, False)
        attack_events.append((agent, target, incoming_dir, target_multiplier))


class InputField:
    ARROW_WIDTH = 20

    def __init__(self, rect, value, step=1.0):
        self.rect = pygame.Rect(rect)
        self.value = str(value)
        self.active = False
        self.step = step

        self.up_rect = pygame.Rect(
            self.rect.right - self.ARROW_WIDTH,
            self.rect.top,
            self.ARROW_WIDTH,
            self.rect.height // 2,
        )

        self.down_rect = pygame.Rect(
            self.rect.right - self.ARROW_WIDTH,
            self.rect.top + self.rect.height // 2,
            self.ARROW_WIDTH,
            self.rect.height - self.rect.height // 2,
        )

    def _change_value(self, amount):
        try:
            value = float(self.value)
        except ValueError:
            value = 0.0

        value += amount

        # Avoid values such as 0.30000000000000004
        value = round(value, 6)

        if float(value).is_integer():
            self.value = str(int(value))
        else:
            self.value = f"{value:g}"

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.up_rect.collidepoint(event.pos):
                self._change_value(self.step)
                self.active = False

            elif self.down_rect.collidepoint(event.pos):
                self._change_value(-self.step)
                self.active = False

            else:
                self.active = self.rect.collidepoint(event.pos)

        elif self.active and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]

            elif event.key == pygame.K_ESCAPE:
                self.active = False

            elif event.key == pygame.K_RETURN:
                self.active = False

            elif event.unicode in "0123456789.-":
                self.value += event.unicode

    def number(self, integer=False):
        try:
            value = float(self.value)
            return int(value) if integer else value
        except ValueError:
            return None

    def draw(self, screen, font, border_color):
        background = (65, 75, 84) if self.active else (40, 45, 51)

        pygame.draw.rect(screen, background, self.rect)
        pygame.draw.rect(
            screen,
            border_color if self.active else (80, 85, 90),
            self.rect,
            1,
        )

        # Divider between number and arrows
        pygame.draw.line(
            screen,
            (80, 85, 90),
            (self.up_rect.left, self.rect.top),
            (self.up_rect.left, self.rect.bottom),
        )

        pygame.draw.line(
            screen,
            (80, 85, 90),
            (self.up_rect.left, self.down_rect.top),
            (self.rect.right, self.down_rect.top),
        )

        screen.blit(
            font.render(self.value, True, WHITE),
            (self.rect.x + 5, self.rect.y + 4),
        )

        # ▲
        up_center_x = self.up_rect.centerx
        up_center_y = self.up_rect.centery
        pygame.draw.polygon(
            screen,
            WHITE,
            [
                (up_center_x, up_center_y - 3),
                (up_center_x - 4, up_center_y + 2),
                (up_center_x + 4, up_center_y + 2),
            ],
        )

        # ▼
        down_center_x = self.down_rect.centerx
        down_center_y = self.down_rect.centery
        pygame.draw.polygon(
            screen,
            WHITE,
            [
                (down_center_x, down_center_y + 3),
                (down_center_x - 4, down_center_y - 2),
                (down_center_x + 4, down_center_y - 2),
            ],
        )


def format_value(value):
    return f"{value:g}"


def create_team_fields(x, config, font):
    fields = {}
    start_y = 98

    for index, (label, key) in enumerate(PARAMETER_NAMES):
        y = start_y + index * 27
        step = PARAMETER_STEPS[key]

        # display as center and width instead of min/max
        vmin, vmax = config.values[key]
        center = (vmin + vmax) / 2.0
        width = max(0.0, vmax - vmin)
        fields[key] = (
            InputField(
                (x + 72, y, 64, 24),
                format_value(center),
                step,
            ),
            InputField(
                (x + 144, y, 64, 24),
                format_value(width),
                step,
            ),
        )

    return fields


def draw_order_button(screen, rect, label, active, accent, font):
    fill = accent if active else (40, 45, 51)
    border = accent if active else (80, 85, 90)
    pygame.draw.rect(screen, fill, rect)
    pygame.draw.rect(screen, border, rect, 1)
    text_color = WHITE if active else GRAY
    screen.blit(font.render(label, True, text_color), (rect.x + 6, rect.y + 4))


def draw_order_state(screen, rect, team, sim, team_color, small_font):
    maneuver_name = sim.team_maneuver.get(team) or "NORMAL"
    stance_name = sim.team_stance.get(team) or "NORMAL"
    maneuver_remaining = sim.maneuver_turns_remaining.get(team, 0.0)
    stance_remaining = sim.stance_turns_remaining.get(team, 0.0)

    screen.blit(small_font.render("ACTIVE ORDERS", True, team_color), (rect.x + 8, rect.y + 350))
    screen.blit(small_font.render(f"MOVE   {maneuver_name} [{maneuver_remaining:.1f}]", True, WHITE), (rect.x + 8, rect.y + 366))
    screen.blit(small_font.render(f"STANCE {stance_name} [{stance_remaining:.1f}]", True, WHITE), (rect.x + 8, rect.y + 382))


def draw_team_panel(screen, rect, title, color, fields, font, small_font, order_font, sim, team, order_buttons):
    pygame.draw.rect(screen, (17, 20, 24), rect)
    pygame.draw.line(screen, color, rect.topleft, rect.topright, 3)
    screen.blit(font.render(title, True, color), (rect.x + 8, rect.y + 12))
    pygame.draw.line(screen, (60, 65, 70), (rect.x + 8, rect.y + 35), (rect.right - 8, rect.y + 35), 1)
    screen.blit(small_font.render("FORCE SIZE", True, GRAY), (rect.x + 12, rect.y + 42))
    pygame.draw.line(screen, (60, 65, 70), (rect.x + 8, rect.y + 71), (rect.right - 8, rect.y + 71), 1)
    screen.blit(small_font.render("TRAITS", True, color), (rect.x + 8, rect.y + 78))
    screen.blit(small_font.render("CENTER", True, GRAY), (rect.x + 76, rect.y + 96))
    screen.blit(small_font.render("WIDTH", True, GRAY), (rect.x + 149, rect.y + 96))
    for label, key in PARAMETER_NAMES:
        left, right = fields[key]
        y = left.rect.y
        screen.blit(small_font.render(label.upper(), True, WHITE), (rect.x + 12, y + 5))
        for field in (left, right):
            field.draw(screen, small_font, color)
    team_size_field = fields.get("team_size")
    if team_size_field is not None:
        team_size_field.draw(screen, small_font, color)

    pygame.draw.line(screen, (60, 65, 70), (rect.x + 8, rect.y + 342), (rect.right - 8, rect.y + 342), 1)
    screen.blit(small_font.render("ORDERS", True, GRAY), (rect.x + 8, rect.y + 400))
    for order_name, btn_rect in order_buttons.items():
        is_active = (
            (order_name in MANEUVER_COMMANDS and sim.team_maneuver.get(team) == order_name)
            or (order_name in STANCE_COMMANDS and sim.team_stance.get(team) == order_name)
        )
        order_labels = {
            "LEFT_ADVANCE": "LEFT ADV.",
            "RIGHT_ADVANCE": "RIGHT ADV.",
            "CENTER_BREAK": "CENTER",
            "ENCIRCLE": "ENCIRCLE",
            "CHARGE": "CHARGE",
            "DEFENSE": "DEFENSE",
        }
        draw_order_button(screen, btn_rect, order_labels[order_name], is_active, color, order_font)

    draw_order_state(screen, rect, team, sim, color, small_font)

def draw_common_panel(screen, fields, font, small_font, status):
    rect = pygame.Rect(0, BATTLE_VIEW_HEIGHT, WIDTH, BOTTOM_PANEL_HEIGHT)
    pygame.draw.rect(screen, (17, 20, 24), rect)
    pygame.draw.line(screen, GRAY, rect.topleft, rect.topright, 2)
    screen.blit(font.render("COMMON PARAMETERS", True, WHITE), (12, rect.y + 10))
    labels = (("Cell size", "cell_size"), ("Separation", "separation_radius"),
              ("Melee range", "melee_range"), ("Local balance", "local_balance_radius"))
    for index, (label, key) in enumerate(labels):
        x = 12 + index * 150
        screen.blit(small_font.render(label, True, GRAY), (x, rect.y + 43))
        field = fields[key]
        pygame.draw.rect(screen, (40, 45, 51) if not field.active else (65, 75, 84), field.rect)
        pygame.draw.rect(screen, WHITE if field.active else (80, 85, 90), field.rect, 1)
        screen.blit(small_font.render(field.value, True, WHITE), (field.rect.x + 5, field.rect.y + 4))
    pygame.draw.rect(screen, (44, 105, 76), (WIDTH - 135, rect.y + 38, 120, 30))
    screen.blit(small_font.render("APPLY + RESET", True, WHITE), (WIDTH - 124, rect.y + 47))
    # Note: Pause/Reset/Grid buttons are drawn in main() within this panel area
    if status:
        screen.blit(small_font.render(status, True, RED if status.startswith("Invalid") else GRAY), (12, rect.y + 105))


def draw_world(screen, sim: BattleSimulation, font, small_font, show_grid):
    world = pygame.Surface((BATTLE_VIEW_WIDTH, BATTLE_VIEW_HEIGHT))
    world.fill(BACKGROUND)

    if show_grid:
        for x in range(0, LOGICAL_WORLD_WIDTH + sim.common_config.cell_size, sim.common_config.cell_size):
            x0 = world_to_view(pygame.Vector2(x, 0))
            x1 = world_to_view(pygame.Vector2(x, LOGICAL_WORLD_HEIGHT))
            pygame.draw.line(world, GRID_COLOR, (int(x0.x), int(x0.y)), (int(x1.x), int(x1.y)), 1)
        for y in range(0, LOGICAL_WORLD_HEIGHT + sim.common_config.cell_size, sim.common_config.cell_size):
            y0 = world_to_view(pygame.Vector2(0, y))
            y1 = world_to_view(pygame.Vector2(LOGICAL_WORLD_WIDTH, y))
            pygame.draw.line(world, GRID_COLOR, (int(y0.x), int(y0.y)), (int(y1.x), int(y1.y)), 1)

    # Dead agents are drawn first and dimmer.
    for a in sim.agents:
        if a.alive:
            continue
        color = RED_DARK if a.team == TEAM_RED else BLUE_DARK
        view_pos = world_to_view(a.pos)
        pygame.draw.circle(world, color, (int(view_pos.x), int(view_pos.y)), max(1, a.radius))

    # Living agents.
    for a in sim.agents:
        if not a.alive:
            continue
        if a.retreating:
            color = RED_RETREAT if a.team == TEAM_RED else BLUE_RETREAT
        else:
            color = RED if a.team == TEAM_RED else BLUE
        if a.forward.length_squared() > 1e-6:
            orient = a.forward.normalize()
        else:
            orient = pygame.Vector2(1, 0) if a.team == TEAM_RED else pygame.Vector2(-1, 0)

        cfg = sim.red_config if a.team == TEAM_RED else sim.blue_config
        keys = [
            "max_hp",
            "speed",
            "damage",
            "attack_interval",
            "armor",
            "perception",
            "aggression",
            "courage",
        ]
        norms = []
        for k in keys:
            v = getattr(a, k)
            rmin, rmax = cfg.values[k]
            if k == "attack_interval":
                if rmax - rmin != 0:
                    n = 1.0 - (v - rmin) / (rmax - rmin)
                else:
                    n = 0.0
            else:
                if rmax - rmin != 0:
                    n = (v - rmin) / (rmax - rmin)
                else:
                    n = 0.0
            norms.append(clamp(n, 0.0, 1.0))
        strength = sum(norms) / len(norms) if norms else 0.0
        if strength >= 0.66:
            tier_scale = 1.6
        elif strength >= 0.33:
            tier_scale = 1.0
        else:
            tier_scale = 0.6
        base = max(1, int(a.radius * 3 * 0.5))
        size = max(1, int(base * tier_scale))
        view_pos = world_to_view(a.pos)
        tip = view_pos + orient * (size * 0.9)
        left = view_pos + orient.rotate(140) * size
        right = view_pos + orient.rotate(-140) * size
        points = [(int(tip.x), int(tip.y)), (int(left.x), int(left.y)), (int(right.x), int(right.y))]
        pygame.draw.polygon(world, color, points)

    red, blue = sim.alive_counts()
    total = red + blue

    pygame.draw.rect(world, (10, 12, 14), (0, 0, BATTLE_VIEW_WIDTH, 42))
    world.blit(font.render(f"RED {red:4d}", True, RED), (12, 8))
    world.blit(font.render(f"BLUE {blue:4d}", True, BLUE), (140, 8))
    total_initial = sim.common_config.red_team_size + sim.common_config.blue_team_size
    world.blit(small_font.render(f"Alive {total:4d} / {total_initial}", True, WHITE), (275, 14))
    world.blit(small_font.render(f"Time {sim.elapsed:6.1f}s", True, WHITE), (440, 14))

    controls = "SPACE pause   R reset   G grid   +/- simulation speed   ESC quit"
    world.blit(small_font.render(controls, True, GRAY), (12, BATTLE_VIEW_HEIGHT - 22))

    if red == 0 or blue == 0:
        winner = "BLUE WINS" if red == 0 and blue > 0 else "RED WINS" if blue == 0 and red > 0 else "DRAW"
        text = font.render(winner + "   [R] restart", True, WHITE)
        rect = text.get_rect(center=(BATTLE_VIEW_WIDTH // 2, 70))
        pygame.draw.rect(world, (10, 12, 14), rect.inflate(30, 18))
        world.blit(text, rect)
    screen.blit(world, (PANEL_WIDTH, 0))


def main():
    global SIM_SPEED

    pygame.init()
    pygame.display.set_caption("Artificial-Life Battle Simulation - 1000 vs 1000")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 23, bold=True)
    small_font = pygame.font.SysFont("consolas", 15)
    order_font = pygame.font.SysFont("consolas", 12)

    red_config = TeamConfig(dict(DEFAULT_TEAM_VALUES))
    blue_config = TeamConfig(dict(DEFAULT_TEAM_VALUES))
    common_config = CommonConfig()
    red_fields = create_team_fields(0, red_config, small_font)
    blue_fields = create_team_fields(WIDTH - PANEL_WIDTH, blue_config, small_font)
    # Team-size fields per team (moved from common panel)
    red_team_size_field = InputField((108, 40, 100, 24), common_config.red_team_size, 1)
    blue_team_size_field = InputField((WIDTH - PANEL_WIDTH + 108, 40, 100, 24), common_config.blue_team_size, 1)
    # attach to fields dict for unified handling
    red_fields["team_size"] = red_team_size_field
    blue_fields["team_size"] = blue_team_size_field
    common_fields = {
        # Positions aligned with labels: x = 12, 162, 312, 462
        "cell_size": InputField(
            (12, BATTLE_VIEW_HEIGHT + 62, 120, 25),
            common_config.cell_size,
            1,
        ),
        "separation_radius": InputField(
            (162, BATTLE_VIEW_HEIGHT + 62, 120, 25),
            common_config.separation_radius,
            1.0,
        ),
        "melee_range": InputField(
            (312, BATTLE_VIEW_HEIGHT + 62, 120, 25),
            common_config.melee_range,
            1.0,
        ),
        "local_balance_radius": InputField(
            (462, BATTLE_VIEW_HEIGHT + 62, 120, 25),
            common_config.local_balance_radius,
            5.0,
        ),
    }
    sim = BattleSimulation(red_config, blue_config, common_config)
    paused = False
    show_grid = False
    status = ""
    red_order_buttons = {
        name: pygame.Rect(12 + (index % 2) * 98, 420 + (index // 2) * 25, 96, 22)
        for index, name in enumerate(MANEUVER_COMMANDS + STANCE_COMMANDS)
    }
    blue_order_buttons = {
        name: pygame.Rect(WIDTH - PANEL_WIDTH + 12 + (index % 2) * 98, 420 + (index // 2) * 25, 96, 22)
        for index, name in enumerate(MANEUVER_COMMANDS + STANCE_COMMANDS)
    }
    apply_rect = pygame.Rect(WIDTH - 135, BATTLE_VIEW_HEIGHT + 38, 120, 30)
    # UI button rects (moved into common panel at bottom, right-aligned)
    pause_rect = pygame.Rect(WIDTH - 320, BATTLE_VIEW_HEIGHT + 8, 60, 26)
    reset_rect = pygame.Rect(WIDTH - 250, BATTLE_VIEW_HEIGHT + 8, 60, 26)
    grid_rect = pygame.Rect(WIDTH - 180, BATTLE_VIEW_HEIGHT + 8, 60, 26)
    speed_minus_rect = pygame.Rect(BATTLE_VIEW_WIDTH + PANEL_WIDTH - 140, BATTLE_VIEW_HEIGHT + 108, 22, 22)
    speed_plus_rect = pygame.Rect(BATTLE_VIEW_WIDTH + PANEL_WIDTH - 90, BATTLE_VIEW_HEIGHT + 108, 22, 22)

    while True:
        raw_dt = clock.tick(FPS) / 1000.0
        raw_dt = min(raw_dt, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            for fields in (red_fields, blue_fields):
                for v in fields.values():
                    # v may be a tuple (min,max) or a single InputField
                    if isinstance(v, tuple) or isinstance(v, list):
                        for fld in v:
                            fld.handle(event)
                    else:
                        v.handle(event)
            for field in common_fields.values():
                field.handle(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                for team_id, order_buttons in ((TEAM_RED, red_order_buttons), (TEAM_BLUE, blue_order_buttons)):
                    for order_name, rect in order_buttons.items():
                        if rect.collidepoint(event.pos):
                            if order_name in MANEUVER_COMMANDS:
                                sim._activate_maneuver(team_id, order_name)
                            elif order_name in STANCE_COMMANDS:
                                sim._activate_stance(team_id, order_name)
                            break
            if event.type == pygame.MOUSEBUTTONDOWN and apply_rect.collidepoint(event.pos):
                valid = True
                for config, fields in ((red_config, red_fields), (blue_config, blue_fields)):
                    new_values = {}
                    for _, key in PARAMETER_NAMES:
                        center = fields[key][0].number()
                        width = fields[key][1].number()
                        if center is None or width is None or width < 0:
                            valid = False
                            break
                        minimum = center - width / 2.0
                        maximum = center + width / 2.0
                        if minimum < 0.0 or minimum > maximum:
                            valid = False
                            break
                        if key == "armor" and maximum >= 1.0:
                            valid = False
                            break
                        new_values[key] = (minimum, maximum)
                    if valid:
                        config.values = new_values
                # Read common fields
                common_values = {}
                for key, field in common_fields.items():
                    value = field.number(integer=(key == "cell_size"))
                    if value is None or value <= 0:
                        valid = False
                    common_values[key] = value
                # Read per-team sizes from team panels
                red_size = red_fields["team_size"].number(integer=True)
                blue_size = blue_fields["team_size"].number(integer=True)
                if red_size is None or blue_size is None or red_size < 1 or blue_size < 1:
                    valid = False
                if valid:
                    # Update common config
                    common_config = CommonConfig(
                        red_team_size=red_size,
                        blue_team_size=blue_size,
                        **common_values,
                    )
                    sim.common_config = common_config
                    sim.reset()
                    status = "Applied. Simulation restarted."
                else:
                    status = "Invalid values: check min <= max."
            # Mouse clicks for other UI buttons
            if event.type == pygame.MOUSEBUTTONDOWN:
                # Pause/Play
                if pause_rect.collidepoint(event.pos):
                    paused = not paused

                # Reset simulation
                elif reset_rect.collidepoint(event.pos):
                    sim.reset()

                # Toggle grid
                elif grid_rect.collidepoint(event.pos):
                    show_grid = not show_grid

                # Speed controls (+ / -)
                elif speed_plus_rect.collidepoint(event.pos):
                    SIM_SPEED = min(4.0, SIM_SPEED * 1.25)
                elif speed_minus_rect.collidepoint(event.pos):
                    SIM_SPEED = max(0.25, SIM_SPEED / 1.25)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_r:
                    sim.reset()
                elif event.key == pygame.K_g:
                    show_grid = not show_grid
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    SIM_SPEED = min(4.0, SIM_SPEED * 1.25)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    SIM_SPEED = max(0.25, SIM_SPEED / 1.25)

        if not paused:
            sim.update(raw_dt * SIM_SPEED)

        draw_world(screen, sim, font, small_font, show_grid)
        # Draw simple HUD buttons over the world (screen coords)
        # Pause / Reset / Grid
        pygame.draw.rect(screen, (40, 45, 51), pause_rect)
        pygame.draw.rect(screen, (40, 45, 51), reset_rect)
        pygame.draw.rect(screen, (40, 45, 51), grid_rect)
        pygame.draw.rect(screen, (40, 45, 51), speed_minus_rect)
        pygame.draw.rect(screen, (40, 45, 51), speed_plus_rect)
        pygame.draw.rect(screen, WHITE if paused else (80, 85, 90), pause_rect, 1)
        pygame.draw.rect(screen, (80, 85, 90), reset_rect, 1)
        pygame.draw.rect(screen, (80, 85, 90), grid_rect, 1)
        pygame.draw.rect(screen, (80, 85, 90), speed_minus_rect, 1)
        pygame.draw.rect(screen, (80, 85, 90), speed_plus_rect, 1)
        # Labels
        screen.blit(small_font.render("PAUSE" if not paused else "PLAY", True, WHITE), (pause_rect.x + 8, pause_rect.y + 3))
        screen.blit(small_font.render("RESET", True, WHITE), (reset_rect.x + 12, reset_rect.y + 3))
        screen.blit(small_font.render("GRID", True, WHITE), (grid_rect.x + 18, grid_rect.y + 3))
        screen.blit(small_font.render("-", True, WHITE), (speed_minus_rect.x + 4, speed_minus_rect.y))
        screen.blit(small_font.render("+", True, WHITE), (speed_plus_rect.x + 4, speed_plus_rect.y))
        screen.fill((12, 14, 17), (0, 0, PANEL_WIDTH, BATTLE_VIEW_HEIGHT))
        screen.fill((12, 14, 17), (WIDTH - PANEL_WIDTH, 0, PANEL_WIDTH, BATTLE_VIEW_HEIGHT))
        draw_team_panel(
            screen,
            pygame.Rect(0, 0, PANEL_WIDTH, BATTLE_VIEW_HEIGHT),
            "RED ARMY",
            RED,
            red_fields,
            font,
            small_font,
            order_font,
            sim,
            TEAM_RED,
            red_order_buttons,
        )
        draw_team_panel(
            screen,
            pygame.Rect(WIDTH - PANEL_WIDTH, 0, PANEL_WIDTH, BATTLE_VIEW_HEIGHT),
            "BLUE ARMY",
            BLUE,
            blue_fields,
            font,
            small_font,
            order_font,
            sim,
            TEAM_BLUE,
            blue_order_buttons,
        )
        draw_common_panel(screen, common_fields, font, small_font, status)

        # Draw HUD buttons after panels so they remain visible and not covered
        pygame.draw.rect(screen, (40, 45, 51), pause_rect)
        pygame.draw.rect(screen, (40, 45, 51), reset_rect)
        pygame.draw.rect(screen, (40, 45, 51), grid_rect)
        pygame.draw.rect(screen, (40, 45, 51), speed_minus_rect)
        pygame.draw.rect(screen, (40, 45, 51), speed_plus_rect)
        pygame.draw.rect(screen, WHITE if paused else (80, 85, 90), pause_rect, 1)
        pygame.draw.rect(screen, (80, 85, 90), reset_rect, 1)
        pygame.draw.rect(screen, (80, 85, 90), grid_rect, 1)
        pygame.draw.rect(screen, (80, 85, 90), speed_minus_rect, 1)
        pygame.draw.rect(screen, (80, 85, 90), speed_plus_rect, 1)
        # Labels
        screen.blit(small_font.render("PAUSE" if not paused else "PLAY", True, WHITE), (pause_rect.x + 8, pause_rect.y + 3))
        screen.blit(small_font.render("RESET", True, WHITE), (reset_rect.x + 12, reset_rect.y + 3))
        screen.blit(small_font.render("GRID", True, WHITE), (grid_rect.x + 18, grid_rect.y + 3))
        screen.blit(small_font.render("-", True, WHITE), (speed_minus_rect.x + 4, speed_minus_rect.y))
        screen.blit(small_font.render("+", True, WHITE), (speed_plus_rect.x + 4, speed_plus_rect.y))

        speed_text = small_font.render(f"x{SIM_SPEED:.2f}  FPS {clock.get_fps():.0f}", True, GRAY)
        screen.blit(speed_text, (BATTLE_VIEW_WIDTH + PANEL_WIDTH - 115, BATTLE_VIEW_HEIGHT + 112))

        pygame.display.flip()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit(0)
