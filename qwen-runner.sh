#!/bin/bash
#SBATCH --partition=gpuq          # The correct partition name
#SBATCH --qos=gpu                # REQUIRED for gpuq on Hopper
#SBATCH --gres=gpu:A100.80gb:1   # Specific syntax for the 80GB A100
#SBATCH --job-name=flaky_repair
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=logs/run_%j.log

# 1. Load the "Golden Stack" again
module load gnu10
module load python/3.10.1-5r
module load cuda/12.6.3

# 2. Activate environment
source /scratch/pkrishn5/flaky_repair/venvs/repair_env/bin/activate

# 3. Ensure HuggingFace is looking at scratch
export HF_HOME="/scratch/pkrishn5/flaky_repair/hf_cache"

# 4. Create logs directory if it doesn't exist
mkdir -p logs

# 5. Run your script
python patch-gen.py ID-dataset.json qwen #--ablate