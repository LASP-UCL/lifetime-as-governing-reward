import gymnasium as gym
import torch
import time
import os
import argparse
import random
from datetime import datetime
from minigrid.wrappers import FullyObsWrapper, ReseedWrapper
from distutils.util import strtobool
import wandb

import numpy as np
import torch
import torch.optim as optim
#from torch.utils.tensorboard import SummaryWriter

from models import MiniGridAgent
from storage import TrajectoryCollector
from ppo import PPO
from utils import *
from customenvs import *

def parse_args():
    # fmt: off
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp-name", type=str, default="",
        help="the name of this experiment")
    parser.add_argument("--seed", type=int, default=1,
        help="seed of the experiment")
    parser.add_argument("--cuda", type=lambda x: bool(strtobool(x)), default=True, nargs="?", const=True,
        help="if toggled, cuda will be enabled by default")
    parser.add_argument("--plot", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
        help="whether to plot metrics and save")
    parser.add_argument("--verbose", type=lambda x: bool(strtobool(x)), default=True, nargs="?", const=True,
        help="whether to print metrics and training logs")
    parser.add_argument("--capture-video", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
        help="whether to capture videos of the agent performances (check out `videos` folder)")
    parser.add_argument("--wandb", type=lambda x: bool(strtobool(x)), default=True, nargs="?", const=True,
        help="whether to use wandb to log metrics")
    parser.add_argument("--wandb-project", type=str, default="experiments-test")


    # Algorithm specific arguments
    parser.add_argument("--env-id", type=str, default=f'MiniGrid-Empty-6x6-v0',
        help="the id of the environment")
    parser.add_argument("--fully-obs", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
        help="whether to use the fully observable wrapper")
    parser.add_argument("--time-cost", type=float, default=0,
        help="value of the time cost")
    parser.add_argument("--action-cost", type=float, default=0,
        help="value of the action cost")
    parser.add_argument("--time-bonus", type=float, default=0,
        help="value of the time bonus (only for EnergyBoxes env)")
    parser.add_argument("--box-reward", type=float, default=1,
        help="value of the box reward (only for EnergyBoxes env)")
    parser.add_argument("--cont-energy-wrapper", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
        help="whether to use continuous energy wrapper for Experiment 3")
    parser.add_argument("--refuel-goal", type=float, default=20,
        help="value of the refuel for reaching goal (only for Experiment 3)")
    parser.add_argument("--initial-energy", type=float, default=25,
        help="value of the initial energy (only for Experiment 3)")
    parser.add_argument("--final-reward-penalty", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
        help="If false, reward when goal is reached is +1. If true, a penalty is added for each step")
    parser.add_argument("--total-timesteps", type=int, default=1000000,
        help="total timesteps of the experiments")
    parser.add_argument("--learning-rate", type=float, default=2.5e-4,
        help="the learning rate of the optimizer")
    parser.add_argument("--num-envs", type=int, default=32,
        help="the number of parallel game environments")
    parser.add_argument("--num-steps", type=int, default=256,
        help="the number of steps to run in each environment per policy rollout")
    parser.add_argument("--anneal-lr", type=lambda x: bool(strtobool(x)), default=True, nargs="?", const=True,
        help="Toggle learning rate annealing for policy and value networks")
    parser.add_argument("--gamma", type=float, default=0.99,
        help="the discount factor gamma")
    parser.add_argument("--gae-lambda", type=float, default=0.95,
        help="the lambda for the general advantage estimation")
    parser.add_argument("--num-minibatches", type=int, default=16,
        help="the number of mini-batches")
    parser.add_argument("--update-epochs", type=int, default=4,
        help="the K epochs to update the policy")
    parser.add_argument("--norm-adv", type=lambda x: bool(strtobool(x)), default=True, nargs="?", const=True,
        help="Toggles advantages normalization")
    parser.add_argument("--clip-coef", type=float, default=0.2,
        help="the surrogate clipping coefficient")
    parser.add_argument("--clip-vloss", type=lambda x: bool(strtobool(x)), default=True, nargs="?", const=True,
        help="Toggles whether or not to use a clipped loss for the value function, as per the paper.")
    parser.add_argument("--ent-coef", type=float, default=0.01,
        help="coefficient of the entropy")
    parser.add_argument("--vf-coef", type=float, default=0.5,
        help="coefficient of the value function")
    parser.add_argument("--max-grad-norm", type=float, default=0.5,
        help="the maximum norm for the gradient clipping")
    parser.add_argument("--target-kl", type=float, default=None,
        help="the target KL divergence threshold")
    args = parser.parse_args()
    args.batch_size = int(args.num_envs * args.num_steps)
    args.minibatch_size = int(args.batch_size // args.num_minibatches)
    # fmt: on
    return args

def make_env(args, idx, run_name):
    def thunk():

        env_seed = args.seed + idx * 100

        if args.cont_energy_wrapper:
            env = gym.make(args.env_id)
            env = ContEnergyWrapper(env,
                                    refuel_goal=args.refuel_goal,
                                    initial_energy=args.initial_energy,
                                    time_bonus=args.time_bonus,
                                    goal_reward=args.box_reward)
            env = gym.wrappers.RecordEpisodeStatistics(env)
            #env = ReseedWrapper(env,  seeds=list(range(100000)), seed_idx=env_seed)
            return env


        if args.env_id == "MiniGrid-FourRooms-v0":
            env = gym.make(args.env_id, max_steps=1024)
        elif args.env_id == "EnergyBoxes":
            env = EnergyBoxesEnv(agent_start_dir="random",
                                agent_start_pos=(1,1),
                                time_bonus=args.time_bonus, 
                                box_open_reward=args.box_reward,
                                seed=env_seed)
        elif args.env_id == "EnergyBoxesHard":
            env = EnergyBoxesHardEnv(agent_start_dir="random",
                                agent_start_pos=(1,1),
                                time_bonus=args.time_bonus, 
                                box_open_reward=args.box_reward,
                                seed=env_seed)
        elif args.env_id == "EnergyBoxesDelay":
            env = EnergyBoxesDelayEnv(agent_start_dir="random",
                                agent_start_pos="random",
                                time_bonus=args.time_bonus, 
                                box_open_reward=args.box_reward,
                                seed=env_seed)
        else:
            env = gym.make(args.env_id)
        # get env max steps
        if args.fully_obs: env = FullyObsWrapper(env)
        if "Energy" not in args.env_id:
            env = TimeCostWrapper(env, 
                                time_cost=args.time_cost, 
                                action_cost=args.action_cost,
                                final_reward_penalty=args.final_reward_penalty,
                                noops_actions=[4,6])
        env = gym.wrappers.RecordEpisodeStatistics(env)
        #env = ReseedWrapper(env, seeds=list(range(100000)),seed_idx=env_seed)
        return env
    return thunk

args = parse_args()

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

timestamp = datetime.now().strftime("%m%d_%H%M%S")
if args.exp_name == "": run_name = timestamp
else: run_name = args.exp_name

num_updates = args.total_timesteps // args.batch_size

# Set up vectorised environments
print(args)
envs = gym.vector.SyncVectorEnv(
    [make_env(args, idx, run_name) for idx in range(args.num_envs)]
)

# Set seeds for reproducibility
random.seed(args.seed)
np.random.seed(args.seed)
torch.manual_seed(args.seed)
if args.cuda and torch.cuda.is_available():
    torch.cuda.manual_seed(args.seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

# Get dimension of a single transformed observation
obs_dim = get_state_tensor(envs.reset()[0])[0].shape

# Define agent
agent = MiniGridAgent(obs_dim, envs.single_action_space.n, n_channels=4).to(device)

# Define storage and ppo objects
is_boxes_env = args.env_id in ["EnergyBoxes", "EnergyBoxesHard", "EnergyBoxesDelay"]
storage = TrajectoryCollector(envs, obs_dim, agent, args, device, is_boxes_env=is_boxes_env)
ppo = PPO(agent, args, device)

os.makedirs(f'trained-models/{args.env_id}', exist_ok=True)
os.makedirs(f'figs/{args.env_id}', exist_ok=True)

if args.wandb:
    if is_boxes_env: 
        env_type = "Boxes"
    else:
        env_type = args.env_id.split('-')[1]
    wandb.init(project=args.wandb_project, 
               entity="nauqs",
               name=run_name, 
               config=args)
    wandb.config.update({"env_type": env_type})

timestep_history, return_history, length_history = [], [], []
if is_boxes_env: 
    cumulative_eat_counts = 0
    cumulative_red_counts = 0
    cumulative_blue_counts = 0
    cumulative_agent_distances = 0

# Run training algorithm
print("Start training...")
for update in range(1, num_updates+1):

    # Collect trajectories
    batch, stats = storage.collect_trajectories()

    # Update PPO agents (actor and critic)
    # TODO: return info (actor/critic loss, KL...)
    # TODO: lr annealing / schedule?
    ppo.update_ppo_agent(batch, save_path=f'trained-models/{args.env_id}/actor_{run_name}.pth')

    # Unifinished episodes
    if not is_boxes_env:
        if len(stats['episode_returns'])==0: 
            stats['episode_returns'] = np.array([0])
        if len(stats['episode_lengths'])==0:
            stats['episode_lengths'] = np.array([args.num_steps])
        if len(stats['episode_timesteps'])==0:
            stats['episode_timesteps'] = np.array([stats['initial_timestep']])
        
    # Print stats
    if args.verbose:
        print(f"\nTimestep: {stats['initial_timestep']}")
        if len(stats['episode_returns'])>0:
            # print stats with mean and std and 3 decimals
            print(f"Episodic return: {stats['episode_returns'].mean():.3f}±{stats['episode_returns'].std():.3f}")
            print(f"Episodic length: {stats['episode_lengths'].mean():.3f}±{stats['episode_lengths'].std():.3f}")
            if is_boxes_env: 
                print(f"Eat counts: {stats['eat_counts'].mean():.3f}±{stats['eat_counts'].std():.3f} "
                    f"(R {stats['red_counts'].mean():.2f} "
                    f"B {stats['blue_counts'].mean():.2f})")
                print(f"Agent distances: {stats['agent_distances'].mean():.3f}±{stats['agent_distances'].std():.3f}")
                #print(f"Consecutive boxes: {stats['consecutive_boxes'].mean():.3f}±{stats['consecutive_boxes'].std():.3f}")
                print(f"Mix rate: {stats['mix_rate'].mean():.3f}±{stats['mix_rate'].std():.3f}")

    # Plot stats
    if args.plot:

        timestep_history.append(stats['initial_timestep'])
        return_history.append((stats['episode_returns'].mean(), stats['episode_returns'].std()))
        length_history.append((stats['episode_lengths'].mean(), stats['episode_lengths'].std()))

        plot_logs(timestep_history, return_history, length_history, update,
            smooth=True,
            title=f'{args.env_id}',
            save_path=f'figs/{args.env_id}/ppo_{args.env_id}_{run_name}.png')
        
    # Log metrics to wandb
    if args.wandb:
        if is_boxes_env:
            cumulative_eat_counts += stats['eat_counts'].sum()
            cumulative_red_counts += stats['red_counts'].sum()
            cumulative_blue_counts += stats['blue_counts'].sum()
            cumulative_agent_distances += stats['agent_distances'].sum()
            cumulative_consecutive_boxes = stats['consecutive_boxes'].sum()

            wandb.log({
                "average_return": stats['episode_returns'].mean(),
                "average_length": stats['episode_lengths'].mean(),
                "average_eat_count": stats['eat_counts'].mean(),
                "cumulative_eat_count": cumulative_eat_counts,
                "average_red_count": stats['red_counts'].mean(),
                "cumulative_red_count": cumulative_red_counts,
                "average_blue_count": stats['blue_counts'].mean(),
                "cumulative_blue_count": cumulative_blue_counts,
                "average_agent_distance": stats['agent_distances'].mean(),
                "cumulative_agent_distance": cumulative_agent_distances,
                "average_consecutive_boxes": stats['consecutive_boxes'].mean(),
                "cumulative_consecutive_boxes": cumulative_consecutive_boxes,
                "average_mix_rate": stats['mix_rate'].mean(),
                "timestep": stats['initial_timestep'],
            })
        else:
            extra_metrics = {}
            if args.cont_energy_wrapper:
                extra_metrics["goal_counts"] = stats['goal_counts'].mean()
                extra_metrics["subepisode_length"] = (stats['goal_counts'] / stats['episode_lengths']).mean()
            wandb.log({
                "average_return": stats['episode_returns'].mean(),
                "average_length": stats['episode_lengths'].mean(),
                "success_rate": (stats['episode_returns'] > 0).astype(int).mean(),
                "timestep": stats['initial_timestep'],
                **extra_metrics
            })
        for i in range(len(stats['episode_returns'])):
            wandb.log({
                "episode_timestep": stats['episode_timesteps'][i],
                "episode_return": stats['episode_returns'][i],
                "episode_length": stats['episode_lengths'][i],
            })


