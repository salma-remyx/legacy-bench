# Legacy-Bench

A benchmark for evaluating AI coding agents on legacy software engineering tasks.

The software that processes trillions in daily financial settlements, routes telephone calls across continents, and adjudicates insurance claims was written in COBOL, Fortran, and Java 7. The engineers who understand it are retiring faster than they can be replaced. Every major coding agent benchmark evaluates agents on modern Python and JavaScript. None of them reflect the reality of working with the world's most critical infrastructure.

Legacy-Bench measures how well frontier AI agents can maintain, debug, and modernize legacy code.

## Overview

Legacy-Bench consists of hundreds of tasks spanning six legacy language families and real enterprise domains. This repository contains ten representative public sample tasks. The full benchmark is available for evaluation -- contact [Factory](https://factory.ai/contact) for access.

| Language | % of Benchmark | Domains |
| --- | --- | --- |
| **COBOL** | 46% | Financial settlement, payroll processing, insurance claims, telecom billing, VSAM file handling |
| **Java 7** | 32% | Enterprise middleware, CDR processing, warehouse logistics, binary parsing, EJB patterns |
| **BASIC** | 6% | Business applications, accounting, data processing |
| **C89** | 5% | Systems programming, low-level debugging, protocol implementation |
| **Fortran** | 5% | Scientific computing, numerical methods, physics simulation |
| **Assembly** | 5% | x86 firmware parsing, protocol decoding, hardware simulation |

## Public Sample Tasks

| Task | Language | Type | Description |
| --- | --- | --- | --- |
| `1907c2` | C | fix/debug | Legacy buddy allocator fix |
| `16b04d` | COBOL | migration | Railroad retirement migration |
| `2831b5` | Java 7 | fix/debug | Rating engine repair |
| `3af1fe` | COBOL | fix/debug | Bond settlement reconciliation |
| `505812` | Java 7 | fix/debug | Inventory cost fix |
| `6fe1ab` | Java 7 | fix/debug | MTOM attachment corruption fix |
| `8e8098` | COBOL | fix/debug | Railcar settlement fix |
| `d1ddc1` | Fortran | migration | Lattice QCD migration to C++ |
| `ecf5e7` | x86-64 ASM | fix/debug | MZ/NE header parser fix |
| `fac397` | COBOL | migration | Batch interest migration |

## Task Structure

Each task directory follows the [Harbor](https://github.com/laude-institute/harbor) task format:

```
tasks/<task-id>/
  instruction.md    # What the agent must do
  task.toml         # Configuration (timeout, resources, etc.)
  environment/      # The legacy codebase and Dockerfile
  solution/         # Reference solution (oracle)
  tests/            # Verifier scripts run after the agent finishes
```

The agent receives `instruction.md` and the `environment/` directory. After the agent submits its changes, the verifier in `tests/` is executed inside the container to check correctness.

## Getting Started

### Prerequisites

- Docker
- [Harbor](https://github.com/laude-institute/harbor) (for automated evaluation)

### Install Harbor

```shell
pip install harbor
```

### Run the Oracle Solutions

Verify that the tasks and verifiers work by running the oracle:

```shell
harbor run --dataset legacy-bench \
  --agent oracle \
  --n-concurrent 4
```

### Run an Agent

```shell
export ANTHROPIC_API_KEY=<YOUR-KEY>
harbor run --dataset legacy-bench \
  --agent claude-code \
  --model anthropic/claude-opus-4-6 \
  --n-concurrent 4
```

Or any other Harbor-compatible agent. See the [Harbor documentation](https://github.com/laude-institute/harbor) for details on integrating custom agents.

### Run a Single Task Manually

Each task can also be run manually with Docker:

```shell
cd tasks/1907c2-c-debug-legacy-buddy-fix

# Build the container
docker build -t legacy-bench-1907c2 -f environment/Dockerfile environment/

# Run the container interactively
docker run -it legacy-bench-1907c2 /bin/bash

# After making changes inside the container, run the verifier
pytest tests/test_outputs.py
```

Refer to `task.toml` for task-specific settings (timeout, internet access, etc.).

## Results

Overall pass rates on the full benchmark range from 16.9% to 42.5% across 12 model-agent combinations evaluated. For context, these same frontier models score >70% on Terminal-Bench 2 and SWE-bench Verified.

Key findings:

- **Agent iteration works only where errors are visible.** Java 7 bug fixing scores highest because stack traces tell the agent what went wrong. COBOL bugs are silent -- wrong output looks correct.
- **Bug fixing outperforms implementation and migration.** Bug fixing scores roughly 2x higher than implementation, which scores roughly 2x higher than migration. Every model shows this pattern.
- **No single model wins.** Each model has categorical failures on entire language families. Rankings are inconsistent across task types.
- **Agents don't know when they're wrong.** In 97% of failures, the agent believes it has solved the task.

Read the full analysis: [factory.ai/news/legacy-bench](https://factory.ai/news/legacy-bench)

## License

This project is licensed under the Apache License 2.0 -- see the [LICENSE](LICENSE) file for details.

## Citation

```bibtex
@misc{legacybench2026,
  title={Legacy-Bench: A Benchmark for AI Agents on Legacy Software Engineering Tasks},
  author={Factory AI},
  year={2026},
  url={https://github.com/factory-ai/legacy-bench}
}
```

## Verifier scoring (continuous, decomposed)

In addition to the binary `reward.txt` written by each task's `test.sh`, a task's verifier may also emit `/logs/verifier/score.json`: a fine-grained, criteria-decomposed score with a per-requirement pass/fail and a short failure explanation. The deterministic oracle is unchanged and remains the source of ground truth; `score.json` is purely a diagnostic that turns a silent binary failure into a signal showing *which* requirement failed and *why* -- directly addressing the finding that agents rarely know when they are wrong. The scoring layer is an opt-in addition currently wired into the `2831b5-java7-rating-engine-repair` task; see `tasks/2831b5-java7-rating-engine-repair/tests/verifier_score.py`.
