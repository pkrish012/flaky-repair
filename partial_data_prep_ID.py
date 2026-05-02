import argparse, os, subprocess, re, json,csv

from pathlib import Path

# CONFIG
MVN_CMD = "mvn nondex:nondex"


# PARSING INPUT
def parse_csv_line(line):
    """
    Expected format:
    test_type, source, commit, module, test_info, directory
    """
    return {
        "test_type": line[0].strip(),
        "source": line[1].strip(),
        "commit": line[2].strip(),
        "module": line[3].strip(),
        "test_info": line[4].strip(),
        "directory": line[5].strip()
    }


# TEST FORMATTING
def to_maven_test(full_test_name: str) -> str:
    """
    com.pkg.Class.method -> com.pkg.Class#method
    """
    return full_test_name.rsplit(".", 1)[0] + "#" + full_test_name.rsplit(".", 1)[1]

# MAVEN COMMAND BUILDER
def build_maven_cmd(module: str, test: str):
    test_flag = f"-Dtest={to_maven_test(test)}"

    if module and module != ".":
        return f"{MVN_CMD} -pl {module} {test_flag} -Drat.skip=true"
    else:
        return f"{MVN_CMD} {test_flag} -Drat.skip=true"

# EXECUTION
def run_nondex(module, test_full_name, directory):
    cmd = build_maven_cmd(module, test_full_name)

    print(f"[RUNNING] {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=directory)

    return result.stdout + "\n" + result.stderr

# PARSERS
def extract_failing_line(full_test_code: str, error_message: str):
    if not error_message.strip():
        return ""
    
    assertions = get_assertion_lines(full_test_code)

    if not assertions:
        return ""

    # Score each assertion
    scored = [
        (line, score_assertion(line, error_message))
        for line in assertions
    ]

    if not scored:
        return ""

    # pick best match
    scored.sort(key=lambda x: x[1], reverse=True)

    best_line, best_score = scored[0]

    # fallback if no match
    if best_score == 0:
        return ""

    return extract_terminal_assertion(re.sub(r"\s+", " ", best_line).strip())

def get_assertion_lines(full_test_code: str):
    if not full_test_code:
        return []

    lines = full_test_code.splitlines()

    blocks = []
    current = []

    chain_open = False

    for line in lines:
        s = line.strip()

        # detect start of assertion chain
        if (
            ".andExpect" in s
            or "assert" in s
            or "expect" in s
        ):
            chain_open = True
            current.append(s)

        elif chain_open:
            # continuation of fluent chain
            current.append(s)

        # chain termination
        if chain_open and s.endswith(";"):
            blocks.append(" ".join(current))
            current = []
            chain_open = False

    return blocks

def extract_string_tokens(text: str):
    return re.findall(r'"(.*?)"', text)

def score_assertion(line: str, error_message: str):
    line_tokens = set(extract_identifiers(line))
    error_tokens = set(extract_identifiers(error_message))

    overlap = len(line_tokens & error_tokens)

    # boost assertion relevance
    if "assert" in line or "expect" in line:
        overlap += 2

    if "andExpect" in line:
        overlap += 1
    
    if "content()" in line:
        overlap += 2

    for s in extract_string_tokens(line):
        if any(s in em for em in error_message.split()):
            overlap += 3
        if s in error_message:
            overlap += 2

    # boost string-heavy assertions
    if '"' in line:
        overlap += 1

    return overlap

def extract_identifiers(line: str):
    """
    Extract variable-like tokens.
    """
    return re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", line)
    
def extract_terminal_assertion(block: str):
    parts = block.split(".andExpect")

    if len(parts) <= 1:
        return block.strip()

    # prefer last content/string assertions if present
    for p in reversed(parts):
        if "string(" in p or "content(" in p:
            return ".andExpect" + p.strip()

    return ".andExpect" + parts[-1].strip()

def extract_error_messages(output: str):
    """
    Extract first assertion failure and strip framework noise.
    Keeps only:
        expected:<...> but was:<...>
    """

    lines = output.splitlines()

    for i, line in enumerate(lines):

        l = line.strip()

        # detect failure signal
        if (
            "AssertionError" in l
            or "ComparisonFailure" in l
            or "expected" in l
        ):

            block = [l]

            # capture continuation (multi-line expected/but was)
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()

                if (
                    nxt.startswith("at ")
                    or "<<< FAILURE" in nxt
                    or "Tests run:" in nxt
                    or nxt == ""
                ):
                    break

                block.append(nxt)
                j += 1

            raw = " ".join(block)

            # strip leading exception type
            raw = re.sub(r"^[\w\.]+(Exception|Error|Failure):\s*", "", raw)

            # normalize whitespace
            raw = re.sub(r"\s+", " ", raw).strip()

            return raw

    return ""

def to_java_file_path(full_test_name: str):
    class_path = full_test_name.rsplit(".", 1)[0]
    return class_path.replace(".", "/") + ".java"

def load_test_file(directory: str, full_test_name: str):
    path = Path(directory) / "src/test/java" / to_java_file_path(full_test_name)

    if not path.exists():
        return ""

    return path.read_text(encoding="utf-8", errors="ignore")

def extract_test_method(full_file: str, method_name: str):
    """
    Extract a JUnit test method including @Test if directly associated.
    """

    if not full_file:
        return ""

    lines = full_file.splitlines()
    method_start = None

    for i, line in enumerate(lines):
        if re.search(rf"\b{re.escape(method_name)}\s*\(", line):
            method_start = i

            # Look ONE meaningful line above
            j = i - 1
            while j >= 0:
                prev = lines[j].strip() 
                # skip empty lines or comments
                if prev == "" or prev.startswith("//") or prev.startswith("/*") or prev.startswith("*"):
                    j -= 1
                    continue

                if "@Test" in prev:
                    method_start = j
                    
                break  # only check the first meaningful line

            break

    if method_start is None:
        return ""

    brace_count = 0
    result = []

    for line in lines[method_start:]:
        result.append(line)  # <-- ALWAYS append

        if "{" in line:
            brace_count += line.count("{")

        if "}" in line:
            brace_count -= line.count("}")
            if brace_count <= 0:
                break

    return "\n".join(result)

def get_java_version_num():
    """
    Retrieves the major Java version as an integer (e.g., 11).
    """
    try:
        result = subprocess.run(["java", "-version"], capture_output=True, text=True)
        # The version string is usually the first line in stderr
        first_line = result.stderr.splitlines()[0] 
        
        # This regex finds the first number. 
        # For "1.8.0...", it finds "1" then "8". 
        # For "11.0.12", it finds "11".
        version_parts = re.findall(r'\d+', first_line)
        
        if version_parts:
            major = version_parts[0]
            # Handle legacy '1.x' naming (1.8 -> 8)
            if major == "1" and len(version_parts) > 1:
                return int(version_parts[1])
            return int(major)
    except Exception:
        pass
    return 0 # Fallback for unknown

# CORE BUILDER
def build_id_json(row):
    module = row["module"].strip()
    source = row["source"].strip()
    commit = row["commit"].strip()
    test_full = row["test_info"].strip()
    directory = row["directory"].strip()

    full_file = load_test_file(directory, test_full)
    method_name = test_full.rsplit(".", 1)[1]
    full_test_code = extract_test_method(full_file, method_name)

    output = run_nondex(module, test_full, directory)

    maven_test = to_maven_test(test_full)

    # ONLY include module flag if meaningful
    if module and module != ".":
        maven_cmd = f"mvn -pl {module} nondex:nondex -Dtest={maven_test} -Drat.skip=true"
    else:
        maven_cmd = f"mvn nondex:nondex -Dtest={maven_test} -Drat.skip=true"

    error_message = extract_error_messages(output)

    failing_line = extract_failing_line(full_test_code, error_message)

    return {
        "test_name": test_full,
        "od_or_id": "ID",
        "source": source,
        "reproduction_steps": [
            "Clone the repository",
            f"Checkout commit {commit}",
            f"Ensure Java {get_java_version_num()} is active",
            f"Run NonDex on the test: {maven_cmd}",
            "Observe failure output in the console output"
        ],
        "error_messages": error_message,
        "failing_lines": failing_line,
        # Suspect lines, helper methods and globals still require a call graph to be accurate
        "suspect_lines": [],
        "global_variables": "",
        "helper_methods": "", 
        "full_test_code": full_test_code
    }

# PIPELINE
def process_csv(input_path, output_path):
    results = []

    with open(input_path, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            try:
                parsed = parse_csv_line(row)
                results.append(build_id_json(parsed))
            except Exception as e:
                print(f"[ERROR] {row}: {e}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"testdata": results}, f, indent=2, ensure_ascii=False)
    print("[INFO] Partial execution note:")
    print(" - Some ID tests may not trigger a failure on a given run due to nondeterministic behavior, even under NonDex.")
    print(" - In such cases, no error message or failing assertion is recorded, as no failure signal is observed.")
    print(" - Non-triggering runs are expected for ID flaky tests and are retained as valid execution attempts.")
    print(" - A small subset of cases may require manual reproduction due to differences in the execution environment (e.g., JVM version) or inherent nondeterminism.")
    print(" - Suspect lines, global variables, and helper methods require interprocedural program analysis (e.g., call graph or data-flow analysis) and are therefore left as manual steps.")

# ENTRY
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert ID CSV dataset to structured JSON format")

    parser.add_argument(
        "input_csv",
        help="Path to input CSV file (e.g., id_input_data.csv)"
    )

    parser.add_argument(
        "output_json",
        help="Path to output JSON file (e.g., ID-dataset.json)"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output JSON file if it already exists"
    )

    args = parser.parse_args()

    # Validate input file extension
    if not args.input_csv.lower().endswith(".csv"):
        print(f"[ERROR] Input file must be a .csv file: {args.input_csv}")
        exit(1)

    # Validate output file extension
    if not args.output_json.lower().endswith(".json"):
        print(f"[ERROR] Output file must be a .json file: {args.output_json}")
        exit(1)

    # Validate input file exists
    if not os.path.isfile(args.input_csv):
        print(f"[ERROR] Input file not found: {args.input_csv}")
        exit(1)

    # Prevent accidental overwrite
    if os.path.exists(args.output_json) and not args.force:
        print(f"[ERROR] Output file already exists: {args.output_json}")
        print("Use --force to overwrite.")
        exit(1)

    process_csv(args.input_csv, args.output_json)