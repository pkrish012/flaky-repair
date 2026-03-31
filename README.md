# Flaky Test Repair Prompt Generator

## Overview

This tool generates structured prompts for Large Language Models (LLMs) to repair **flaky tests**.
It supports both:

* **ID (Implementation-Dependent)** flaky tests
* **OD (Order-Dependent)** flaky tests

Given a JSON dataset describing flaky tests, the script:

1. Parses each test entry.
2. Extracts relevant debugging metadata.
3. Constructs a structured LLM prompt.
4. Creates an organized output directory for each test.
5. Generates placeholder patch files containing the prompt.

The generated prompts are intended to be sent to LLMs (e.g., **LLaMA** or **Qwen**) to produce candidate test repairs.

---

# Supported Flaky Test Types

## ID (Implementation-Dependent)

Implementation-dependent flaky tests fail due to nondeterministic behavior in APIs or runtime environments.

Common causes include:

* unordered collections
* reflection ordering
* concurrency timing
* platform-dependent APIs

Typical fixes enforce deterministic ordering or remove assumptions about execution order.

---

## OD (Order-Dependent)

Order-dependent flaky tests fail due to **interactions between tests**.

A **polluter test** modifies shared state that causes a **victim test** to fail when executed afterward.

Typical fixes include:

* isolating shared state
* resetting static fields
* cleaning environment state

---

# Input Dataset Format

The input JSON file must contain a single key mapping to an array of test objects:

```json
{
  "testdata": [
    { ... },
    { ... }
  ]
}
```

---

# ID Test Entry Format

```json
{
  "test_name": "com.example.TestClass.testA",
  "od_or_id": "IDA",
  "source": "https://github.com/example/project",
  "reproduction_steps": [
    "Clone the repository",
    "Checkout commit <commit-hash>",
    "Ensure Java <version-number> is active",
    "Run NonDex on the test: mvn nondex:nondex -Dtest=<package-location>#test-name",
    "Observe test failures in the console output"
  ],
  "error_messages": "...",
  "failing_lines": "...",
  "suspect_lines": ["..."],
  "global_variables": "...",
  "helper_methods": "...",
  "full_test_code": "..."
}
```

---

# OD Test Entry Format

```json
{
  "od_or_id": "OD",
  "source": "https://github.com/example/project",
  "reproduction_steps": [
    "Clone the repository",
    "Checkout commit <commit-hash>",
    "Ensure Java <version-number> is active",
    "Go to <directory>",
    "Execute Polluter <polluter-test>, then Victim <victim-test>",
    "Observe test failures in the console output"
  ],
  "victim_test_name": "com.example.TestClass.victimTest",
  "polluter_test_name": "com.example.TestClass.polluterTest",
  "error_messages": "...",
  "failing_lines": "...",
  "suspect_lines": ["..."],
  "global_variables": "...",
  "helper_methods": "...",
  "full_test_code": "..."
}
```

---

# Commit Hash Extraction

The commit hash is automatically extracted from the reproduction step:

```
Checkout commit <commit-hash>
```

This hash is used to build the output directory structure.

---

# Running the Script

Basic usage:

```bash
python generate_prompts.py <json_file> <model>
```

Example:

```bash
python generate_prompts.py dataset.json llama
```

Supported models:

```
llama
qwen
```

The selected model name is used only for **file naming** at this stage.

---

# Ablation Mode

Ablation mode removes reproduction steps from the generated prompts.

Run with:

```bash
python generate_prompts.py <json_file> <model> -ablate
```

Example:

```bash
python generate_prompts.py dataset.json qwen -ablate
```

This produces prompts **without reproduction instructions**, allowing controlled experiments on prompt context.

---

# Output Directory Structure

Generated files are organized as follows:

```
outputs/
 ├── normal/
 │   ├── ID-candidates/
 │   │   └── <repo>-<commit>/
 │   │        └── <test-name>/
 │   │             ├── <commit>__<model>patch1.txt
 │   │             ├── <commit>__<model>patch2.txt
 │   │             └── <commit>__<model>patch3.txt
 │   │
 │   └── OD-candidates/
 │        └── <repo>-<commit>/
 │             └── <victim>__<polluter>/
 │                  ├── <commit>__<model>patch1.txt
 │                  ├── <commit>__<model>patch2.txt
 │                  └── <commit>__<model>patch3.txt
 │
 └── ablated/
      └── (same structure)
```

---

# Patch Files

Each test produces **three candidate patch files**:

```
patch1
patch2
patch3
```

These correspond to **multiple LLM repair attempts** for the same test.

Currently, each file stores the **generated prompt**, as well as the **generated repair patch**.

---

# Prompt Structure

Prompts contain structured debugging evidence:

* test metadata
* flakiness description
* reproduction steps
* error information
* suspect lines
* code context

The model is required to produce output in a strict format including:

```
 //<fix start>
 ...
 //<fix end>
```

Optional sections include:

```
<!-- <pom.xml start> -->
```

and

```
 //<import start>
```

---

# Current Status

Implemented:

* JSON dataset parsing
* ID/OD differentiation
* prompt generation
* directory organization
* patch file creation
* ablation mode
* LLM API integration
* manual patch integration and validation (performed outside this tool)

---

# Example Execution

```
python generate_prompts.py dataset.json llama
```

Produces:

```
outputs/normal/ID-candidates/fastjson-<commit>/com.alibaba.../
```

with three candidate prompt files.

---

# Notes

* Existing files are **not overwritten**.
* The script skips already-generated patch files.
* All filesystem paths are sanitized to avoid invalid characters.

---

# Authors

Research prototype for automated flaky test repair using LLMs.
