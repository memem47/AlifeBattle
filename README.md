# AlifeBattle

AlifeBattle is a real-time many-agent battle simulation written in Python.

The initial prototype simulates approximately 1,000 agents versus 1,000 agents. Each soldier acts as an independent agent and makes decisions primarily from local battlefield information.

The long-term goal is to explore whether collective behaviors such as battle-line formation, retreat, concentration of forces, and encirclement can emerge from simple agent-level rules.

## Current Features

* 1,000 vs. 1,000 agent simulation
* Real-time visualization with Pygame
* Individual movement and combat behavior
* Local enemy detection
* Spatial-grid-based neighborhood search
* Agent variation in parameters such as movement speed and combat ability
* Pause, restart, simulation-speed, and grid-display controls

## Requirements

* Python 3.12 or 3.13 recommended
* Pygame 2.6 or later

Install dependencies with:

```bash
python -m pip install -r requirements.txt
```

## Running

Create and activate a virtual environment on Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the simulator:

```powershell
python alife_battle.py
```

## Controls

| Key   | Action                    |
| ----- | ------------------------- |
| Space | Pause / resume            |
| R     | Restart simulation        |
| G     | Toggle spatial grid       |
| +     | Increase simulation speed |
| -     | Decrease simulation speed |
| Esc   | Exit                      |

## Project Structure

```text
AlifeBattle/
├─ alife_battle.py
├─ requirements.txt
├─ README.md
├─ .gitignore
└─ docs/
   └─ Design.md
```

The detailed architecture and development roadmap are described in `docs/Design.md`.

## Development Direction

The current version is a prototype.

Planned development includes:

* performance profiling and optimization
* improved collective behavior
* morale and retreat
* limited perception
* squads and commanders
* multiple unit types
* terrain
* evolutionary algorithms
* larger simulations using NumPy, Numba, or GPU computation

The core design principle is to avoid directly programming high-level tactics wherever possible. Instead, the project aims to observe tactics emerging from interactions between simple autonomous agents.
