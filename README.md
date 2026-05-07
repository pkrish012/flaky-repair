# Flaky Test Repair Prompt Generator

## Overview

This artifact evaluates LLM-based repair exclusively on **implementation-dependent (ID) flaky tests.**

Given a JSON dataset describing flaky tests, the script:

1. Parses each test entry.
2. Extracts relevant debugging metadata.
3. Constructs a structured LLM prompt.
4. Creates an organized output directory for each test.
5. Generates patch files (textual outputs only; patches are not automatically applied or validated within the repository) for each test instance containing the prompt and corresponding LLM-generated repair output.

The generated prompts are intended to be sent to LLMs (e.g., **LLaMA-3.3-70B-Instruct** or **Qwen-2.5-14B-Instruct**) to produce candidate test repairs.

*Note: All of the tests in the dataset run using Java 8*

---

# Repository File Descriptions

## Input JSON Object Partial Data Preparation

### Implementation-Dependent Data Preparation

#### `id_input_data.csv`
Raw extracted dataset used for implementation-dependent (ID) flaky test construction in CSV format. Each row corresponds to a test case and includes the following fields:

* **`ID`**: Identifier for flaky type (must be `ID`)
* **`Source Repository name`**: URL of the source repository
* **`Commit Hash`**: The full commit hash of the repository version where flakiness was found
* **`Module name`**: The module where the ID flaky test was found (use `.` if none)
* **`test name`**: The fully-qualified test name (e.g., `com.pkg.Class.testMethod`)
* **`directory`**: Local filesystem path to the cloned repository

---

#### `test_ID.csv`
A sample of the raw dataset used for implementation-dependent (ID) flaky test construction. The format is identical to `id_input_data.csv`.

---

#### `partial_data_prep_ID.py`
Script that converts raw CSV data into structured JSON used by the prompt generation pipeline.

This script takes ~11 minutes to run.

**Functionality:**
* Parses CSV input into structured test entries
* Executes each test using NonDex
* **Extracts critical data:**
  * Failure messages
  * Likely failing assertion lines
  * Test method source code
* Constructs standardized JSON output

**Assumptions:**
* Repositories are already cloned locally.
* Each repository is checked out to the correct commit.
* The NonDex Maven plugin is installed in the project `pom.xml`.

**Limitations:**
* Failure reproduction is best-effort due to nondeterminism.
* Advanced context fields (e.g., suspect lines) are not automatically generated.

**Suspect Line Extraction Policy**:

Suspect lines are identified using a structured, dependency-aware analysis of the failing assertion:

**(i) Assertion-Level Expression**  
The specific sub-expression within the assertion that produces the actual value under test.

**(ii) Data-Flow Dependencies**  
The most recent definitions and state-altering mutations of variables that directly influence the value computed by the assertion-level expression.

**(iii) API Boundary Calls**  
Method call(s) within the assertion-level expression that interface with the system under test (SUT), marking the boundary between test logic and production behavior.

**(iv) Nondeterministic Sources (ID Only)**  
Operations along the execution path of the assertion-level expression that are known sources of implementation-dependent behavior, including:

- **Unordered Collections:** Iteration, streaming, or element access over non-sequential types (e.g., `HashSet`, `HashMap`).
- **Dynamic Inspection:** Reflection-based retrieval of class members or annotations with unspecified ordering.
- **Environmental Inputs:** Dependence on external or volatile state (e.g., system time, file system ordering, or thread interleavings).

**Global Variables Extraction Policy**:

Global variables included in the schema are restricted to class-level fields, static constants, and shared state that are explicitly referenced within the failing test method or its identified suspect lines. By isolating only variables within the tests immediate dependency graph, the representation provides necessary state context while avoiding unrelated class members. Priority is given to variables that undergo state-altering mutations, as these represent the primary vectors of state pollution in implementation-dependent scenarios.

**Helper Methods Extraction Policy**:

Helper methods and inner classes encompass the supporting logic required for the test to remain a self-contained unit of reasoning. These include:

- **Utility Logic:** Private helper methods and inner classes invoked within the test body.
- **Lifecycle Hooks:** Setup and teardown routines (e.g., `@Before`, `@After`) that initialize or clean up the system under test.
- **Assertion Wrappers:** Custom assertion utilities used within the test.

## Candidate Patch Generation Pipeline files

### `patch-gen.py`
Core pipeline script that processes implementation-dependent (ID) flaky test datasets, constructs structured LLM prompts, and optionally queries LLMs (LLaMA-3.3-70B-Instruct or Qwen2.5-Coder-14B-Instruct). It outputs generated prompts and model responses into structured directories and supports ablation mode for reproduction-step removal experiments on ID tests.

Due to changes in project scope, the underlying pipeline was originally designed to support multiple flaky test types. Any functionality related to other flaky test types (e.g., OD) is present in the codebase but not used in this artifact and is excluded from evaluation. This artifact version focuses exclusively on implementation-dependent (ID) tests.

Depending on the mode (i.e. `qwen` or `llama`) this script can run anywhere from ~45 minutes to a couple hours on Hopper.

### `setup.sh`
Shell script that initializes the execution environment on a SLURM-based HPC cluster. It loads system modules, creates a Python 3.10 virtual environment in scratch storage, 
installs dependencies (PyTorch, Transformers, Accelerate, BitsAndBytes), and verifies CUDA availability.

### `llama_runner.sh`
SLURM job submission script for running the full pipeline using the LLaMA-3.3-70B-Instruct model. It loads the environment via setup.sh, sets authentication via HuggingFace token, and executes patch-gen.py on the ID dataset.

### `qwen_runner.sh`
SLURM job submission script for running the pipeline using the Qwen2.5-Coder-14B-Instruct model. It mirrors the LLaMA execution workflow but runs without authentication requirements.

### `ID-dataset.json`
Structured dataset of implementation-dependent flaky tests, including test code, reproduction steps, failure logs, and metadata required for prompt construction.

### `outputted-patches/`
This directory contains the generated candidate outputs for all dataset entries, generated using the pipeline described above. 
These outputs are included to support reproducibility without requiring re-execution.

Each file contains (1) the generated prompt and (2) the corresponding LLM output patch.

The original `outputs/` directory produced by `patch-gen.py` is provided here as `outputted-patches/` for reproducibility.

### `requirements.txt`
A set of requirements to install, via:
```bash
pip install -r requirements.txt
```

---

# Automated Partial Data Preparation Pipeline 

## Example Execution: ID Automated Partial Data Preparation

The following steps describe a complete reproduction of running the partial data preparation pipeline for implementation-dependent (ID) flaky tests.

This uses an example `test_ID.csv`:

### Step 1: Prepare Input CSV

Ensure that the input CSV file (`test_ID.csv`) is correctly formatted.

Each row must contain:

```csv
test_type, source, commit, module, test_info, directory
```

Example row, from `test_ID.csv`

```csv
ID,https://github.com/alibaba/fastjson,e05e9c5e4be580691cc55a59f3256595393203a1,.,com.alibaba.json.bvt.asm.SortFieldTest.test_1, fastjson-e05e9c5e4be580691cc55a59f3256595393203a1
```

Requirements:

* The repository must be cloned locally
  * The required repositories and commits correspond exactly to those listed in the CSV file.
* The repository must be checked out to the specified commit
* The directory field must point to the root of the cloned repository

### Step 2: Configure Repository for NonDex

For each repository listed in the CSV:

1. Clone the repository into a named folder

```bash
git clone https://github.com/alibaba/fastjson fastjson-e05e9c5e4be580691cc55a59f3256595393203a1
```

2. Navigate to the repository, and checkout the commit

```bash
cd fastjson-e05e9c5e4be580691cc55a59f3256595393203a1
git checkout e05e9c5e4be580691cc55a59f3256595393203a1
```

3. Add the NonDex Maven plugin to the build part of the pom.xml:

```xml
<plugin>
    <groupId>edu.illinois</groupId>
    <artifactId>nondex-maven-plugin</artifactId>
    <version>2.2.1</version>
</plugin>
```

4. Ensure JVM is properly configured (depends on the project). For the subjects tested, all are tested via Java 8.


### Step 3: Run Partial Data Preparation Script
Execute the script to convert CSV input into structured JSON:

**CRITICAL:** This script must be executed from the parent directory (outside of the cloned repository folder). The `directory` field in your CSV must correctly point to the relative path of the repository.

```bash
python partial_data_prep_ID.py test_ID.csv ID-sample.json
```

### Expected Execution Behavior

For each test entry, the script:

* Constructs a NonDex Maven command
* Executes the test under NonDex
* Captures console output
* Extracts:
  * error messages
  * failing assertion lines (best-effort)
* Extracts test method source code from the repository
* Builds a structured JSON object

### Example Console Output (Partial Data Preparation)

```
python .\partial_data_prep_ID.py .\test_ID.csv output.json
[RUNNING] mvn nondex:nondex -Dtest=com.alibaba.json.bvt.asm.SortFieldTest#test_1 -Drat.skip=true
[INFO] Partial execution note:
 - Some ID tests may not trigger a failure on a given run due to nondeterministic behavior, even under NonDex.
 - In such cases, no error message or failing assertion is recorded, as no failure signal is observed.
 - Non-triggering runs are expected for ID flaky tests and are retained as valid execution attempts.
 - A small subset of cases may require manual reproduction due to differences in the execution environment (e.g., JVM version) or inherent nondeterminism.
 - Suspect lines, global variables, and helper methods require interprocedural program analysis (e.g., call graph or data-flow analysis) and are therefore left for future work or external analysis tooling.
 ```

### Important Notes (Reproducibility Caveats)

* ID flaky tests are nondeterministic by nature
  * Some runs may not trigger failures, even under NonDex
  * In such cases, error fields may be empty

* The following fields are not automatically extracted:
  * suspect_lines
  * global_variables
  * helper_methods

* Some tests may fail to reproduce due to:
  * JVM version differences
  * environment-specific behavior
  * dependency mismatches

---

## Automation Scope and Manual Data Disclaimer

This artifact is currently designed to **reduce manual intervention** and automate the flaky test repair pipeline as much as possible.

### Fully Automated Components

The following steps are fully automated and reproducible:

* Best-effort execution of flaky tests (subject to nondeterminism)
* Extraction of:
  * Error messages
  * Failing assertion lines
  * Full test method source code
* Construction of the standardized reproduction steps
* Construction of structured JSON datasets
* Prompt generation and LLM-based patch generation

### Non-automated and out-of-scope components

The following fields are **not automatically generated** in this artifact:

* `suspect_lines`
* `global_variables`
* `helper_methods`

These require **interprocedural program analysis** (e.g., call graphs or data-flow analysis) for reliable extraction and are therefore left as manually obtained. The extraction policies for these fields are in the description of [partial_data_prep_ID.py](#partial-data-prep-idpy)

The following is **not automatically performed** by this artifact:

* Automatic application of generated patches to the original source repository
* Manual inspection of generated patches

#### Example illustrating acquiring suspect lines, global variables, and helper methods:
For `test_name` = `com.alibaba.json.bvt.asm.SortFieldTest.test_1`

```bash
public void test_1() throws Exception {
    V1 entity = new V1();

    String text = JSON.toJSONString(entity, SerializerFeature.SortField);
    System.out.println(text);

    // 按字段顺序输出
    // {"f1":0,"f2":0,"f3":0,"f4":0,"f5":0} 
    Assert.assertEquals("{\"f1\":0,\"f2\":0,\"f3\":0,\"f4\":0,\"f5\":0}", text);

    JSONObject object = JSON.parseObject(text);
    text = JSON.toJSONString(object, SerializerFeature.SortField);
    Assert.assertEquals("{\"f1\":0,\"f2\":0,\"f3\":0,\"f4\":0,\"f5\":0}", text);

}
```

The failing line (as per my collected results in `ID-dataset.json`) is `Assert.assertEquals("{\"f1\":0,\"f2\":0,\"f3\":0,\"f4\":0,\"f5\":0}", text);`

As per rule (i) and (ii) of the **Suspect Line Extraction Policy**, the value of text is = `JSON.toJSONString(object, SerializerFeature.SortField);`

Therefore, the `"suspect_lines"` field is  `[JSON.toJSONString(object, SerializerFeature.SortField);]`

The file containing the above test method has no global variables referenced by the test method. Therefore, the `"global_variables"` is `""`

Finally, as per the **Helper Methods Extraction Policy** the inter class V1 is invoked, therefore, the `"helper_methods"` field is `"public static class V1 {\n    private int f2;\n    private int f1;\n    private int f4;\n    private int f3;\n    private int f5;\n\n    public int getF2() { return f2; }\n    public void setF2(int f2) { this.f2 = f2; }\n    public int getF1() { return f1; }\n    public void setF1(int f1) { this.f1 = f1; }\n    public int getF4() { return f4; }\n    public void setF4(int f4) { this.f4 = f4; }\n    public int getF3() { return f3; }\n    public void setF3(int f3) { this.f3 = f3; }\n    public int getF5() { return f5; }\n    public void setF5(int f5) { this.f5 = f5; }\n}"`

Or, the entirety of the inner class V1.


### Summary

This artifact demonstrates a reproducible pipeline for prompt-based flaky test repair, with partial automation of data preparation and full automation of prompt and patch generation.

---

# Example Execution (End-to-End Patch Generation Pipeline Run)

The following steps describe a complete reproduction of the pipeline on a high-performance computing (HPC) cluster using SLURM.

---

### Step 1: Model Access Configuration (LLaMA only)

If using **LLaMA-3.3-70B-Instruct**, you must first configure HuggingFace authentication:

`export HF_TOKEN="your_token_here"`

This should be set on line 23 of the execution script `llama_runner.sh`. You must also ensure that you have been granted access to the 
**LLaMA-3.3-70B-Instruct** model on HuggingFace.

*Note: The **Qwen2.5-Coder-14B-Instruct** model does not require an authentication token.*

### Step 2: Environment Setup

On a SLURM-based HPC cluster (e.g., GMU Hopper), initialize the execution environment by running:

`bash setup.sh`

This script:
* Loads required system modules (Python, CUDA, GCC toolchain)
* Creates a Python 3.10 virtual environment in scratch storage
* Installs required dependencies (PyTorch, Transformers, Accelerate, BitsAndBytes)
* Verifies CUDA availability

#### Step 2a: Environment-specific paths

The runner scripts require environment-specific paths.

Update the following lines to match your environment before execution:

- `llama_runner.sh`
  - Line 19: path to the Python virtual environment
  - Line 22: path to the HuggingFace cache directory

- `qwen_runner.sh`
  - Line 19: path to the Python virtual environment
  - Line 22: path to the HuggingFace cache directory

#### Example:

```bash
# Example (llama_runner.sh)
# Change the <user> field to match your user name
source /scratch/<user>/flaky_repair/venvs/repair_env/bin/activate

export HF_HOME="/scratch/<user>/flaky_repair/hf_cache"
```

### Step 3: Job Submission (SLURM Execution)

Using LLaMA as an example, submit the batch job to the cluster:

`sbatch llama-runner.sh`

This job:
* Activates the virtual environment created in Step 2
* Runs patch-gen.py using ID-dataset.json as input
* Selects LLaMA-3.3-70B-Instruct as the inference model
* Generates structured prompts and LLM-based patches

**Optional:**
* To run ablation experiments, uncomment the ablation flag in llama-runner.sh (line 34)
* To run on a different dataset, modify the dataset path argument inside the same script

---

### Output Format

For each flaky test instance, the system produces an output file containing two main sections:

=== PROMPT ===

(Full structured prompt constructed from the JSON dataset, including metadata, 
reproduction steps, error traces, suspect lines, and full test code)

=== OUTPUT ===

(The LLM-generated patch corresponding to the input prompt)

Each test produces three independent candidate outputs, corresponding to three separate single-shot generations from the model
to account for generation variability. All results are written to structured directories under `outputs/`, organized by mode, dataset type, repository name, and test identifier.

An example of the directory structure is in [Output Directory Structure](#output-directory-structure)

### Example Console Output (Patch Generation Procedure)

```
Selected model: llama
Selected JSON file input: ID-dataset.json
Running in NORMAL mode
com.alibaba.json.bvt.asm.SortFieldTest.test_1
Loading weights: 100%|██████████| 723/723 [00:57<00:00, 12.68it/s]
com.alibaba.json.bvt.asm.SortFieldTest.test_1
Created file: outputs\normal\ID-candidates\fastjson-e05e9c5e4be580691cc55a59f3256595393203a1\com.alibaba.json.bvt.asm.SortFieldTest.test_1\e05e9c5e4be580691cc55a59f3256595393203a1__llamapatch1.txt
Created file: outputs\normal\ID-candidates\fastjson-e05e9c5e4be580691cc55a59f3256595393203a1\com.alibaba.json.bvt.asm.SortFieldTest.test_1\e05e9c5e4be580691cc55a59f3256595393203a1__llamapatch2.txt
Created file: outputs\normal\ID-candidates\fastjson-e05e9c5e4be580691cc55a59f3256595393203a1\com.alibaba.json.bvt.asm.SortFieldTest.test_1\e05e9c5e4be580691cc55a59f3256595393203a1__llamapatch3.txt
com.alibaba.json.bvt.issue_1100.Issue1177_1.test_for_issue
Created file: outputs\normal\ID-candidates\fastjson-e05e9c5e4be580691cc55a59f3256595393203a1\com.alibaba.json.bvt.issue_1100.Issue1177_1.test_for_issue\e05e9c5e4be580691cc55a59f3256595393203a1__llamapatch1.txt
Created file: outputs\normal\ID-candidates\fastjson-e05e9c5e4be580691cc55a59f3256595393203a1\com.alibaba.json.bvt.issue_1100.Issue1177_1.test_for_issue\e05e9c5e4be580691cc55a59f3256595393203a1__llamapatch2.txt
Created file: outputs\normal\ID-candidates\fastjson-e05e9c5e4be580691cc55a59f3256595393203a1\com.alibaba.json.bvt.issue_1100.Issue1177_1.test_for_issue\e05e9c5e4be580691cc55a59f3256595393203a1__llamapatch3.txt
...
```

---

# Supported Flaky Test Type

## ID (Implementation-Dependent)

Implementation-dependent flaky tests fail due to nondeterministic behavior in APIs or runtime environments.

Common causes include:

* unordered collections
* reflection ordering
* concurrency timing
* platform-dependent APIs

Typical fixes enforce deterministic ordering or remove assumptions about execution order.

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
  "od_or_id": "ID",
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

# Commit Hash Extraction

The commit hash is automatically extracted from the reproduction step:

```
Checkout commit <commit-hash>
```

This hash is used to build the output directory structure.

---

# Running the Candidate Patch Generation Script

Basic usage:

```bash
python patch-gen.py <json_file> <model>
```

Example:

```bash
python patch-gen.py ID-dataset.json llama
```

Supported models:

```
llama (LLaMA-3.3-70B-Instruct)
qwen  (Qwen2.5-Coder-14B-Instruct)
```

The selected model name is used for **file naming**, and **selecting the LLM to generate output patches**

---

# Ablation Mode

Ablation mode removes reproduction steps from the generated prompts.

Run with:

```bash
python patch-gen.py <json_file> <model> --ablate
```

Example:

```bash
python patch-gen.py dataset.json qwen --ablate
```

This produces prompts **without reproduction instructions**, allowing controlled experiments on prompt context.

---

# Output Directory Structure

Generated files are organized as follows:

```
outputs/
 ├── normal/
 │   └── ID-candidates/
 │       └── <repo>-<commit>/
 │            └── <test-name>/
 │                 ├── <commit>__<model>patch1.txt
 │                 ├── <commit>__<model>patch2.txt
 │                 └── <commit>__<model>patch3.txt
 │
 └── ablated/
      └── (same structure)
```

---

# Patch Files

Each test currently produces **three candidate patch files**:

```
patch1
patch2
patch3
```

These correspond to **multiple, single-shot LLM repair attempts** for the same test.

Currently, each file stores the **generated prompt** and the **generated repair patch**

In the case that the name set to the output file is too long, the first few package directories are **hashed**
using MD5.

---

# Prompt Structure

Prompts contain structured debugging evidence:

* test metadata
* flakiness description
* reproduction steps
* error information
* suspect lines
* code context

*Note: Reproduction Steps are not executed by the LLM. They serve solely as contextual information*

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

* JSON dataset parsing (evaluated on ID flaky tests)
* prompt generation
* directory organization
* patch file creation
* ablation mode
* LLM API integration
* manual patch integration and validation (performed outside this tool)

---

# Notes

* Existing files are **not overwritten**.
* The script skips already-generated patch files.
* All filesystem paths are sanitized to avoid invalid characters.

---

# Author

Prashanth Krishnan

Research prototype for automated flaky test repair using LLMs. Developed for Synergies of LLMs and SWE - Spring 2026
