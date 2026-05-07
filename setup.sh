#!/bin/bash

# 1. Load the GMU Hopper Module Stack (Order is important!)
module load gnu10
module load python/3.10.1-5r
module load cuda/12.6.3

# 2. Define Scratch Paths
SCRATCH_PATH="/scratch/$USER/flaky_repair"
VENV_PATH="$SCRATCH_PATH/venvs/repair_env"
export HF_HOME="$SCRATCH_PATH/hf_cache"

mkdir -p "$SCRATCH_PATH/hf_cache"
mkdir -p "$SCRATCH_PATH/venvs"

# 3. Virtual Environment Logic
# If the venv exists but was built with the wrong python, we rebuild it.
if [ -d "$VENV_PATH" ]; then
    VENV_PYTHON_VER=$( "$VENV_PATH/bin/python" --version 2>&1 | awk '{print $2}' )
    if [[ "$VENV_PYTHON_VER" != 3.10* ]]; then
        echo "Old Python version ($VENV_PYTHON_VER) detected. Rebuilding venv with 3.10..."
        rm -rf "$VENV_PATH"
    fi
fi

if [ ! -d "$VENV_PATH" ]; then
    echo "Creating Python 3.10 virtual environment in scratch..."
    python3 -m venv "$VENV_PATH"
fi

# 4. Activate and Install
source "$VENV_PATH/bin/activate"

echo "Updating pip and installing modern LLM libraries..."
pip install --upgrade pip
# We force newer versions to ensure Llama 3.3/Qwen 2.5 compatibility
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "Error: requirements.txt not found!"
    exit 1
fi

# 5. Final Sanity Check
echo "------------------------------------------------"
echo "SETUP SUCCESSFUL"
echo "Python: $(python --version)"
echo "HF_HOME: $HF_HOME"
echo "------------------------------------------------"
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"NONE\"}')"
echo "------------------------------------------------"