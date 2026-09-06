import pygame
import pytest

import alife_battle as simmod


def _make_sim():
    red_cfg = simmod.TeamConfig({
        "max_hp": (80.0, 80.0),
        "speed": (30.0, 30.0),
        "damage": (10.0, 10.0),
        "attack_interval": (0.5, 0.5),
        "armor": (0.0, 0.0),
        "perception": (150.0, 150.0),
        "aggression": (1.0, 1.0),
        "courage": (1.0, 1.0),
    })
    blue_cfg = simmod.TeamConfig({
        "max_hp": (80.0, 80.0),
        "speed": (30.0, 30.0),
        "damage": (10.0, 10.0),
        "attack_interval": (0.5, 0.5),
        "armor": (0.0, 0.0),
        "perception": (150.0, 150.0),
        "aggression": (1.0, 1.0),
        "courage": (1.0, 1.0),
    })
    common = simmod.CommonConfig(
        red_team_size=2,
        blue_team_size=2,
        cell_size=24,
        separation_radius=10.0,
        melee_range=9.0,
        local_balance_radius=42.0,
    )
    return simmod.BattleSimulation(red_cfg, blue_cfg, common), red_cfg, blue_cfg, common


def test_attacks_are_resolved_simultaneously():
    red_cfg = simmod.TeamConfig({
        "max_hp": (40.0, 40.0),
        "speed": (10.0, 10.0),
        "damage": (100.0, 100.0),
        "attack_interval": (0.1, 0.1),
        "armor": (0.0, 0.0),
        "perception": (150.0, 150.0),
        "aggression": (1.0, 1.0),
        "courage": (1.0, 1.0),
    })
    blue_cfg = simmod.TeamConfig({
        "max_hp": (40.0, 40.0),
        "speed": (10.0, 10.0),
        "damage": (100.0, 100.0),
        "attack_interval": (0.1, 0.1),
        "armor": (0.0, 0.0),
        "perception": (150.0, 150.0),
        "aggression": (1.0, 1.0),
        "courage": (1.0, 1.0),
    })
    common = simmod.CommonConfig(
        red_team_size=2,
        blue_team_size=2,
        cell_size=24,
        separation_radius=10.0,
        melee_range=9.0,
        local_balance_radius=42.0,
    )

    red = simmod.Agent(simmod.TEAM_RED, 50.0, 50.0, red_cfg)
    blue = simmod.Agent(simmod.TEAM_BLUE, 60.0, 50.0, blue_cfg)
    red.max_hp = 40.0
    red.hp = 40.0
    red.damage = 100.0
    red.attack_interval = 0.1
    red.attack_cooldown = 0.0
    red.target = blue
    red.forward = pygame.Vector2(1.0, 0.0)

    blue.max_hp = 40.0
    blue.hp = 40.0
    blue.damage = 100.0
    blue.attack_interval = 0.1
    blue.attack_cooldown = 0.0
    blue.target = red
    blue.forward = pygame.Vector2(-1.0, 0.0)

    sim = simmod.BattleSimulation(red_cfg, blue_cfg, common)
    sim.agents = [red, blue]
    sim.grid.rebuild(sim.agents)

    sim.update(0.016)

    assert red.hp <= 0 and blue.hp <= 0


def test_maneuver_speed_rebalances_main_and_support_forces():
    sim, _, _, _ = _make_sim()

    red_center = pygame.Vector2(150.0, 200.0)
    blue_center = pygame.Vector2(550.0, 200.0)

    left_agent = simmod.Agent(simmod.TEAM_RED, 110.0, 100.0, sim.red_config)
    right_agent = simmod.Agent(simmod.TEAM_RED, 110.0, 300.0, sim.red_config)
    center_agent = simmod.Agent(simmod.TEAM_RED, 150.0, 200.0, sim.red_config)

    sim.team_maneuver[simmod.TEAM_RED] = "LEFT_ADVANCE"
    assert sim._maneuver_speed_multiplier(left_agent, red_center, blue_center, retreating=False) == simmod.MAIN_ATTACK_SPEED_MULTIPLIER
    assert sim._maneuver_speed_multiplier(right_agent, red_center, blue_center, retreating=False) == simmod.SUPPORT_SPEED_MULTIPLIER

    sim.team_maneuver[simmod.TEAM_RED] = "RIGHT_ADVANCE"
    assert sim._maneuver_speed_multiplier(right_agent, red_center, blue_center, retreating=False) == simmod.MAIN_ATTACK_SPEED_MULTIPLIER
    assert sim._maneuver_speed_multiplier(left_agent, red_center, blue_center, retreating=False) == simmod.SUPPORT_SPEED_MULTIPLIER

    sim.team_maneuver[simmod.TEAM_RED] = "CENTER_BREAK"
    assert sim._maneuver_speed_multiplier(center_agent, red_center, blue_center, retreating=False) == simmod.MAIN_ATTACK_SPEED_MULTIPLIER
    assert sim._maneuver_speed_multiplier(left_agent, red_center, blue_center, retreating=False) == simmod.SUPPORT_SPEED_MULTIPLIER

    sim.team_maneuver[simmod.TEAM_RED] = "ENCIRCLE"
    assert sim._maneuver_speed_multiplier(center_agent, red_center, blue_center, retreating=False) == simmod.ENCIRCLE_CENTER_SPEED_MULTIPLIER
    assert sim._maneuver_speed_multiplier(left_agent, red_center, blue_center, retreating=False) == simmod.ENCIRCLE_FLANK_SPEED_MULTIPLIER

    left_agent.retreating = True
    assert sim._maneuver_speed_multiplier(left_agent, red_center, blue_center, retreating=True) == 1.0


def test_encircle_order_vector_stays_on_flanks_and_not_center():
    sim, _, _, _ = _make_sim()
    red_center = pygame.Vector2(150.0, 200.0)
    blue_center = pygame.Vector2(550.0, 200.0)
    center_agent = simmod.Agent(simmod.TEAM_RED, 150.0, 200.0, sim.red_config)
    upper_agent = simmod.Agent(simmod.TEAM_RED, 150.0, 120.0, sim.red_config)
    lower_agent = simmod.Agent(simmod.TEAM_RED, 150.0, 280.0, sim.red_config)

    sim.team_maneuver[simmod.TEAM_RED] = "ENCIRCLE"
    center_vec = sim._order_vector_for_agent(center_agent, red_center, blue_center)
    upper_vec = sim._order_vector_for_agent(upper_agent, red_center, blue_center)
    lower_vec = sim._order_vector_for_agent(lower_agent, red_center, blue_center)

    assert center_vec.length_squared() == 0.0
    assert upper_vec.x > 0.0
    assert lower_vec.x > 0.0
    assert upper_vec.y <= 0.0
    assert lower_vec.y >= 0.0


def test_red_blue_maneuver_rules_are_symmetric():
    sim, _, _, _ = _make_sim()
    red_center = pygame.Vector2(150.0, 200.0)
    blue_center = pygame.Vector2(550.0, 200.0)

    red_left = simmod.Agent(simmod.TEAM_RED, 110.0, 180.0, sim.red_config)
    red_right = simmod.Agent(simmod.TEAM_RED, 110.0, 220.0, sim.red_config)
    blue_upper = simmod.Agent(simmod.TEAM_BLUE, 590.0, 180.0, sim.blue_config)
    blue_lower = simmod.Agent(simmod.TEAM_BLUE, 590.0, 220.0, sim.blue_config)

    sim.team_maneuver[simmod.TEAM_RED] = "LEFT_ADVANCE"
    sim.team_maneuver[simmod.TEAM_BLUE] = "LEFT_ADVANCE"

    red_left_mult = sim._maneuver_speed_multiplier(red_left, red_center, blue_center, retreating=False)
    red_right_mult = sim._maneuver_speed_multiplier(red_right, red_center, blue_center, retreating=False)
    blue_upper_mult = sim._maneuver_speed_multiplier(blue_upper, red_center, blue_center, retreating=False)
    blue_lower_mult = sim._maneuver_speed_multiplier(blue_lower, red_center, blue_center, retreating=False)

    assert red_left_mult == simmod.MAIN_ATTACK_SPEED_MULTIPLIER
    assert red_right_mult == simmod.SUPPORT_SPEED_MULTIPLIER
    assert blue_upper_mult == simmod.SUPPORT_SPEED_MULTIPLIER
    assert blue_lower_mult == simmod.MAIN_ATTACK_SPEED_MULTIPLIER

    sim.team_maneuver[simmod.TEAM_RED] = "RIGHT_ADVANCE"
    sim.team_maneuver[simmod.TEAM_BLUE] = "RIGHT_ADVANCE"
    assert sim._maneuver_speed_multiplier(red_left, red_center, blue_center, retreating=False) == simmod.SUPPORT_SPEED_MULTIPLIER
    assert sim._maneuver_speed_multiplier(red_right, red_center, blue_center, retreating=False) == simmod.MAIN_ATTACK_SPEED_MULTIPLIER
    assert sim._maneuver_speed_multiplier(blue_upper, red_center, blue_center, retreating=False) == simmod.MAIN_ATTACK_SPEED_MULTIPLIER
    assert sim._maneuver_speed_multiplier(blue_lower, red_center, blue_center, retreating=False) == simmod.SUPPORT_SPEED_MULTIPLIER


def test_initial_formation_is_split_into_three_vertical_bands():
    red_cfg = simmod.TeamConfig({
        "max_hp": (80.0, 80.0),
        "speed": (30.0, 30.0),
        "damage": (10.0, 10.0),
        "attack_interval": (0.5, 0.5),
        "armor": (0.0, 0.0),
        "perception": (150.0, 150.0),
        "aggression": (1.0, 1.0),
        "courage": (1.0, 1.0),
    })
    blue_cfg = simmod.TeamConfig({
        "max_hp": (80.0, 80.0),
        "speed": (30.0, 30.0),
        "damage": (10.0, 10.0),
        "attack_interval": (0.5, 0.5),
        "armor": (0.0, 0.0),
        "perception": (150.0, 150.0),
        "aggression": (1.0, 1.0),
        "courage": (1.0, 1.0),
    })
    common = simmod.CommonConfig(
        red_team_size=10,
        blue_team_size=10,
        cell_size=24,
        separation_radius=10.0,
        melee_range=9.0,
        local_balance_radius=42.0,
    )
    sim = simmod.BattleSimulation(red_cfg, blue_cfg, common)

    red_agents = [a for a in sim.agents if a.team == simmod.TEAM_RED]
    blue_agents = [a for a in sim.agents if a.team == simmod.TEAM_BLUE]

    assert len(red_agents) == 10
    assert len(blue_agents) == 10

    top_band = [a for a in red_agents if a.pos.y < simmod.WORLD_HEIGHT * 0.33]
    mid_band = [a for a in red_agents if simmod.WORLD_HEIGHT * 0.33 <= a.pos.y < simmod.WORLD_HEIGHT * 0.67]
    bottom_band = [a for a in red_agents if a.pos.y >= simmod.WORLD_HEIGHT * 0.67]

    assert len(top_band) > 0
    assert len(mid_band) > 0
    assert len(bottom_band) > 0
    assert len(top_band) + len(mid_band) + len(bottom_band) == len(red_agents)


def test_directional_damage_is_applied_per_hit():
    cfg = simmod.TeamConfig({
        "max_hp": (100.0, 100.0),
        "speed": (30.0, 30.0),
        "damage": (10.0, 10.0),
        "attack_interval": (0.5, 0.5),
        "armor": (0.0, 0.0),
        "perception": (150.0, 150.0),
        "aggression": (1.0, 1.0),
        "courage": (1.0, 1.0),
    })
    agent = simmod.Agent(simmod.TEAM_RED, 50.0, 50.0, cfg)
    agent.hp = 100.0
    agent.max_hp = 100.0
    agent.forward = pygame.Vector2(1.0, 0.0)

    front_damage = agent.calculate_received_damage(10.0, pygame.Vector2(1.0, 0.0))
    side_damage = agent.calculate_received_damage(10.0, pygame.Vector2(0.0, 1.0))
    rear_damage = agent.calculate_received_damage(10.0, pygame.Vector2(-1.0, 0.0))

    assert front_damage == pytest.approx(5.0)
    assert side_damage == pytest.approx(10.0)
    assert rear_damage == pytest.approx(15.0)


def test_enemy_direction_count_distinguishes_front_from_multi_direction_encirclement():
    sim, _, _, _ = _make_sim()
    agent = simmod.Agent(simmod.TEAM_RED, 100.0, 100.0, sim.red_config)
    agent.forward = pygame.Vector2(1.0, 0.0)

    enemies = [
        simmod.Agent(simmod.TEAM_BLUE, 140.0, 100.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 150.0, 100.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 100.0, 140.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 100.0, 60.0, sim.blue_config),
    ]

    local = sim._local_tactical_state(agent, enemies)
    assert local.enemy_direction_count >= 3
    assert local.encirclement_ratio > 0.0
    assert local.enemy_direction_count <= simmod.ENCIRCLEMENT_SECTORS
