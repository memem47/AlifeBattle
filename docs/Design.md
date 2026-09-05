# AlifeBattle Design Document

## 1. Overview

AlifeBattle is a real-time many-versus-many combat simulation in which individual agents make decisions based primarily on local information.

The initial target scale is:

* 1,000 agents vs. 1,000 agents
* Approximately 2,000 simultaneously active agents
* Real-time graphical visualization using Pygame

The main goal is not to directly program high-level military tactics. Instead, the system is intended to explore whether behaviors such as front-line formation, encirclement, retreat, concentration of forces, and coordinated movement can emerge from relatively simple local rules.

The project is also intended as a learning platform for real-time simulation, artificial life, optimization, spatial algorithms, and emergent behavior.

## 2. Objectives

### 2.1 Functional Objectives

The system should:

* Simulate approximately 2,000 agents in real time.
* Represent each soldier as an independent agent.
* Allow agents to make decisions based on nearby information.
* Support differences in physical ability and behavioral tendencies between agents.
* Visualize movement, combat, casualties, and battle progress.
* Provide a structure that can later support unit types, morale, commanders, terrain, communication, and evolution.

### 2.2 Engineering Objectives

The project should provide practical experience with:

* Python application design
* Object-oriented design
* Real-time game loops
* Spatial partitioning
* Performance profiling
* Algorithm optimization
* Artificial-life systems
* Emergent behavior
* Evolutionary algorithms
* NumPy, Numba, and potentially GPU computation

## 3. Design Principles

### 3.1 Avoid Centralized Control

The simulation should not directly specify the movement of every soldier from a central controller.

A central system may eventually provide high-level objectives, but individual movement and combat decisions should remain agent-based.

### 3.2 Prefer Local Information

Agents should normally make decisions using information available within their perception range.

This allows imperfect information and local interactions to produce complex global behavior.

### 3.3 Start with Simple Rules

Complex tactics should not initially be hard-coded.

Instead, behavior should emerge from combinations of simple forces such as:

* attraction toward enemies
* cohesion with allies
* separation from nearby agents
* retreat from unfavorable situations
* behavioral randomness

### 3.4 Separate Simulation from Rendering

The simulation engine should not depend on graphical rendering.

This is important because future evolutionary experiments may require thousands of battles to run without displaying them.

### 3.5 Measure Before Optimizing

Performance improvements should be based on profiling results rather than assumptions.

## 4. High-Level Architecture

```text
Game
├─ Simulation
│  ├─ Agent
│  ├─ Team
│  ├─ SpatialGrid
│  ├─ CombatSystem
│  └─ World
├─ Renderer
├─ InputController
└─ Statistics
```

The first prototype may keep several responsibilities in a single Python file, but the logical responsibilities should remain separated.

## 5. Game

The `Game` component manages the overall application lifecycle.

Responsibilities:

* initialization
* main loop
* input processing
* simulation update
* rendering
* termination

Conceptually:

```python
while running:
    process_input()
    simulation.update(dt)
    renderer.draw()
```

`Game` should not contain detailed agent decision logic.

## 6. Simulation

The `Simulation` component owns and updates the world state.

Responsibilities:

* managing agents
* rebuilding or updating the spatial grid
* updating agents
* processing combat
* processing deaths
* checking victory conditions
* updating statistics

Typical update sequence:

```text
1. Update spatial partition
2. Gather local information
3. Decide agent actions
4. Update movement
5. Resolve attacks
6. Update hit points
7. Process deaths
8. Update statistics
```

A future implementation should separate decision calculation from state application to reduce update-order bias.

## 7. Agent

An `Agent` represents one soldier.

### 7.1 Basic State

Typical state:

```python
id
team
position
velocity
hp
max_hp
alive
```

### 7.2 Physical and Combat Parameters

Examples:

```python
speed
attack_power
attack_range
attack_interval
vision_range
```

### 7.3 Behavioral Parameters

Possible behavioral parameters:

```python
aggressiveness
bravery
cohesion
caution
```

Examples:

* High `aggressiveness`: stronger tendency to approach enemies.
* Low `bravery`: earlier retreat under disadvantage.
* High `cohesion`: stronger tendency to remain near allies.
* High `caution`: stronger avoidance of locally dangerous situations.

These parameters may later become part of an evolvable genome.

## 8. Agent Behavior Model

An agent's movement vector can be modeled as the combination of several behavioral forces.

```text
Movement =
    EnemyAttraction
  + AllyCohesion
  + Separation
  + Retreat
  + Noise
```

### 8.1 Enemy Attraction

Agents move toward selected enemy targets.

Initially, the nearest visible enemy may be used.

Later versions may use a target evaluation function.

### 8.2 Ally Cohesion

Agents tend to remain reasonably close to nearby allies.

This is conceptually similar to cohesion behavior in Boids.

### 8.3 Separation

Agents avoid occupying the same physical location.

Repulsive force should increase as distance decreases.

### 8.4 Retreat

Agents may retreat when local conditions become unfavorable.

Possible inputs include:

* low HP
* local numerical disadvantage
* low morale
* nearby ally deaths
* commander death

The initial implementation may use only HP and the local ally-to-enemy ratio.

### 8.5 Noise

Small random movement components prevent all agents from behaving identically.

Noise may also help avoid overly stable or artificial-looking battle lines.

## 9. Target Selection

The initial implementation may select the nearest enemy within perception range.

Future versions can use a score such as:

```text
TargetScore =
    distance
  + target HP
  + target type
  + nearby allies
  + threat level
```

The exact scoring function should remain replaceable.

## 10. SpatialGrid

### 10.1 Purpose

A naive all-to-all search for 2,000 agents can require approximately:

```text
2,000 × 2,000
= 4,000,000
```

pair comparisons.

To reduce this cost, the battlefield is divided into spatial cells.

```text
+----+----+----+
|    | ●● |    |
+----+----+----+
| ●  | ●  | ● |
+----+----+----+
|    | ●  |    |
+----+----+----+
```

Agents search only their current cell and nearby cells.

### 10.2 Data Structure

Example:

```python
grid[(cell_x, cell_y)] = [agent1, agent2, ...]
```

### 10.3 Processing

```text
Agent position
↓
Calculate cell coordinates
↓
Register agent in grid
↓
Search nearby cells only
```

### 10.4 Cell Size

The initial prototype uses approximately:

```text
CELL_SIZE = 48
```

The appropriate value should later be determined experimentally based on:

* vision range
* combat range
* agent density
* profiling results

## 11. CombatSystem

An attack occurs when:

```text
distance_to_target <= attack_range
AND
attack_cooldown <= 0
```

Example:

```python
target.hp -= attacker.attack_power
attacker.cooldown = attacker.attack_interval
```

When:

```python
target.hp <= 0
```

the target is marked as dead.

Future combat models may support:

* projectiles
* armor
* accuracy
* ranged combat
* suppression
* directional attacks

## 12. Team

A `Team` represents a group of allied agents.

Initial responsibilities:

```python
id
members
spawn_area
```

Future responsibilities may include:

```python
commander
global_morale
objective
strategy
```

The team should provide high-level context rather than directly controlling every soldier.

## 13. Rendering

The `Renderer` is responsible only for visualization.

Initial visualization:

* Team A: one color
* Team B: another color
* dead agents: dark markers

The interface should display:

* surviving agents per team
* FPS
* simulation speed
* pause state
* battle result

Rendering logic should remain separate from simulation behavior.

## 14. Input Controls

Initial controls:

| Key   | Action                    |
| ----- | ------------------------- |
| Space | Pause / resume            |
| R     | Restart                   |
| G     | Toggle spatial grid       |
| +     | Increase simulation speed |
| -     | Decrease simulation speed |
| Esc   | Exit                      |

## 15. Time Management

Simulation movement should not depend directly on FPS.

Movement should use frame delta time:

```python
position += velocity * dt
```

This allows similar simulation speed at:

```text
60 FPS
30 FPS
20 FPS
```

although extremely low FPS may still reduce simulation accuracy.

## 16. Performance Requirements

Initial target:

```text
Agents: approximately 2,000
Minimum target: 30 FPS
Preferred target: 60 FPS
```

Future targets:

```text
Phase 1: 2,000 agents
Phase 2: 10,000 agents
Phase 3: 50,000+ agents
```

Performance improvements should preferably allow larger simulations without requiring stronger hardware.

## 17. Expected Performance Bottlenecks

Likely bottlenecks include:

1. Python-level agent loops
2. repeated function calls for every agent
3. neighborhood queries
4. distance calculations
5. repeated target searches
6. large numbers of Python objects
7. repeated reconstruction of temporary lists

Rendering may eventually become expensive, but simulation logic is expected to be the primary bottleneck first.

## 18. Optimization Strategy

### Phase 1: Algorithmic Optimization

Potential improvements:

* optimize spatial partitioning
* reduce repeated neighborhood queries
* reuse nearby-agent information
* reduce target-search frequency
* compare squared distances instead of repeatedly calculating square roots

For example:

```text
Target search every frame
```

may be replaced with:

```text
Target search every 5–10 frames
```

when appropriate.

### Phase 2: Data-Oriented Design

Replace large numbers of independent Python objects with arrays such as:

```text
positions[]
velocities[]
hp[]
team[]
```

This should improve memory locality and make vectorization easier.

### Phase 3: NumPy

Move suitable calculations to vectorized NumPy operations.

### Phase 4: Numba

Use JIT compilation for performance-critical loops.

### Phase 5: GPU Computing

GPU computation may be considered if the simulation grows to tens or hundreds of thousands of agents.

## 19. Future Artificial-Life Features

### 19.1 Morale

Possible morale model:

```text
Morale =
    nearby allies
  - nearby enemies
  - recent allied deaths
  + battle advantage
  + commander effect
```

Low morale may cause:

* reduced aggression
* retreat
* complete rout

### 19.2 Limited Vision

Agents should eventually stop having perfect omnidirectional information.

Possible parameters:

```text
vision_range
vision_angle
```

### 19.3 Information Sharing

Information may propagate through nearby soldiers or command structures.

Example:

```text
Soldier
↓
Squad leader
↓
Nearby soldiers
```

This allows battlefield knowledge itself to become part of the simulation.

### 19.4 Command Hierarchy

Possible hierarchy:

```text
Army Commander
↓
Unit Commander
↓
Soldier
```

Higher levels issue increasingly abstract orders.

Example:

```text
Commander:
"Advance on the right."

Soldier:
"Attack this enemy."
"Avoid this nearby threat."
```

### 19.5 Unit Types

Possible future types:

* Infantry
* Heavy Infantry
* Archer
* Cavalry
* Commander

Each unit type should differ in both physical parameters and behavior rules.

## 20. Evolution System

Behavioral parameters may eventually be encoded as a genome.

Possible genes:

```text
aggressiveness
bravery
cohesion
vision_range
retreat_threshold
target_selection_bias
```

After each battle, a fitness score can be calculated.

Example:

```text
Fitness =
    survival
  + damage dealt
  + enemies defeated
  + team victory
```

The next generation can be produced through:

```text
Generation N
↓
Battle
↓
Fitness Evaluation
↓
Selection
↓
Crossover
↓
Mutation
↓
Generation N+1
```

The purpose is not merely to optimize individual kill count.

The more interesting objective is to observe whether useful collective strategies emerge through selection.

## 21. Recommended Project Structure

Initial structure:

```text
AlifeBattle/
├─ alife_battle.py
├─ requirements.txt
├─ README.md
├─ .gitignore
└─ docs/
   └─ Design.md
```

Future structure:

```text
AlifeBattle/
├─ main.py
├─ simulation/
│  ├─ simulation.py
│  ├─ agent.py
│  ├─ team.py
│  ├─ world.py
│  └─ spatial_grid.py
├─ systems/
│  ├─ movement.py
│  ├─ combat.py
│  ├─ perception.py
│  └─ morale.py
├─ rendering/
│  └─ renderer.py
├─ evolution/
│  ├─ genome.py
│  └─ evolution.py
├─ docs/
│  ├─ Design.md
│  └─ Performance.md
├─ tests/
├─ requirements.txt
├─ README.md
└─ .gitignore
```

## 22. Development Roadmap

### Version 0.1 — Prototype

* 1,000 vs. 1,000 agents
* movement
* target search
* attack
* death
* spatial grid
* graphical visualization

### Version 0.2 — Performance

* profiling
* spatial-grid optimization
* reduction of redundant calculations
* target-search optimization

Target:

```text
2,000 agents at 30 FPS or better
```

### Version 0.3 — Collective Behavior

* cohesion
* separation
* local numerical advantage
* retreat behavior
* improved battle-line formation

### Version 0.4 — Perception and Morale

* field of view
* limited vision
* morale
* rout behavior

### Version 0.5 — Units and Commanders

* squads
* commanders
* orders
* information sharing

### Version 0.6 — Unit Types

* infantry
* ranged units
* cavalry

### Version 0.7 — Environment

* walls
* terrain
* forests
* movement costs
* elevation

### Version 0.8 — Evolution

* genome
* fitness
* selection
* mutation
* automated battles

### Version 1.0 — Artificial-Life Battle Simulator

The long-term objective is:

```text
Local agent rules
+
Individual variation
+
Environment
+
Evolution
↓
Emergent collective tactics
```

## 23. Long-Term Research Question

The central question of AlifeBattle is:

Can recognizable military behavior emerge without explicitly programming military tactics?

For example:

```text
No command says "encircle the enemy."
↓
Encirclement nevertheless emerges.
```

or:

```text
No algorithm explicitly says "form a battle line."
↓
A battle line emerges from local interactions.
```

AlifeBattle should therefore evolve not only as a game, but also as an experimental platform for:

* artificial life
* complex systems
* emergent behavior
* evolutionary computation
* large-scale real-time simulation
