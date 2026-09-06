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

WORLD_WIDTH = 700
# Stretch vertical size by 1.3x for a taller world
WORLD_HEIGHT = int(425 * 1.3)
PANEL_WIDTH = 220
BOTTOM_PANEL_HEIGHT = 150
WIDTH = PANEL_WIDTH * 2 + WORLD_WIDTH
HEIGHT = WORLD_HEIGHT + BOTTOM_PANEL_HEIGHT
FPS = 60

TEAM_SIZE = 1000
TEAM_RED = 0
TEAM_BLUE = 1

TACTICAL_TURN_SECONDS = 1.0
ORDER_DURATION_TURNS = 10.0
MANEUVER_COMMANDS = (
    "LEFT_ADVANCE",
    "RIGHT_ADVANCE",
    "CENTER_BREAK",
    "ENCIRCLE",
)
STANCE_COMMANDS = ("CHARGE", "DEFENSE")
CENTER_BAND = 30.0
ENCIRCLE_OFFSET = 80.0
ENCIRCLE_STRENGTH = 1.2
ADVANCE_SPEED_MULTIPLIER = 1.10

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

CELL_SIZE = 24
SEPARATION_RADIUS = 10.0
MELEE_RANGE = 9.0

DEFAULT_PERCEPTION_RADIUS = 150.0
LOCAL_BALANCE_RADIUS = 42.0

SIM_SPEED = 1.0

PARAMETER_NAMES = (
    ("HP", "max_hp"),
    ("Speed", "speed"),
    ("Damage", "damage"),
    ("Attack", "attack_interval"),
    ("Perception", "perception"),
    ("Aggression", "aggression"),
    ("Courage", "courage"),
)

PARAMETER_STEPS = {
    "max_hp": 5.0,
    "speed": 1.0,
    "damage": 1.0,
    "attack_interval": 0.05,
    "perception": 5.0,
    "aggression": 0.05,
    "courage": 0.05,
}

@dataclass
class TeamConfig:
    values: dict


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
    "perception": (DEFAULT_PERCEPTION_RADIUS * 0.8, DEFAULT_PERCEPTION_RADIUS * 1.2),
    "aggression": (0.35, 1.0),
    "courage": (0.25, 1.0),
}


def clamp(value, low, high):
    return max(low, min(high, value))


def safe_normalize(v: pygame.Vector2) -> pygame.Vector2:
    if v.length_squared() < 1e-9:
        return pygame.Vector2()
    return v.normalize()


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
        "perception",
        "aggression",
        "courage",
        "target",
        "retarget_timer",
        "radius",
        "retreating",
        "forward",
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
        self.perception = random.uniform(*values["perception"])
        self.aggression = random.uniform(*values["aggression"])
        self.courage = random.uniform(*values["courage"])
        self.target = None
        self.retarget_timer = random.uniform(0.05, 0.35)
        self.radius = 2
        self.retreating = False

    def take_damage(self, amount: float, incoming_dir: pygame.Vector2 | None = None, incoming_multiplier: float = 1.0):
        if not self.alive:
            return

        total_multiplier = incoming_multiplier
        if incoming_dir is not None and incoming_dir.length_squared() > 1e-9:
            incoming_norm = safe_normalize(incoming_dir)
            forward = safe_normalize(self.forward)
            dot = forward.dot(incoming_norm)
            if dot > 0.5:
                damage_multiplier = 0.5
            elif dot < -0.5:
                damage_multiplier = 1.5
            else:
                damage_multiplier = 1.0
            total_multiplier *= damage_multiplier

        amount *= total_multiplier

        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            self.target = None
            self.vel.xy = 0, 0


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
        self.elapsed = 0.0
        self.reset()

    def _clear_team_orders(self):
        self.team_maneuver = {TEAM_RED: None, TEAM_BLUE: None}
        self.team_stance = {TEAM_RED: None, TEAM_BLUE: None}
        self.maneuver_turns_remaining = {TEAM_RED: 0.0, TEAM_BLUE: 0.0}
        self.stance_turns_remaining = {TEAM_RED: 0.0, TEAM_BLUE: 0.0}

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

    def _team_center_for(self, team: int):
        red_center, blue_center = self._team_centers()
        return red_center if team == TEAM_RED else blue_center

    def _enemy_center_for(self, team: int):
        red_center, blue_center = self._team_centers()
        return blue_center if team == TEAM_RED else red_center

    def _wing_for_agent(self, agent: "Agent", team_center: pygame.Vector2, team: int):
        if team == TEAM_RED:
            return "left" if agent.pos.y < team_center.y else "right"
        return "left" if agent.pos.y > team_center.y else "right"

    def _team_offensive_multiplier(self, team: int, is_outgoing: bool):
        stance = self.team_stance.get(team)
        if stance == "CHARGE":
            return 1.25 if is_outgoing else 1.20
        if stance == "DEFENSE":
            return 0.80 if is_outgoing else 0.75
        return 1.0

    def _order_vector_for_agent(self, agent: "Agent", red_center: pygame.Vector2, blue_center: pygame.Vector2):
        team = agent.team
        if agent.retreating:
            return pygame.Vector2()

        team_center = red_center if team == TEAM_RED else blue_center
        enemy_center = blue_center if team == TEAM_RED else red_center
        maneuver = self.team_maneuver.get(team)
        if maneuver is None:
            return pygame.Vector2()

        base_vec = safe_normalize(enemy_center - agent.pos)
        wing = self._wing_for_agent(agent, team_center, team)
        order_vec = pygame.Vector2()

        if maneuver == "LEFT_ADVANCE":
            if wing == "left":
                order_vec += base_vec * 1.6
        elif maneuver == "RIGHT_ADVANCE":
            if wing == "right":
                order_vec += base_vec * 1.6
        elif maneuver == "CENTER_BREAK":
            if abs(agent.pos.y - team_center.y) < CENTER_BAND:
                order_vec += base_vec * 1.8
                order_vec += base_vec * (0.4 + agent.aggression)
        elif maneuver == "ENCIRCLE":
            flank_y = -ENCIRCLE_OFFSET if agent.pos.y < team_center.y else ENCIRCLE_OFFSET
            flank_target = enemy_center + pygame.Vector2(0.0, flank_y)
            order_vec += safe_normalize(flank_target - agent.pos) * ENCIRCLE_STRENGTH

        return order_vec

    def _maneuver_speed_multiplier(self, agent: "Agent", red_center: pygame.Vector2, blue_center: pygame.Vector2):
        if agent.retreating:
            return 1.0

        maneuver = self.team_maneuver.get(agent.team)
        if maneuver is None:
            return 1.0

        team_center = red_center if agent.team == TEAM_RED else blue_center
        if maneuver == "CENTER_BREAK":
            applies = abs(agent.pos.y - team_center.y) < CENTER_BAND
        elif maneuver in ("LEFT_ADVANCE", "RIGHT_ADVANCE"):
            wing = self._wing_for_agent(agent, team_center, agent.team)
            applies = (maneuver == "LEFT_ADVANCE" and wing == "left") or (
                maneuver == "RIGHT_ADVANCE" and wing == "right"
            )
        else:
            applies = False

        return ADVANCE_SPEED_MULTIPLIER if applies else 1.0

    def _effective_damage_multiplier(self, team: int, is_outgoing: bool):
        return self._team_offensive_multiplier(team, is_outgoing)

    def reset(self):
        self.grid = SpatialGrid(self.common_config.cell_size)
        self.agents.clear()
        self.dead_positions.clear()
        self._clear_team_orders()
        self.elapsed = 0.0
        # Two broad formations. Jitter prevents perfectly rigid initial lines.
        self._spawn_army(TEAM_RED, center_x=130, center_y=WORLD_HEIGHT / 2, facing=1, team_size=self.common_config.red_team_size)
        self._spawn_army(TEAM_BLUE, center_x=WORLD_WIDTH - 130, center_y=WORLD_HEIGHT / 2, facing=-1, team_size=self.common_config.blue_team_size)
        self.grid.rebuild(self.agents)

    def _spawn_army(self, team, center_x, center_y, facing, team_size):
        cols = max(5, min(25, math.ceil(math.sqrt(team_size))))
        rows = math.ceil(team_size / cols)
        # Increase spacing to avoid overly dense initial clusters
        spacing_x = 6.0
        spacing_y = 6.0
        count = 0

        for row in range(rows):
            for col in range(cols):
                if count >= team_size:
                    return

                # Depth extends away from the enemy, width along Y.
                x = center_x - facing * (row - rows / 2) * spacing_x
                y = center_y + (col - cols / 2) * spacing_y
                # smaller jitter so formation is more regular
                x += random.uniform(-0.5, 0.5)
                y += random.uniform(-0.5, 0.5)
                config = self.red_config if team == TEAM_RED else self.blue_config
                self.agents.append(Agent(team, x, y, config))
                count += 1

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
        red_center, blue_center = self._team_centers()

        for agent in self.agents:
            if not agent.alive:
                continue

            agent.attack_cooldown = max(0.0, agent.attack_cooldown - dt)
            agent.retarget_timer -= dt

            if agent.retarget_timer <= 0.0:
                agent.target = self._acquire_target(agent)
                # Stagger retargeting so all 2000 agents do not search together.
                agent.retarget_timer = random.uniform(0.18, 0.42)

            local_allies, local_enemies = self._local_balance(agent)
            move = self._movement_vector(agent, red_center, blue_center, local_allies, local_enemies)

            if move.length_squared() > 1e-9:
                speed_multiplier = self._maneuver_speed_multiplier(agent, red_center, blue_center)
                desired = safe_normalize(move) * agent.speed * speed_multiplier
                # Smooth acceleration instead of instant direction changes.
                response = clamp(7.0 * dt, 0.0, 1.0)
                agent.vel = agent.vel.lerp(desired, response)
            else:
                agent.vel *= max(0.0, 1.0 - 8.0 * dt)

            if agent.vel.length_squared() > 1e-6:
                agent.forward = agent.vel.normalize()

            agent.pos += agent.vel * dt
            agent.pos.x = clamp(agent.pos.x, 8, WORLD_WIDTH - 8)
            agent.pos.y = clamp(agent.pos.y, 8, WORLD_HEIGHT - 8)

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
            combined_dir = pygame.Vector2()
            multiplier_weight = 0.0
            for attacker, incoming_dir, incoming_multiplier in hits:
                final_damage = attacker.damage * random.uniform(0.82, 1.18) * self._team_offensive_multiplier(attacker.team, True)
                total_damage += final_damage
                if incoming_dir.length_squared() > 1e-9:
                    combined_dir += incoming_dir * final_damage
                    multiplier_weight += incoming_multiplier * final_damage
                attacker.attack_cooldown = attacker.attack_interval

            if total_damage <= 0.0:
                continue

            if combined_dir.length_squared() > 1e-9:
                incoming_dir = safe_normalize(combined_dir)
                combined_multiplier = multiplier_weight / total_damage if total_damage > 0.0 else 1.0
            else:
                incoming_dir = None
                combined_multiplier = 1.0

            target.take_damage(total_damage, incoming_dir, incoming_multiplier=combined_multiplier)

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

        red_center = pygame.Vector2(rx / rc, ry / rc) if rc else pygame.Vector2(WORLD_WIDTH * 0.25, WORLD_HEIGHT / 2)
        blue_center = pygame.Vector2(bx / bc, by / bc) if bc else pygame.Vector2(WORLD_WIDTH * 0.75, WORLD_HEIGHT / 2)
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

    def _local_balance(self, agent: Agent):
        allies = 0
        enemies = 0
        local_radius = self.common_config.local_balance_radius
        r2 = local_radius * local_radius
        for other in self.grid.nearby(agent.pos, local_radius):
            if other is agent or not other.alive:
                continue
            if agent.pos.distance_squared_to(other.pos) > r2:
                continue
            if other.team == agent.team:
                allies += 1
            else:
                enemies += 1
        return allies, enemies

    def _movement_vector(self, agent, red_center, blue_center, local_allies, local_enemies):
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
        else:
            strategic_target = blue_center if agent.team == TEAM_RED else red_center
            target_vec = safe_normalize(strategic_target - agent.pos)

        # Low-courage agents retreat if locally overwhelmed.
        hp_ratio = agent.hp / agent.max_hp
        outnumbered = local_enemies > max(2, local_allies * 1.55)
        badly_hurt = hp_ratio < (0.18 + (1.0 - agent.courage) * 0.22)
        retreat = outnumbered and agent.courage < 0.55 or badly_hurt

        if retreat:
            if agent.target is not None and agent.target.alive:
                target_vec = safe_normalize(agent.pos - agent.target.pos)
            else:
                home_x = 65 if agent.team == TEAM_RED else WORLD_WIDTH - 65
                target_vec = safe_normalize(pygame.Vector2(home_x, WORLD_HEIGHT / 2) - agent.pos)

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
            + self._order_vector_for_agent(agent, red_center, blue_center)
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
    start_y = 112

    for index, (label, key) in enumerate(PARAMETER_NAMES):
        y = start_y + index * 29
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

    screen.blit(small_font.render("ACTIVE ORDERS", True, team_color), (rect.x + 8, rect.y + 328))
    screen.blit(small_font.render(f"MOVE   {maneuver_name} [{maneuver_remaining:.1f}]", True, WHITE), (rect.x + 8, rect.y + 344))
    screen.blit(small_font.render(f"STANCE {stance_name} [{stance_remaining:.1f}]", True, WHITE), (rect.x + 8, rect.y + 360))


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

    pygame.draw.line(screen, (60, 65, 70), (rect.x + 8, rect.y + 320), (rect.right - 8, rect.y + 320), 1)
    screen.blit(small_font.render("ORDERS", True, GRAY), (rect.x + 8, rect.y + 380))
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
    rect = pygame.Rect(0, WORLD_HEIGHT, WIDTH, BOTTOM_PANEL_HEIGHT)
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
    world = pygame.Surface((WORLD_WIDTH, WORLD_HEIGHT))
    world.fill(BACKGROUND)

    if show_grid:
        for x in range(0, WORLD_WIDTH, sim.common_config.cell_size):
            pygame.draw.line(world, GRID_COLOR, (x, 0), (x, WORLD_HEIGHT), 1)
        for y in range(0, WORLD_HEIGHT, sim.common_config.cell_size):
            pygame.draw.line(world, GRID_COLOR, (0, y), (WORLD_WIDTH, y), 1)

    # Dead agents are drawn first and dimmer.
    for a in sim.agents:
        if a.alive:
            continue
        color = RED_DARK if a.team == TEAM_RED else BLUE_DARK
        pygame.draw.circle(world, color, (int(a.pos.x), int(a.pos.y)), max(1, a.radius))

    # Living agents.
    for a in sim.agents:
        if not a.alive:
            continue
        # Choose color: different when retreating
        if a.retreating:
            color = RED_RETREAT if a.team == TEAM_RED else BLUE_RETREAT
        else:
            color = RED if a.team == TEAM_RED else BLUE
        # Draw agent as a triangle pointing in velocity direction.
        # If velocity is very small, fall back to facing toward enemy side.
        if a.forward.length_squared() > 1e-6:
            orient = a.forward.normalize()
        else:
            orient = pygame.Vector2(1, 0) if a.team == TEAM_RED else pygame.Vector2(-1, 0)

        # Triangle size based on composite strength across traits (3 tiers)
        cfg = sim.red_config if a.team == TEAM_RED else sim.blue_config
        keys = [
            "max_hp",
            "speed",
            "damage",
            "attack_interval",
            "perception",
            "aggression",
            "courage",
        ]
        norms = []
        for k in keys:
            v = getattr(a, k)
            rmin, rmax = cfg.values[k]
            if k == "attack_interval":
                # lower is better -> invert
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
        # map to three tiers
        if strength >= 0.66:
            tier_scale = 1.6
        elif strength >= 0.33:
            tier_scale = 1.0
        else:
            tier_scale = 0.6
        base = max(1, int(a.radius * 3 * 0.5))
        size = max(1, int(base * tier_scale))
        tip = a.pos + orient * (size * 0.9)
        left = a.pos + orient.rotate(140) * size
        right = a.pos + orient.rotate(-140) * size
        points = [(int(tip.x), int(tip.y)), (int(left.x), int(left.y)), (int(right.x), int(right.y))]
        pygame.draw.polygon(world, color, points)

    red, blue = sim.alive_counts()
    total = red + blue

    # HUD
    pygame.draw.rect(world, (10, 12, 14), (0, 0, WORLD_WIDTH, 42))
    world.blit(font.render(f"RED {red:4d}", True, RED), (12, 8))
    world.blit(font.render(f"BLUE {blue:4d}", True, BLUE), (140, 8))
    total_initial = sim.common_config.red_team_size + sim.common_config.blue_team_size
    world.blit(small_font.render(f"Alive {total:4d} / {total_initial}", True, WHITE), (275, 14))
    world.blit(small_font.render(f"Time {sim.elapsed:6.1f}s", True, WHITE), (440, 14))

    controls = "SPACE pause   R reset   G grid   +/- simulation speed   ESC quit"
    world.blit(small_font.render(controls, True, GRAY), (12, WORLD_HEIGHT - 22))

    if red == 0 or blue == 0:
        winner = "BLUE WINS" if red == 0 and blue > 0 else "RED WINS" if blue == 0 and red > 0 else "DRAW"
        text = font.render(winner + "   [R] restart", True, WHITE)
        rect = text.get_rect(center=(WORLD_WIDTH // 2, 70))
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
            (12, WORLD_HEIGHT + 62, 120, 25),
            common_config.cell_size,
            1,
        ),
        "separation_radius": InputField(
            (162, WORLD_HEIGHT + 62, 120, 25),
            common_config.separation_radius,
            1.0,
        ),
        "melee_range": InputField(
            (312, WORLD_HEIGHT + 62, 120, 25),
            common_config.melee_range,
            1.0,
        ),
        "local_balance_radius": InputField(
            (462, WORLD_HEIGHT + 62, 120, 25),
            common_config.local_balance_radius,
            5.0,
        ),
    }
    sim = BattleSimulation(red_config, blue_config, common_config)
    paused = False
    show_grid = False
    status = ""
    red_order_buttons = {
        name: pygame.Rect(12 + (index % 2) * 98, 397 + (index // 2) * 25, 96, 22)
        for index, name in enumerate(MANEUVER_COMMANDS + STANCE_COMMANDS)
    }
    blue_order_buttons = {
        name: pygame.Rect(WIDTH - PANEL_WIDTH + 12 + (index % 2) * 98, 397 + (index // 2) * 25, 96, 22)
        for index, name in enumerate(MANEUVER_COMMANDS + STANCE_COMMANDS)
    }
    apply_rect = pygame.Rect(WIDTH - 135, WORLD_HEIGHT + 38, 120, 30)
    # UI button rects (moved into common panel at bottom, right-aligned)
    pause_rect = pygame.Rect(WIDTH - 320, WORLD_HEIGHT + 8, 60, 26)
    reset_rect = pygame.Rect(WIDTH - 250, WORLD_HEIGHT + 8, 60, 26)
    grid_rect = pygame.Rect(WIDTH - 180, WORLD_HEIGHT + 8, 60, 26)
    speed_minus_rect = pygame.Rect(WORLD_WIDTH + PANEL_WIDTH - 140, WORLD_HEIGHT + 108, 22, 22)
    speed_plus_rect = pygame.Rect(WORLD_WIDTH + PANEL_WIDTH - 90, WORLD_HEIGHT + 108, 22, 22)

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
                        if minimum > maximum:
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
        screen.fill((12, 14, 17), (0, 0, PANEL_WIDTH, WORLD_HEIGHT))
        screen.fill((12, 14, 17), (WIDTH - PANEL_WIDTH, 0, PANEL_WIDTH, WORLD_HEIGHT))
        draw_team_panel(
            screen,
            pygame.Rect(0, 0, PANEL_WIDTH, WORLD_HEIGHT),
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
            pygame.Rect(WIDTH - PANEL_WIDTH, 0, PANEL_WIDTH, WORLD_HEIGHT),
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
        screen.blit(speed_text, (WORLD_WIDTH + PANEL_WIDTH - 115, WORLD_HEIGHT + 112))

        pygame.display.flip()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit(0)
