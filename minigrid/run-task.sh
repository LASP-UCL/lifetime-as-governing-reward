#!/bin/bash

# Input Parameters
TASK_ID=${SGE_TASK_ID}
EXP_FILENAME=${EXP_FILENAME}
CSV_FILE="/cluster/project2/tithonus/msc-project/minigrid/$EXP_FILENAME"
START_SEED=${START_SEED}
NUM_SEEDS=${NUM_SEEDS}
NUM_TASKS=${NUM_TASKS}

# Calculate the seed and line number
seed=$((START_SEED + (TASK_ID - 1) / NUM_TASKS))
line_number=$(((TASK_ID - 1) % NUM_TASKS + 2))

echo "TASK_ID is: $TASK_ID"
echo "SEED is: $seed"
echo "Line number is: $line_number"

# Read the specific line from the csv file
LINE=$(sed "${line_number}q;d" $CSV_FILE)

# Parse the configuration
IFS=, read -r env_id wandb_project total_timesteps num_steps ent_coef time_cost action_cost final_reward_penalty cont_energy_wrapper time_bonus box_reward refuel_goal initial_energy gae_lambda <<< "$LINE"

# Determine the --cuda parameter based on the RESOURCE environment variable
if [ "$RESOURCE" = "gpu" ]; then
    cuda_option="--cuda true"
else
    cuda_option="--cuda false"
fi

# Determine the --cuda parameter based on the RESOURCE environment variable
if [ "$wandb_project" = "" ]; then
    wandb="false"
else
    wandb="true"
fi

# Create the experiment name
timestamp=$(date "+%m%d-%H%M%S.%3N")
exp_name="${timestamp}_${TASK_ID}_${seed}"

# Execute the command
echo "Executing: /cluster/project2/tithonus/miniconda3/bin/conda run -n minigrid python -u train.py --env-id $env_id --wandb $wandb --wandb-project $wandb_project --total-timesteps $total_timesteps --num-steps $num_steps --ent-coef $ent_coef --time-cost $time_cost --action-cost $action_cost --final-reward-penalty $final_reward_penalty --cont-energy-wrapper $cont_energy_wrapper --time-bonus $time_bonus --box-reward $box_reward --refuel-goal $refuel_goal --initial-energy $initial_energy --gae-lambda $gae_lambda --seed $seed --exp-name $exp_name $cuda_option"
cd /cluster/project2/tithonus/msc-project/minigrid
free -g
/cluster/project2/tithonus/miniconda3/bin/conda run -n minigrid python -u train.py --env-id $env_id --wandb $wandb --wandb-project $wandb_project --total-timesteps $total_timesteps --num-steps $num_steps --ent-coef $ent_coef --time-cost $time_cost --action-cost $action_cost --final-reward-penalty $final_reward_penalty --cont-energy-wrapper $cont_energy_wrapper --time-bonus $time_bonus --box-reward $box_reward --refuel-goal $refuel_goal --initial-energy $initial_energy --gae-lambda $gae_lambda --seed $seed --exp-name $exp_name $cuda_option
