# AlifeBattle

AlifeBattle is a real-time artificial-life-style battle simulation written in Python and Pygame.

The simulation models large numbers of autonomous agents fighting on a shared battlefield. Each agent makes decisions mainly from local information such as nearby enemies, local numerical balance, health, and its own behavioral traits.

The project explores whether recognizable collective behaviors such as battle-line formation, concentration of forces, retreat, and obstacle avoidance can emerge from simple agent-level rules.

## Current Features

### Large-Scale Agent Simulation

* Default configuration: 1,000 RED agents vs. 1,000 BLUE agents
* RED and BLUE team sizes can be configured independently
* Each soldier is represented as an independent agent
* Real-time movement, targeting, combat, damage, and death

### Individual Traits

Each agent receives randomly generated traits when the simulation is reset:

* HP
* Speed
* Damage
* Attack interval
* Perception
* Aggression
* Courage

Each trait is generated from a continuous uniform distribution.

The GUI specifies each distribution using:

```text
center
width
```

The actual range is:

```text
minimum = center - width / 2
maximum = center + width / 2
```

Example:

```text
HP center = 100
HP width  = 40

→ HP range = 80–120
```

### Local Agent Behavior

Agents currently perform the following behaviors:

* search for nearby enemies
* select a nearby target
* move toward the target
* avoid excessive crowding
* evaluate the local ally/enemy balance
* retreat when locally overwhelmed
* retreat when badly wounded
* attack enemies within melee range

Agents without a detected target use the center of the opposing army as a coarse strategic direction.

### Retreat Behavior

Retreat is currently evaluated dynamically rather than represented as a permanent state.

Agents may retreat when:

* they are locally outnumbered and have relatively low courage
* their HP falls below a courage-dependent threshold

Retreating agents are shown using a different color.

### Spatial Grid

A spatial grid is used to reduce neighborhood-search cost.

Instead of comparing every agent with every other agent, agents search only nearby grid cells.

The grid is used for:

* enemy detection
* local force-balance calculation
* separation behavior
* obstacle collision

### Obstacles

Random obstacle clusters are generated when the simulation is reset.

Obstacles:

* occupy grid cells
* are generated as connected clusters
* avoid the main RED and BLUE spawn regions
* block agent movement

Cluster generation uses bounded search attempts to prevent infinite loops when no valid expansion is possible.

### Visualization

Living agents are rendered as triangles.

The triangle:

* points in the current velocity direction
* falls back to the enemy-facing direction when stationary
* changes color while retreating
* changes size according to a composite score based on the agent's traits

Dead agents remain visible as dim markers.

### Interactive GUI

The GUI allows RED and BLUE parameters to be edited independently.

Per-team settings:

* Team size
* HP
* Speed
* Damage
* Attack interval
* Perception
* Aggression
* Courage

Common settings:

* Cell size
* Separation radius
* Melee range
* Local balance radius

Numeric fields support:

* keyboard input
* mouse-operated up/down arrows

Changes to simulation parameters are applied when `APPLY + RESET` is pressed.

Existing agents are not modified in real time; the armies are regenerated using the new configuration.

## Controls

| Control       | Action                              |
| ------------- | ----------------------------------- |
| Space         | Pause / resume                      |
| R             | Reset battle                        |
| G             | Toggle spatial grid                 |
| +             | Increase simulation speed           |
| -             | Decrease simulation speed           |
| Esc           | Exit                                |
| PAUSE / PLAY  | Pause or resume with mouse          |
| RESET         | Reset with mouse                    |
| GRID          | Toggle grid with mouse              |
| +/- buttons   | Change simulation speed             |
| APPLY + RESET | Apply parameter changes and restart |

## Requirements

Recommended environment:

* Python 3.12 or 3.13
* Pygame 2.6 or later

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Running

Create a virtual environment on Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run:

```powershell
python alife_battle.py
```

## Project Structure

Current recommended structure:

```text
AlifeBattle/
├─ alife_battle.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ .gitattributes
└─ docs/
   └─ Design.md
```

As the project grows:

```text
AlifeBattle/
├─ main.py
├─ simulation/
│  ├─ agent.py
│  ├─ simulation.py
│  ├─ spatial_grid.py
│  └─ world.py
├─ systems/
│  ├─ movement.py
│  ├─ combat.py
│  └─ perception.py
├─ rendering/
│  └─ renderer.py
├─ docs/
│  ├─ Design.md
│  ├─ Performance.md
│  └─ Experiments/
├─ tests/
├─ requirements.txt
├─ README.md
├─ .gitignore
└─ .gitattributes
```

## Current Limitations

The current version is still a prototype.

Important limitations include:

* Agent updates are sequential rather than simultaneous.
* RED agents are currently stored before BLUE agents and therefore updated earlier in each frame.
* Attack and movement results are immediately applied during the update loop.
* Target selection uses the nearest detected enemy.
* Agents use the opposing army's center when no local target is detected.
* Retreat is recalculated continuously and is not yet a persistent finite-state behavior.
* Obstacle avoidance is reactive rather than path-planned.
* There are no explicit squads, commanders, morale system, ranged units, terrain costs, or evolutionary learning yet.

These limitations are important when interpreting experimental results.

## Development Direction

Near-term priorities:

1. Measure and eliminate RED/BLUE update-order bias.
2. Add automated multi-battle experiments and win-rate statistics.
3. Improve local collective behavior.
4. Introduce explicit behavioral states such as fighting, retreating, and routing.
5. Improve obstacle navigation.
6. Separate simulation logic from rendering and GUI code.

Longer-term goals include:

* morale
* limited field of view
* information sharing
* squads and commanders
* different unit types
* terrain
* evolutionary algorithms
* headless batch simulation
* NumPy / Numba optimization
* larger populations

## Core Research Question

The central question of AlifeBattle is:

> Can recognizable military behavior emerge without explicitly programming military tactics?

For example:

```text
No explicit command says:
"Encircle the enemy."

↓ local interactions

Encirclement emerges.
```

The project is therefore intended to become both a game-like simulation and an experimental platform for artificial life, emergent behavior, complex systems, and evolutionary computation.
