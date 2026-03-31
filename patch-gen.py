import argparse, json, sys, re, os

from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from huggingface_hub import login
import torch

MODEL_CACHE = {}

def load_model(model_name):
    if model_name in MODEL_CACHE:
        return MODEL_CACHE[model_name]

    hf_token = os.getenv("HF_TOKEN") if model_name == "llama" else None

    if model_name == "llama":
        model_id = "meta-llama/Meta-Llama-3-8B-Instruct"
        if not hf_token:
            raise RuntimeError("HF_TOKEN environment variable not set for LLaMA access")

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )

        tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # single-GPU load
        load_kwargs = {
            "quantization_config": bnb_config,
            "trust_remote_code": True,
            "token": hf_token,
            "device_map": {"": "cuda:0"}  # load entirely on GPU 0
        }

        model = AutoModelForCausalLM.from_pretrained(model_id, **load_kwargs)

    elif model_name == "qwen":
        model_id = "Qwen/Qwen2.5-Coder-14B-Instruct"
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto")
    else:
        raise ValueError(f"Unsupported model: {model_name}")

    MODEL_CACHE[model_name] = (tokenizer, model)
    return tokenizer, model

def run_llm(prompt, model_name):
    tokenizer, model = load_model(model_name)

    # Tokenize prompt
    inputs = tokenizer(prompt, return_tensors="pt")

    device = model.device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=1536,
            temperature=0.1,
            top_p=0.95,
            do_sample=True,
            repetition_penalty=1.15,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id
        )

    input_len = inputs["input_ids"].shape[1]
    output_text = tokenizer.decode(output_ids[0][input_len:], skip_special_tokens=True)

    return output_text

def read_and_parse_json(json_path, ablate, model):
    # Step 1: Read JSON
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: JSON file not found: {json_path}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in {json_path}")
        sys.exit(1)

    # Step 2: Get array of test entries
    top_key = list(data.keys())[0]
    entries = data[top_key]

    # Step 3: Iterate and extract variables
    for entry in entries:
        flaky_type = entry.get("od_or_id", "UNKNOWN")
        source = entry.get("source", "")
        repo_name = source.rstrip("/").split("/")[-1]
        reproduction_steps = entry.get("reproduction_steps", [])
        
        victim_test = ""
        polluter_test = ""

        # parse commit hash from 2nd step
        commit_hash = None
        if len(reproduction_steps) > 1:
            match = re.search(r"Checkout commit (\w+)", reproduction_steps[1])
            if match:
                commit_hash = match.group(1)
        
        if flaky_type == "OD":
            victim_test = entry.get("victim_test_name", "")
            polluter_test = entry.get("polluter_test_name", "")
            test_identifier = f"{victim_test} + {polluter_test}"
        else:
            test_identifier = entry.get("test_name", "")

        # Adjust reproduction steps if ablation flag is on
        if ablate:
            reproduction_steps_to_use = []  # remove reproduction steps in ablation mode
        else:
            reproduction_steps_to_use = reproduction_steps

        # DYNAMIC FOLDER CREATION
        create_folders_and_files(flaky_type, ablate, test_identifier, repo_name, commit_hash, model,
                                entry.get("test_name", ""),
                                victim_test,
                                polluter_test,
                                reproduction_steps_to_use,
                                entry.get("error_messages", ""),
                                entry.get("failing_lines", ""),
                                entry.get("suspect_lines", []),
                                entry.get("global_variables", ""),
                                entry.get("helper_methods", ""),
                                entry.get("full_test_code", "")
                                )

def create_folders_and_files(flaky_type, ablate, test_identifier, repo_name, commit_hash, model,
                            test_name, victim_test, polluter_test, reproduction_steps, error_messages,
                            failing_lines, suspect_lines, global_variables, helper_methods, full_test_code):
    mode_dir = "ablated" if ablate else "normal"
    type_dir = "OD-candidates" if flaky_type == "OD" else "ID-candidates"

    # sanitize identifier for filesystem
    safe_identifier = test_identifier.replace(" ", "_").replace("+", "__")

    repo_commit_dir = f"{repo_name}-{commit_hash}"

    base_dir = os.path.join(
        "outputs",
        mode_dir,
        type_dir,
        repo_commit_dir,
        safe_identifier
    )

    os.makedirs(base_dir, exist_ok=True)

    # Create placeholder patch files
    for i in range(1, 4):

        filename = f"{commit_hash}__{model}patch{i}.txt"
        filepath = os.path.join(base_dir, filename)

        if not os.path.exists(filepath):

            # Prompt creation
            prompt_content = build_prompt(flaky_type, test_name, victim_test, polluter_test, reproduction_steps,
                                          error_messages, failing_lines, suspect_lines, global_variables, helper_methods,
                                          full_test_code, ablate)
            # RUN LLM
            llm_output = run_llm(prompt_content, model)

            # SAVE OUTPUT
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("=== PROMPT ===\n")
                f.write(prompt_content)
                f.write("\n\n=== OUTPUT ===\n")
                f.write(llm_output)

            print(f"Created file: {filepath}")

        else:
            print(f"Skipped existing file: {filepath}")

def build_prompt(flaky_type, test_name, victim_test, polluter_test, reproduction_steps,
                error_messages, failing_lines, suspect_lines, global_variables, helper_methods,
                full_test_code, ablate):
    prompt = ""

    prompt += "You are a software testing expert specializing in debugging and repairing flaky tests.\n"
    prompt += "Your task is to fix a flaky test using structured execution evidence.\n\n"

    prompt += "TEST METADATA:\n"
    prompt += f"Flaky Type: {flaky_type}\n"

    if flaky_type == "ID":
        prompt += f"Test Name: {test_name}\n"

    if flaky_type == "OD":
        prompt += "ORDER-DEPENDENT CONTEXT:\n"
        prompt += f"Victim Test: {victim_test}\n"
        prompt += f"Polluter Test: {polluter_test}\n"

    prompt += "\nFLAKINESS DESCRIPTION:\n"

    if flaky_type == "ID":
        prompt += (
            "ID flaky tests are caused by APIs or logic that assume deterministic ordering or stable execution behavior.\n"
            "Examples include unordered collections, reflection order, concurrency timing, or platform-dependent APIs.\n"
            "Fixes typically enforce deterministic ordering or remove nondeterministic assumptions.\n"
        )
    else:
        prompt += (
            "Order-dependent flaky tests fail due to interactions between tests through shared state.\n"
            "A polluter test modifies state that causes a victim test to fail.\n"
            "Fixes typically remove shared state dependencies or isolate tests.\n"
        )

    if not ablate:
        prompt += "\nREPRODUCTION STEPS:\n"
        prompt += "Steps required to reproduce failure:\n"

        for i, step in enumerate(reproduction_steps, start = 1):
            prompt += f"{i}. {step}\n"

    prompt += "\nERROR INFORMATION:\n"
    prompt += f"Error Messages: {error_messages}\n"
    prompt += f"Failing Lines: {failing_lines}\n"
    if isinstance(suspect_lines, list):
        suspect_lines = "\n".join(suspect_lines)

    prompt += f"Potential Flaky Lines: {suspect_lines}\n"

    prompt += "\nCODE CONTEXT:\n"
    prompt += f"Relevant Global Variables: {global_variables}\n"
    prompt += f"Relevant Helper Methods: {helper_methods}\n"
    prompt += f"Relevant Test Code: {full_test_code}\n"

    prompt += """
    INSTRUCTIONS - STRICT OUTPUT FORMAT:
    Follow steps below. Output raw code only. Do NOT use markdown code fences (```). Do NOT include ``` anywhere in your output. 
    Do not write explanations.

    1) Fix the flakiness and print the fixed complete method code of this test between:
        //<fix start>
        CODE HERE
        //<fix end>

        Requirements:
        - Code must compile and use correct argument and variable types.
        - Do NOT invent any classes, methods, or APIs not already present in the test or provided code context.
        - Do NOT suppress assertion failures with try-catch.
        - Make minimal changes; preserve the original test logic unless absolutely necessary.
        - Fix nondeterminism at the source (e.g., ordering, shared state, API usage).
        - Only wrap or modify the existing flaky API usage; do NOT bypass it.
        - Do NOT manually reconstruct expected outputs or JSON strings.
        - Only use reflection if it is already present in the test.

    2) If dependencies must be updated, output:
        <!-- <pom.xml start> -->
        DEPENDENCY HERE
        <!-- <pom.xml end> -->

        Rules:
        - Provide exact version
        - Do not duplicate existing dependencies
        - Do not include project artifacts

    3) If imports must be added, output:
        //<import start>
        IMPORTS HERE
        //<import end>

        Assume all existing classes and imports are already correctly configured.
    """
    return prompt

def main():
    parser = argparse.ArgumentParser(description="Generate LLM prompts for flaky test repair")

    # JSON input
    parser.add_argument(
        "json_file",
        help="Path to flaky test JSON file"
    )

    # Model selection (required positional argument)
    parser.add_argument(
        "model",
        choices=["llama", "qwen"],
        help="LLM model to use (llama or qwen)"
    )

    # Ablation flag (optional)
    parser.add_argument(
        "--ablate",
        action="store_true",
        help="Run in ablation mode (remove reproduction steps)"
    )

    args = parser.parse_args()

    model = args.model
    ablate = args.ablate
    json_path = args.json_file

    print(f"Selected model: {model}")
    print(f"Selected JSON file input: {json_path}")

    if ablate:
        print("Running in ABLATION mode")
    else:
        print("Running in NORMAL mode")

    read_and_parse_json(json_path, ablate, model)

if __name__ == "__main__":
    main()