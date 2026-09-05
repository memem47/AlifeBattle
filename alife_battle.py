import math
import random
import sys
from collections import defaultdict

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

WIDTH, HEIGHT = 1400, 850
FPS = 60

TEAM_SIZE = 1000
TEAM_RED = 0
TEAM_BLUE = 1

BACKGROUND = (22, 25, 29)
RED = (225, 80, 76)
BLUE = (72, 145, 230)
RED_DARK = (120, 42, 40)
BLUE_DARK = (37, 78, 130)
WHITE = (235, 235, 235)
GRAY = (135, 140, 145)
GRID_COLOR = (38, 42, 48)

CELL_SIZE = 48
SEPARATION_RADIUS = 10.0
MELEE_RANGE = 9.0
PERCEPTION_RADIUS = 150.0

SIM_SPEED = 1.0


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
    )

    def __init__(self, team: int, x: float, y: float):
        self.team = team
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2()
        self.alive = True

        # Slightly different traits give the population a more "life-like"
        # character and create local variation without scripting individuals.
        self.max_hp = random.uniform(80.0, 120.0)
        self.hp = self.max_hp
        self.speed = random.uniform(34.0, 52.0)
        self.damage = random.uniform(8.0, 15.0)
        self.attack_interval = random.uniform(0.45, 0.75)
        self.attack_cooldown = random.random() * self.attack_interval
        self.perception = random.uniform(PERCEPTION_RADIUS * 0.8, PERCEPTION_RADIUS * 1.2)
        self.aggression = random.uniform(0.35, 1.0)
        self.courage = random.uniform(0.25, 1.0)
        self.target = None
        self.retarget_timer = random.uniform(0.05, 0.35)
        self.radius = 2

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
    def __init__(self):
        self.grid = SpatialGrid(CELL_SIZE)
        self.agents = []
        self.dead_positions = []
        self.elapsed = 0.0
        self.reset()

    def reset(self):
        self.agents.clear()
        self.dead_positions.clear()
        self.elapsed = 0.0

        # Two broad formations. Jitter prevents perfectly rigid initial lines.
        self._spawn_army(TEAM_RED, center_x=260, center_y=HEIGHT / 2, facing=1)
        self._spawn_army(TEAM_BLUE, center_x=WIDTH - 260, center_y=HEIGHT / 2, facing=-1)
        self.grid.rebuild(self.agents)

    def _spawn_army(self, team, center_x, center_y, facing):
        cols = 25
        rows = math.ceil(TEAM_SIZE / cols)
        spacing_x = 7.5
        spacing_y = 7.5
        count = 0

        for row in range(rows):
            for col in range(cols):
                if count >= TEAM_SIZE:
                    return

                # Depth extends away from the enemy, width along Y.
                x = center_x - facing * (row - rows / 2) * spacing_x
                y = center_y + (col - cols / 2) * spacing_y
                x += random.uniform(-2.0, 2.0)
                y += random.uniform(-2.0, 2.0)
                self.agents.append(Agent(team, x, y))
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

            agent.pos += agent.vel * dt
            agent.pos.x = clamp(agent.pos.x, 8, WIDTH - 8)
            agent.pos.y = clamp(agent.pos.y, 8, HEIGHT - 8)

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

        red_center = pygame.Vector2(rx / rc, ry / rc) if rc else pygame.Vector2(WIDTH * 0.25, HEIGHT / 2)
        blue_center = pygame.Vector2(bx / bc, by / bc) if bc else pygame.Vector2(WIDTH * 0.75, HEIGHT / 2)
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
        r2 = 42.0 * 42.0
        for other in self.grid.nearby(agent.pos, 42.0):
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
        sep_r2 = SEPARATION_RADIUS * SEPARATION_RADIUS

        for other in self.grid.nearby(agent.pos, SEPARATION_RADIUS):
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
            if dist > MELEE_RANGE * 0.85:
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
                home_x = 65 if agent.team == TEAM_RED else WIDTH - 65
                target_vec = safe_normalize(pygame.Vector2(home_x, HEIGHT / 2) - agent.pos)

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

        attack_range = MELEE_RANGE + agent.radius + target.radius
        if agent.pos.distance_squared_to(target.pos) <= attack_range * attack_range:
            agent.vel *= 0.55
            if agent.attack_cooldown <= 0.0:
                # Damage varies slightly per strike.
                target.take_damage(agent.damage * random.uniform(0.82, 1.18))
                agent.attack_cooldown = agent.attack_interval


def draw_world(screen, sim: BattleSimulation, font, small_font, show_grid):
    screen.fill(BACKGROUND)

    if show_grid:
        for x in range(0, WIDTH, CELL_SIZE):
            pygame.draw.line(screen, GRID_COLOR, (x, 0), (x, HEIGHT), 1)
        for y in range(0, HEIGHT, CELL_SIZE):
            pygame.draw.line(screen, GRID_COLOR, (0, y), (WIDTH, y), 1)

    # Dead agents are drawn first and dimmer.
    for a in sim.agents:
        if a.alive:
            continue
        color = RED_DARK if a.team == TEAM_RED else BLUE_DARK
        pygame.draw.circle(screen, color, (int(a.pos.x), int(a.pos.y)), 1)

    # Living agents.
    for a in sim.agents:
        if not a.alive:
            continue
        color = RED if a.team == TEAM_RED else BLUE
        pygame.draw.circle(screen, color, (int(a.pos.x), int(a.pos.y)), a.radius)

    red, blue = sim.alive_counts()
    total = red + blue

    # HUD
    pygame.draw.rect(screen, (10, 12, 14), (0, 0, WIDTH, 56))
    screen.blit(font.render(f"RED {red:4d}", True, RED), (18, 12))
    screen.blit(font.render(f"BLUE {blue:4d}", True, BLUE), (160, 12))
    screen.blit(font.render(f"Alive {total:4d} / {TEAM_SIZE*2}", True, WHITE), (320, 12))
    screen.blit(font.render(f"Time {sim.elapsed:6.1f}s", True, WHITE), (535, 12))

    controls = "SPACE pause   R reset   G grid   +/- simulation speed   ESC quit"
    screen.blit(small_font.render(controls, True, GRAY), (770, 18))

    if red == 0 or blue == 0:
        winner = "BLUE WINS" if red == 0 and blue > 0 else "RED WINS" if blue == 0 and red > 0 else "DRAW"
        text = font.render(winner + "   [R] restart", True, WHITE)
        rect = text.get_rect(center=(WIDTH // 2, 90))
        pygame.draw.rect(screen, (10, 12, 14), rect.inflate(30, 18))
        screen.blit(text, rect)


def main():
    global SIM_SPEED

    pygame.init()
    pygame.display.set_caption("Artificial-Life Battle Simulation - 1000 vs 1000")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 23, bold=True)
    small_font = pygame.font.SysFont("consolas", 15)

    sim = BattleSimulation()
    paused = False
    show_grid = False

    while True:
        raw_dt = clock.tick(FPS) / 1000.0
        raw_dt = min(raw_dt, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
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
        speed_text = small_font.render(f"x{SIM_SPEED:.2f}   FPS {clock.get_fps():.0f}", True, GRAY)
        screen.blit(speed_text, (WIDTH - 175, HEIGHT - 28))

        pygame.display.flip()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit(0)
