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


def test_logical_world_is_separate_from_battle_view():
    assert simmod.BATTLE_VIEW_WIDTH == 600
    assert simmod.BATTLE_VIEW_HEIGHT == 600
    assert simmod.LOGICAL_WORLD_WIDTH == 600
    assert simmod.LOGICAL_WORLD_HEIGHT == 600
    assert simmod.WORLD_WIDTH == simmod.LOGICAL_WORLD_WIDTH
    assert simmod.WORLD_HEIGHT == simmod.LOGICAL_WORLD_HEIGHT
    view_pos = simmod.world_to_view(pygame.Vector2(simmod.LOGICAL_WORLD_WIDTH, simmod.LOGICAL_WORLD_HEIGHT))
    assert view_pos.x == pytest.approx(simmod.BATTLE_VIEW_WIDTH)
    assert view_pos.y == pytest.approx(simmod.BATTLE_VIEW_HEIGHT)


def test_agents_keep_persistent_formation_units_and_slots():
    sim, _, _, _ = _make_sim()
    red_agents = [agent for agent in sim.agents if agent.team == simmod.TEAM_RED]
    assert set(sim.team_formation_units[simmod.TEAM_RED]) == {"UNIT_0", "UNIT_1", "UNIT_2"}
    assert {agent.formation_unit_id for agent in red_agents} <= {"UNIT_0", "UNIT_1", "UNIT_2"}
    assert all(agent.formation_slot_local.length_squared() > 0.0 for agent in red_agents)


def test_formation_origin_is_independent_of_agent_positions():
    sim, _, _, _ = _make_sim()
    origin = sim.team_formation_origin[simmod.TEAM_RED].copy()
    for agent in sim.agents:
        if agent.team == simmod.TEAM_RED:
            agent.pos.xy = 600.0, 500.0

    assert sim.team_formation_origin[simmod.TEAM_RED] == origin


def test_agents_without_targets_follow_formation_instead_of_enemy_center():
    sim, _, _, _ = _make_sim()
    agent = sim.agents[0]
    agent.target = None
    agent.pos = sim.team_formation_origin[agent.team] + pygame.Vector2(-80.0, 0.0)
    local_state = sim._local_tactical_state(agent, [])

    move = sim._movement_vector(
        agent,
        sim.team_formation_origin[simmod.TEAM_RED],
        sim.team_formation_origin[simmod.TEAM_BLUE],
        local_state.allies,
        local_state.enemies,
        local_state,
    )

    assert move.x > 0.0


def test_maneuvers_deform_generic_unit_targets():
    sim, _, _, _ = _make_sim()
    states = sim.team_formation_units[simmod.TEAM_RED]
    base = {unit_id: state.target_offset_local.copy() for unit_id, state in states.items()}

    sim.team_maneuver[simmod.TEAM_RED] = "LEFT_ADVANCE"
    sim._update_formation_targets()
    assert states["UNIT_0"].target_offset_local.x > base["UNIT_0"].x
    assert states["UNIT_1"].target_offset_local == base["UNIT_1"]
    assert states["UNIT_2"].target_offset_local == base["UNIT_2"]

    sim.team_maneuver[simmod.TEAM_RED] = "CENTER_BREAK"
    sim._update_formation_targets()
    assert states["UNIT_1"].target_offset_local.x > states["UNIT_0"].target_offset_local.x
    assert states["UNIT_1"].target_offset_local.x > states["UNIT_2"].target_offset_local.x

    sim.team_maneuver[simmod.TEAM_RED] = "ENCIRCLE"
    sim._update_formation_targets()
    assert states["UNIT_0"].target_offset_local.y < base["UNIT_0"].y
    assert states["UNIT_2"].target_offset_local.y > base["UNIT_2"].y
    assert states["UNIT_1"].target_offset_local == base["UNIT_1"]


def test_encircle_lateral_offsets_stay_in_pixel_coordinates():
    sim, _, _, _ = _make_sim()
    states = sim.team_formation_units[simmod.TEAM_RED]

    assert states["UNIT_0"].base_offset_local.y == pytest.approx(-simmod.FORMATION_LATERAL_SPACING)
    assert states["UNIT_2"].base_offset_local.y == pytest.approx(simmod.FORMATION_LATERAL_SPACING)

    sim.team_maneuver[simmod.TEAM_RED] = "ENCIRCLE"
    sim._update_formation_targets()

    assert states["UNIT_0"].target_offset_local.y == pytest.approx(
        -simmod.FORMATION_LATERAL_SPACING - simmod.FORMATION_ENCIRCLE_LATERAL_DISTANCE
    )
    assert states["UNIT_2"].target_offset_local.y == pytest.approx(
        simmod.FORMATION_LATERAL_SPACING + simmod.FORMATION_ENCIRCLE_LATERAL_DISTANCE
    )


def test_formation_maneuvers_are_mirrored_in_army_local_coordinates():
    sim, _, _, _ = _make_sim()
    sim.team_maneuver[simmod.TEAM_RED] = "LEFT_ADVANCE"
    sim.team_maneuver[simmod.TEAM_BLUE] = "LEFT_ADVANCE"
    sim._update_formation_targets()
    red_left = sim.team_formation_units[simmod.TEAM_RED]["UNIT_0"].target_offset_local.x
    blue_left = sim.team_formation_units[simmod.TEAM_BLUE]["UNIT_0"].target_offset_local.x
    assert red_left == pytest.approx(blue_left)


def test_five_unit_definition_uses_same_controller():
    sim, _, _, _ = _make_sim()
    five_band = simmod.FormationDefinition(
        "FIVE_BAND",
        tuple(simmod.FormationUnitSpec(f"UNIT_{index}", 0.2, 0.0, offset) for index, offset in enumerate((-1.0, -0.5, 0.0, 0.5, 1.0))),
    )
    simmod.FORMATION_DEFINITIONS["FIVE_BAND"] = five_band
    sim.agents.clear()
    sim._spawn_army(simmod.TEAM_RED, 130.0, simmod.WORLD_HEIGHT / 2, 1, 20, "FIVE_BAND")
    sim.team_maneuver[simmod.TEAM_RED] = "RIGHT_ADVANCE"
    sim._update_formation_targets()
    assert len(sim.team_formation_units[simmod.TEAM_RED]) == 5
    assert sim.team_formation_units[simmod.TEAM_RED]["UNIT_4"].target_offset_local.x > sim.team_formation_units[simmod.TEAM_RED]["UNIT_0"].target_offset_local.x


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
    assert local.enemy_direction_count == 1
    assert local.front_enemies == 2
    assert local.rear_enemies == 0
    assert local.encirclement_pressure == 0.0
    assert local.enemy_direction_count <= simmod.ENCIRCLEMENT_SECTORS


def test_encirclement_pressure_requires_rear_and_dense_regions():
    assert simmod._calculate_encirclement_pressure(8, 0, 0, 0) == 0.0
    assert simmod._calculate_encirclement_pressure(8, 2, 0, 0) == pytest.approx(0.50)
    assert simmod._calculate_encirclement_pressure(0, 2, 0, 2) == pytest.approx(0.45)
    assert simmod._calculate_encirclement_pressure(2, 2, 2, 2) == pytest.approx(1.0)

    sim, _, _, _ = _make_sim()
    agent = simmod.Agent(simmod.TEAM_RED, 100.0, 100.0, sim.red_config)
    agent.forward = pygame.Vector2(1.0, 0.0)
    enemies = [
        simmod.Agent(simmod.TEAM_BLUE, 125.0, 100.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 125.0, 100.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 75.0, 100.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 75.0, 100.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 100.0, 125.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 100.0, 125.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 100.0, 75.0, sim.blue_config),
        simmod.Agent(simmod.TEAM_BLUE, 100.0, 75.0, sim.blue_config),
    ]

    local = sim._local_tactical_state(agent, enemies)
    assert local.enemy_direction_count == 4
    assert (local.front_enemies, local.rear_enemies) == (2, 2)
    assert (local.left_enemies, local.right_enemies) == (2, 2)
    assert local.encirclement_pressure == pytest.approx(1.0)


def test_frontal_pressure_does_not_trigger_retreat_but_encirclement_does():
    sim, _, _, _ = _make_sim()
    agent = simmod.Agent(simmod.TEAM_RED, 350.0, 200.0, sim.red_config)
    agent.forward = pygame.Vector2(1.0, 0.0)
    agent.courage = 0.5
    agent.hp = agent.max_hp

    allies = [simmod.Agent(simmod.TEAM_RED, 325.0, 180.0 + i * 8.0, sim.red_config) for i in range(5)]
    frontal_enemies = [simmod.Agent(simmod.TEAM_BLUE, 375.0, 180.0 + i * 8.0, sim.blue_config) for i in range(6)]
    sim.agents = [agent, *allies, *frontal_enemies]
    sim.grid.rebuild(sim.agents)
    frontal_state = sim._local_tactical_state(agent)
    sim._movement_vector(agent, pygame.Vector2(300.0, 200.0), pygame.Vector2(400.0, 200.0),
                         frontal_state.allies, frontal_state.enemies, frontal_state)
    assert frontal_state.encirclement_pressure == 0.0
    assert agent.retreating is False

    encircled_enemies = []
    for x, y in ((375.0, 200.0), (375.0, 203.0), (325.0, 200.0), (325.0, 197.0),
                 (350.0, 225.0), (353.0, 225.0), (350.0, 175.0), (353.0, 175.0)):
        encircled_enemies.append(simmod.Agent(simmod.TEAM_BLUE, x, y, sim.blue_config))
    sim.agents = [agent, *allies, *encircled_enemies]
    sim.grid.rebuild(sim.agents)
    encircled_state = sim._local_tactical_state(agent)
    sim._movement_vector(agent, pygame.Vector2(300.0, 200.0), pygame.Vector2(400.0, 200.0),
                         encircled_state.allies, encircled_state.enemies, encircled_state)
    assert encircled_state.encirclement_pressure == pytest.approx(1.0)
    assert agent.retreating is True

    agent.courage = 0.95
    sim._movement_vector(agent, pygame.Vector2(300.0, 200.0), pygame.Vector2(400.0, 200.0),
                         encircled_state.allies, encircled_state.enemies, encircled_state)
    assert agent.retreating is False
