import pygame

import alife_battle as simmod


def test_attacks_are_resolved_simultaneously():
    red_cfg = simmod.TeamConfig({
        "max_hp": (5.0, 5.0),
        "speed": (10.0, 10.0),
        "damage": (20.0, 20.0),
        "attack_interval": (0.1, 0.1),
        "perception": (150.0, 150.0),
        "aggression": (1.0, 1.0),
        "courage": (1.0, 1.0),
    })
    blue_cfg = simmod.TeamConfig({
        "max_hp": (5.0, 5.0),
        "speed": (10.0, 10.0),
        "damage": (20.0, 20.0),
        "attack_interval": (0.1, 0.1),
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
    red.max_hp = 5.0
    red.hp = 5.0
    red.damage = 20.0
    red.attack_interval = 0.1
    red.attack_cooldown = 0.0
    red.target = blue
    red.forward = pygame.Vector2(1.0, 0.0)

    blue.max_hp = 5.0
    blue.hp = 5.0
    blue.damage = 20.0
    blue.attack_interval = 0.1
    blue.attack_cooldown = 0.0
    blue.target = red
    blue.forward = pygame.Vector2(-1.0, 0.0)

    sim = simmod.BattleSimulation(red_cfg, blue_cfg, common)
    sim.agents = [red, blue]
    sim.grid.rebuild(sim.agents)

    sim.update(0.016)

    assert red.hp <= 0 and blue.hp <= 0
