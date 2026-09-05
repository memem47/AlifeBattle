# AlifeBattle Design Document

## 1. Purpose

AlifeBattle is a real-time many-agent combat simulation intended to explore artificial life, emergent collective behavior, and large-scale agent simulation.

The system does not primarily aim to implement sophisticated military tactics directly.

Instead, it assigns simple local rules and individual traits to autonomous agents and observes the resulting global behavior.

The long-term research question is:

> Can recognizable collective tactics emerge from simple local agent behavior without explicitly programming those tactics?

## 2. Current Scope

The current prototype supports:

* configurable RED and BLUE armies
* approximately 2,000 agents by default
* independent individual traits
* local enemy detection
* local numerical-balance evaluation
* target pursuit
* crowding avoidance
* retreat behavior
* melee combat
* randomly generated obstacles
* spatial partitioning
* real-time Pygame visualization
* GUI parameter editing

The current implementation remains in a single Python source file.

## 3. System Layout

The window consists of four main areas.

```text
+------------+--------------------------+------------+
| RED config |                          | BLUE config|
|            |       Battlefield        |            |
|            |                          |            |
+------------+--------------------------+------------+
|               Common parameters                    |
+----------------------------------------------------+
```

The battlefield size is currently:

```text
WORLD_WIDTH  = 700
WORLD_HEIGHT = 552
```

The vertical size is approximately 1.3 times the earlier prototype.

## 4. Logical Architecture

Although the prototype is currently implemented in one file, the logical structure is:

```text
Application
├─ Configuration
│  ├─ TeamConfig
│  └─ CommonConfig
├─ Simulation
│  ├─ Agent
│  ├─ BattleSimulation
│  └─ SpatialGrid
├─ Environment
│  └─ Obstacles
├─ UI
│  └─ InputField
└─ Rendering
   ├─ Battlefield
   ├─ Agents
   ├─ Obstacles
   └─ Parameter panels
```

These logical responsibilities should eventually be separated into modules.

## 5. Configuration Model

### 5.1 TeamConfig

Each army has its own `TeamConfig`.

```python
@dataclass
class TeamConfig:
    values: dict
```

The configurable agent traits are:

```text
max_hp
speed
damage
attack_interval
perception
aggression
courage
```

RED and BLUE can use different distributions.

### 5.2 Distribution Representation

The GUI represents each trait distribution using:

```text
center
width
```

During `APPLY + RESET`, these are converted to:

```text
minimum = center - width / 2
maximum = center + width / 2
```

Each new agent samples its trait using a continuous uniform distribution:

```python
random.uniform(minimum, maximum)
```

The current model therefore assumes no normal distribution or cross-trait correlation.

### 5.3 CommonConfig

Current common configuration:

```python
@dataclass
class CommonConfig:
    red_team_size: int
    blue_team_size: int
    cell_size: int
    separation_radius: float
    melee_range: float
    local_balance_radius: float
```

`red_team_size` and `blue_team_size` can be independently configured.

## 6. Agent Model

Each `Agent` represents one soldier.

### 6.1 State

Current state includes:

```text
team
position
velocity
alive
hp
target
attack cooldown
retarget timer
retreating
```

### 6.2 Individual Traits

Each agent also stores:

```text
max_hp
speed
damage
attack_interval
perception
aggression
courage
```

These are fixed when the agent is generated.

Changing GUI values does not alter existing agents. New values take effect after the simulation is reset.

### 6.3 Memory Optimization

`Agent` uses `__slots__`.

This reduces per-object attribute overhead compared with standard Python instances.

This is useful for thousands of agents, although future larger simulations may require a data-oriented representation using arrays.

## 7. SpatialGrid

### 7.1 Purpose

A naive neighborhood search can approach:

```text
N × N
```

comparisons.

For approximately 2,000 agents, this could result in millions of pair checks.

The battlefield is therefore divided into spatial cells.

```text
+----+----+----+
|    | ●● |    |
+----+----+----+
| ●  | ●  | ● |
+----+----+----+
|    | ●  |    |
+----+----+----+
```

### 7.2 Data Structure

```python
cells[(cell_x, cell_y)] = [agents...]
```

Only living agents are inserted.

### 7.3 Neighborhood Query

`nearby(position, radius)` identifies all cells whose area may overlap the query radius and yields their agents.

Exact distance filtering is performed by the calling logic.

### 7.4 Grid Rebuilding

The current implementation rebuilds the spatial grid once at the beginning of every simulation update.

Agents then move during the same update without rebuilding the grid until the next frame.

This is an approximation that should be considered when improving simulation consistency.

## 8. Army Generation

RED and BLUE armies start from opposite sides.

Approximate spawn centers:

```text
RED  x = 130
BLUE x = WORLD_WIDTH - 130
```

Agents are arranged in broad formations with small positional jitter.

Current spacing:

```text
spacing_x = 6
spacing_y = 6
```

Agent placement avoids obstacle cells where possible.

If the initial position is obstructed, the code first tries displacement along Y and then along X.

Placement attempts are bounded.

## 9. Obstacle Generation

### 9.1 Representation

Obstacles are represented as grid-cell coordinates:

```python
obstacle_cells = set[(cell_x, cell_y)]
```

Each obstacle therefore occupies one complete spatial-grid cell.

### 9.2 Cluster Generation

At reset:

1. A number of obstacle clusters is determined from battlefield area.
2. A random cluster target size between 3 and 12 cells is selected.
3. A valid seed cell is searched for.
4. The cluster grows using random four-connected neighbors.

### 9.3 Spawn Protection

Obstacle seed and growth positions are prevented from entering protected X regions around the two army spawn centers.

Current protection width:

```text
spawn_margin = 5 × cell_size
```

### 9.4 Infinite-Loop Protection

Both seed search and cluster growth use bounded attempts.

Seed search:

```text
maximum 200 attempts
```

Cluster growth:

```text
maximum attempts = cluster_size × 50
```

If no seed is found, the cluster is skipped.

If a cluster cannot reach its requested size, the partially generated cluster is accepted.

This prevents random obstacle generation from hanging indefinitely.

## 10. Simulation Update

Current frame update:

```text
1. Increase elapsed simulation time
2. Rebuild SpatialGrid
3. Compute RED and BLUE centers
4. Iterate over all agents
   4.1 Update cooldowns
   4.2 Retarget if required
   4.3 Evaluate local numerical balance
   4.4 Calculate movement vector
   4.5 Smooth velocity
   4.6 Move while avoiding obstacle cells
   4.7 Attempt attack
```

This is currently a sequential update model.

## 11. Target Acquisition

Agents periodically search for enemies.

The search is staggered using a randomized timer so that all agents do not perform expensive target searches in the same frame.

Typical interval:

```text
0.18–0.42 seconds
```

The target is currently:

> the nearest living enemy inside the agent's perception range.

Perception is an individual agent trait.

## 12. Strategic Direction

When an agent has no valid detected target, it moves approximately toward the center of the opposing army.

```text
RED  → BLUE center
BLUE → RED center
```

This provides a coarse global strategic bias.

It means the current system is not yet based purely on locally perceived information.

A future design may remove or replace this global knowledge.

## 13. Local Balance

Local force balance is evaluated separately from perception.

```text
Agent perception
= range used to detect target enemies

Local balance radius
= radius used to estimate nearby allies and enemies
```

The local balance radius is a common simulation parameter.

This separation makes the meaning of the two concepts explicit.

## 14. Movement Model

The movement vector combines several influences:

```text
Movement =
    Target direction
  + Separation
  + Lateral variation
```

Retreat may replace the normal target direction.

### 14.1 Target Direction

If a target exists:

```text
Agent → target
```

If the target is already within approximately melee distance, direct forward movement is reduced.

If no target exists:

```text
Agent → enemy army center
```

### 14.2 Aggression

The target component is weighted by aggression.

Conceptually:

```text
high aggression
→ enemy direction receives greater relative weight

low aggression
→ other movement influences have more effect
```

Aggression does not directly increase the agent's maximum speed.

### 14.3 Separation

Agents repel nearby agents when they are inside the configured separation radius.

The force increases at shorter distances.

The current rule does not distinguish friend from foe for physical separation.

### 14.4 Lateral Variation

A sinusoidal perpendicular component is added to reduce one-dimensional movement and produce a less rigid battle front.

This component currently depends on world position and elapsed time.

## 15. Retreat Model

Retreat is not currently a persistent finite-state transition.

Instead, retreat is recalculated every update.

```text
FIGHT / ADVANCE
       ⇅
RETREAT
```

An agent retreats if either:

### Condition A: Local Numerical Disadvantage

```text
local enemies > max(2, local allies × 1.55)
AND
courage < 0.55
```

### Condition B: Heavy Injury

An agent retreats when its HP ratio falls below a courage-dependent threshold.

Lower-courage agents therefore become willing to retreat at higher HP.

### Retreat Direction

If a valid target exists:

```text
move away from target
```

Otherwise:

```text
move toward own rear area
```

The boolean:

```python
agent.retreating
```

is stored primarily so rendering can distinguish retreating agents.

A future version may replace this with an explicit state machine such as:

```text
ADVANCE
FIGHT
RETREAT
RECOVER
ROUT
```

## 16. Combat

Agents attack only a currently selected target.

Attack condition:

```text
distance <= melee_range + attacker radius + target radius
AND
attack cooldown <= 0
```

Damage:

```text
agent.damage × random factor
```

The random damage multiplier currently ranges approximately from:

```text
0.82 to 1.18
```

After attacking, the cooldown is reset to the agent's attack interval.

If HP reaches zero:

```text
alive = False
velocity = 0
target = None
```

## 17. Obstacle Collision

Before applying movement, the simulation checks whether the desired destination lies in an obstacle cell.

If blocked:

```text
1. Try X-only movement
2. Otherwise try Y-only movement
3. Otherwise heavily damp velocity
```

This is reactive obstacle avoidance.

The agent does not currently plan a route around obstacles.

Therefore agents can become inefficient or temporarily stuck around complex obstacle structures.

## 18. Update-Order Limitation

The current simulation updates agents sequentially.

Because RED agents are spawned before BLUE agents, the list normally contains:

```text
RED agents
then
BLUE agents
```

Therefore RED agents are normally processed first in each frame.

Movement and damage are applied immediately.

This creates possible update-order bias.

For example:

```text
RED attacks BLUE
→ BLUE dies
→ BLUE's later update is skipped
```

while BLUE may observe already-updated RED positions later in the same frame.

The current design therefore cannot guarantee strict RED/BLUE symmetry.

A future simulation update should use a staged model:

```text
Phase 1: Observe
Phase 2: Decide
Phase 3: Apply movement
Phase 4: Calculate attacks
Phase 5: Apply damage simultaneously
```

This is a high-priority architectural improvement.

## 19. Rendering

### 19.1 Living Agents

Living agents are drawn as triangles.

Orientation is determined from velocity.

If velocity is nearly zero:

```text
RED  faces right
BLUE faces left
```

### 19.2 Retreat Visualization

Retreating agents use distinct colors.

This allows retreat behavior to be observed visually.

### 19.3 Agent Size

Triangle size is derived from a composite normalized strength measure based on:

```text
HP capacity
Speed
Damage
Attack interval
Perception
Aggression
Courage
```

For attack interval, a lower value is treated as stronger.

Agents are grouped into three visual tiers.

This size is currently a visualization feature and does not itself change combat physics.

### 19.4 Dead Agents

Dead agents remain visible as small dark team-colored markers.

## 20. User Interface

### 20.1 InputField

`InputField` supports:

* text entry
* backspace
* Enter
* Escape
* mouse up arrow
* mouse down arrow
* parameter-specific step size

### 20.2 Team Parameters

Each team panel supports:

```text
Team size

Trait             center   width
HP
Speed
Damage
Attack
Perception
Aggression
Courage
```

### 20.3 Common Parameters

Current common controls:

```text
Cell size
Separation
Melee range
Local balance
```

### 20.4 Apply Behavior

GUI edits are not automatically applied to the running simulation.

`APPLY + RESET`:

1. validates fields
2. converts center/width to min/max
3. updates configuration objects
4. rebuilds the simulation
5. regenerates agents and obstacles

## 21. Simulation Controls

Keyboard:

| Key   | Function                  |
| ----- | ------------------------- |
| Space | Pause / play              |
| R     | Reset                     |
| G     | Grid on/off               |
| +     | Increase simulation speed |
| -     | Decrease simulation speed |
| Esc   | Exit                      |

Mouse buttons provide equivalent controls for:

* Pause / Play
* Reset
* Grid
* Simulation speed
* Apply + Reset

Simulation-speed multiplier is currently limited to approximately:

```text
0.25× to 4.0×
```

## 22. Time Model

Simulation movement uses delta time.

```python
position += velocity * dt
```

Therefore movement is not intended to depend directly on rendering FPS.

The raw delta time is capped at:

```text
0.05 seconds
```

to prevent unusually long frames from causing very large simulation jumps.

## 23. Performance Characteristics

Primary expected CPU costs include:

* spatial-grid rebuilding
* neighborhood searches
* target acquisition
* local balance evaluation
* separation evaluation
* per-agent Python loops
* Pygame Vector2 operations
* agent rendering

Target searches are intentionally staggered.

However, `_local_balance()` and separation still perform neighborhood searches for every living agent each update.

This remains a likely optimization target.

## 24. Current Technical Debt

The current implementation contains several areas that should eventually be improved.

### 24.1 Single-File Structure

Simulation, GUI, input, configuration, and rendering are currently combined.

### 24.2 Sequential Updates

Update order can affect battle outcome.

### 24.3 Global Enemy-Center Knowledge

Agents without local targets use information unavailable through local perception.

### 24.4 Reactive Obstacle Navigation

Agents do not perform pathfinding.

### 24.5 Dynamic Retreat Without State Memory

Agents may repeatedly switch between advance and retreat near the decision threshold.

### 24.6 Repeated Neighborhood Searches

Local balance and separation independently query nearby cells.

### 24.7 Unused Death-Record Infrastructure

`dead_positions` and the `_death_recorded` check currently do not provide meaningful functionality.

These should either be implemented fully or removed.

## 25. Recommended Future Architecture

```text
AlifeBattle/
├─ main.py
├─ config/
│  └─ settings.py
├─ simulation/
│  ├─ simulation.py
│  ├─ agent.py
│  ├─ spatial_grid.py
│  └─ world.py
├─ systems/
│  ├─ movement.py
│  ├─ combat.py
│  ├─ perception.py
│  ├─ morale.py
│  └─ navigation.py
├─ rendering/
│  ├─ renderer.py
│  └─ ui.py
├─ experiments/
│  └─ runner.py
├─ docs/
│  ├─ Design.md
│  ├─ Performance.md
│  └─ Experiments/
├─ tests/
├─ requirements.txt
└─ README.md
```

## 26. Development Roadmap

### Version 0.1 — Basic Prototype

Implemented:

* large agent populations
* movement
* targeting
* melee combat
* spatial grid
* visualization

### Version 0.2 — Interactive Experimentation

Largely implemented:

* RED/BLUE parameter editing
* independent team sizes
* center/width distributions
* mouse spin controls
* retreat visualization
* directional triangle rendering
* common simulation parameters

### Version 0.3 — Environment

Partially implemented:

* obstacle generation
* obstacle collision
* clustered terrain structures

Future:

* improved navigation around obstacles
* multiple terrain types
* movement cost

### Version 0.4 — Simulation Correctness

High priority:

* measure RED/BLUE win-rate bias
* eliminate update-order bias
* implement staged or simultaneous updates
* add deterministic random seeds for reproducible experiments

### Version 0.5 — Experiment Framework

Planned:

* headless simulation
* automatic repeated battles
* RED/BLUE win rates
* survivor counts
* damage statistics
* parameter sweeps
* CSV or JSON export

### Version 0.6 — Behavioral State Model

Planned:

```text
ADVANCE
FIGHT
RETREAT
RECOVER
ROUT
```

Potential additions:

* state persistence
* hysteresis
* morale

### Version 0.7 — Collective Organization

Planned:

* cohesion
* squad membership
* commanders
* information sharing
* formation tendencies

### Version 0.8 — Advanced Artificial Life

Planned:

* genome representation
* fitness evaluation
* selection
* mutation
* repeated generations

### Version 1.0 — Artificial-Life Battle Laboratory

Long-term objective:

```text
Local rules
+
Individual variation
+
Environment
+
Information limitations
+
Evolution
↓
Emergent collective behavior
```

## 27. Engineering Principles

### Principle 1 — Separate Rules from Emergent Results

If encirclement or formation behavior emerges, it should preferably result from local rules rather than explicit high-level commands.

### Principle 2 — Preserve Experimental Symmetry

RED and BLUE should follow equivalent computational rules unless an experiment intentionally changes them.

### Principle 3 — Avoid Unbounded Random Search

Any random placement or generation loop must have an explicit termination condition.

### Principle 4 — Separate Simulation and Visualization

Future experiments should be executable without Pygame rendering.

### Principle 5 — Measure Before Optimizing

Performance work should be based on profiling.

### Principle 6 — Make Experiments Reproducible

Future versions should support explicit random seeds and record parameter configurations.

## 28. Immediate Priorities

The recommended next three engineering tasks are:

1. **Remove update-order bias**

   * introduce staged decision and state application
   * verify symmetric RED/BLUE win rates

2. **Add automated experiment execution**

   * run identical configurations many times
   * record win rate and survivors

3. **Separate the current single-file implementation**

   * simulation
   * rendering
   * GUI
   * configuration

These changes will move AlifeBattle from a visual prototype toward a reliable artificial-life experimentation platform.
