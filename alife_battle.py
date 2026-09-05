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
    )

    def __init__(self, team: int, x: float, y: float, config: TeamConfig):
        self.team = team
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2()
        self.alive = True

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
        self.radius = 1
        self.retreating = False

    def take_damage(self, amount: float):
        if not self.alive:
            return
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
        # obstacle cells stored as set of (cell_x, cell_y)
        self.obstacle_cells = set()
        self.elapsed = 0.0
        self.reset()

    def reset(self):
        self.grid = SpatialGrid(self.common_config.cell_size)
        self.agents.clear()
        self.dead_positions.clear()
        self.obstacle_cells.clear()
        # generate clustered obstacles on grid cells
        cell_size = self.common_config.cell_size
        cols = max(3, WORLD_WIDTH // cell_size)
        rows = max(3, WORLD_HEIGHT // cell_size)
        area_scale = (WORLD_WIDTH * WORLD_HEIGHT) / (700.0 * 425.0)
        num_clusters = max(3, int(6 * area_scale))
        # prohibited spawn x ranges around team centers
        left_spawn_x = 130
        right_spawn_x = WORLD_WIDTH - 130
        # reduce spawn margin to make finding seed cells easier
        spawn_margin = 5 * cell_size
        for _ in range(num_clusters):
            cluster_size = random.randint(3, 12)
            # find seed cell not in spawn margins; give up after attempts and skip cluster
            seed_found = False
            for _attempt in range(200):
                cx = random.randint(1, cols - 2)
                cy = random.randint(1, rows - 2)
                px = cx * cell_size + cell_size / 2
                if abs(px - left_spawn_x) < spawn_margin or abs(px - right_spawn_x) < spawn_margin:
                    continue
                if (cx, cy) in self.obstacle_cells:
                    continue
                # accept seed
                seed_found = True
                break
            if not seed_found:
                # couldn't find a valid seed within attempts; skip this cluster
                continue

            cluster = {(cx, cy)}
            self.obstacle_cells.add((cx, cy))
            # grow cluster with bounded attempts to avoid infinite loops
            max_growth_attempts = cluster_size * 50
            growth_attempts = 0
            while (
                len(cluster) < cluster_size
                and growth_attempts < max_growth_attempts
            ):
                growth_attempts += 1
                bx, by = random.choice(list(cluster))
                # 4-neighbors
                nbors = [(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)]
                nx, ny = random.choice(nbors)
                if nx <= 0 or nx >= cols - 1 or ny <= 0 or ny >= rows - 1:
                    continue
                if (nx, ny) in self.obstacle_cells:
                    continue
                # avoid spawn margins
                px = nx * cell_size + cell_size / 2
                if abs(px - left_spawn_x) < spawn_margin or abs(px - right_spawn_x) < spawn_margin:
                    continue
                cluster.add((nx, ny))
                self.obstacle_cells.add((nx, ny))
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
                # avoid obstacle cells by nudging y until free
                cell_x = int(x // self.common_config.cell_size)
                cell_y = int(y // self.common_config.cell_size)
                safe = ((cell_x, cell_y) not in self.obstacle_cells)
                attempts = 0
                while not safe and attempts < 6:
                    y += spacing_y
                    cell_y = int(y // self.common_config.cell_size)
                    safe = ((cell_x, cell_y) not in self.obstacle_cells)
                    attempts += 1
                if not safe:
                    # try nudging x instead
                    attempts = 0
                    safe = False
                    while not safe and attempts < 6:
                        x += spacing_x
                        cell_x = int(x // self.common_config.cell_size)
                        safe = ((cell_x, cell_y) not in self.obstacle_cells)
                        attempts += 1
                if not safe:
                    # give up on this cell, skip placing here
                    continue
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
                desired = safe_normalize(move) * agent.speed
                # Smooth acceleration instead of instant direction changes.
                response = clamp(7.0 * dt, 0.0, 1.0)
                agent.vel = agent.vel.lerp(desired, response)
            else:
                agent.vel *= max(0.0, 1.0 - 8.0 * dt)

            # Attempt movement but prevent entering obstacle cells
            desired = agent.pos + agent.vel * dt
            ncell = self.grid.key(desired)
            if ncell in self.obstacle_cells:
                # try X-only then Y-only movement
                x_only = pygame.Vector2(agent.pos.x + agent.vel.x * dt, agent.pos.y)
                y_only = pygame.Vector2(agent.pos.x, agent.pos.y + agent.vel.y * dt)
                if self.grid.key(x_only) not in self.obstacle_cells:
                    agent.pos.x = clamp(x_only.x, 8, WORLD_WIDTH - 8)
                elif self.grid.key(y_only) not in self.obstacle_cells:
                    agent.pos.y = clamp(y_only.y, 8, WORLD_HEIGHT - 8)
                else:
                    # blocked; damp velocity
                    agent.vel *= 0.1
            else:
                agent.pos = desired
                agent.pos.x = clamp(agent.pos.x, 8, WORLD_WIDTH - 8)
                agent.pos.y = clamp(agent.pos.y, 8, WORLD_HEIGHT - 8)

            self._try_attack(agent)

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
        )

    def _try_attack(self, agent: Agent):
        target = agent.target
        if target is None or not target.alive:
            return

        attack_range = self.common_config.melee_range + agent.radius + target.radius
        if agent.pos.distance_squared_to(target.pos) <= attack_range * attack_range:
            agent.vel *= 0.55
            if agent.attack_cooldown <= 0.0:
                # Damage varies slightly per strike.
                target.take_damage(agent.damage * random.uniform(0.82, 1.18))
                agent.attack_cooldown = agent.attack_interval


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
    # Move parameters down to avoid overlapping the team-size field and headers
    start_y = 82

    for index, (label, key) in enumerate(PARAMETER_NAMES):
        y = start_y + index * 38
        step = PARAMETER_STEPS[key]

        # display as center and width instead of min/max
        vmin, vmax = config.values[key]
        center = (vmin + vmax) / 2.0
        width = max(0.0, vmax - vmin)
        fields[key] = (
            InputField(
                (x + 8, y, 92, 24),
                format_value(center),
                step,
            ),
            InputField(
                (x + 112, y, 92, 24),
                format_value(width),
                step,
            ),
        )

    return fields


def draw_team_panel(screen, rect, title, color, fields, font, small_font):
    pygame.draw.rect(screen, (17, 20, 24), rect)
    pygame.draw.line(screen, color, rect.topleft, rect.topright, 3)
    screen.blit(font.render(title, True, color), (rect.x + 8, rect.y + 12))
    # Label for the min/max columns, placed below the team-size field
    screen.blit(small_font.render("center       width", True, GRAY), (rect.x + 8, rect.y + 65))
    for label, key in PARAMETER_NAMES:
        left, right = fields[key]
        y = left.rect.y
        screen.blit(small_font.render(label, True, WHITE), (rect.x + 8, y + 27))
        for field in (left, right):
            field.draw(screen, small_font, color)
    # Optional per-team size field
    team_size_field = fields.get("team_size")
    if team_size_field is not None:
        # Team size label sits under the title
        screen.blit(small_font.render("Team size", True, WHITE), (rect.x + 8, rect.y + 40))
        team_size_field.draw(screen, small_font, color)

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

    # draw obstacles as filled grid cells
    cell_size = sim.common_config.cell_size
    for cx, cy in getattr(sim, "obstacle_cells", set()):
        rx = cx * cell_size
        ry = cy * cell_size
        pygame.draw.rect(world, (60, 66, 72), (rx, ry, cell_size, cell_size))

    # Dead agents are drawn first and dimmer.
    for a in sim.agents:
        if a.alive:
            continue
        color = RED_DARK if a.team == TEAM_RED else BLUE_DARK
        pygame.draw.circle(world, color, (int(a.pos.x), int(a.pos.y)), 1)

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
        if a.vel.length_squared() > 1e-6:
            orient = a.vel.normalize()
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

    red_config = TeamConfig(dict(DEFAULT_TEAM_VALUES))
    blue_config = TeamConfig(dict(DEFAULT_TEAM_VALUES))
    common_config = CommonConfig()
    red_fields = create_team_fields(0, red_config, small_font)
    blue_fields = create_team_fields(WIDTH - PANEL_WIDTH, blue_config, small_font)
    # Team-size fields per team (moved from common panel)
    red_team_size_field = InputField((8, 40, 120, 24), common_config.red_team_size, 1)
    blue_team_size_field = InputField((WIDTH - PANEL_WIDTH + 8, 40, 120, 24), common_config.blue_team_size, 1)
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
        draw_team_panel(screen, pygame.Rect(0, 0, PANEL_WIDTH, WORLD_HEIGHT), "RED ARMY", RED, red_fields, font, small_font)
        draw_team_panel(screen, pygame.Rect(WIDTH - PANEL_WIDTH, 0, PANEL_WIDTH, WORLD_HEIGHT), "BLUE ARMY", BLUE, blue_fields, font, small_font)
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
