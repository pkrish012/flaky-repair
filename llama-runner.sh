#!/bin/bash
#SBATCH --partition=gpuq
#SBATCH --qos=gpu
#SBATCH --gres=gpu:A100.80gb:1
#SBATCH --job-name=flaky_repair_llama
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=160G
#SBATCH --time=09:00:00
#SBATCH --output=logs/run_%j.log

# 1. Load modules
module load gnu10
module load python/3.10.1-5r
module load cuda/12.6.3

# 2. Activate environment
source /scratch/pkrishn5/flaky_repair/venvs/repair_env/bin/activate

# 3. Hugging Face cache
export HF_HOME="/scratch/pkrishn5/flaky_repair/hf_cache"
export HF_TOKEN="your_token_here"
export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:128,expandable_segments:True"

# 4. PyTorch memory config
export PYTORCH_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false

# 5. Create logs
mkdir -p logs

# 6. Run LLaMA
python patch-gen.py ID-dataset.json llama #--ablate