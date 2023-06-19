import os
import gymnasium as gym
import torch
import numpy as np
import wandb
import argparse
from minigrid.wrappers import FullyObsWrapper
from utils import get_state_tensor
from distutils.util import strtobool


def evaluate_agent(env, agent, num_episodes, verbose=True):
    total_returns = []
    episode_lengths = []

    for i in range(num_episodes):
        state = env.reset()[0]
        episode_return = 0
        episode_length = 0

        while True:
            state['image'] = state['image'].reshape(1, *state['image'].shape)
            state['direction'] = np.array([state['direction']])
            obs = get_state_tensor(state)
            action = agent.get_action_and_value(obs)[0].item()
            state, reward, terminated, truncated, info = env.step(action)

            episode_return += reward
            episode_length += 1

            if terminated or truncated:
                total_returns.append(episode_return)
                episode_lengths.append(episode_length)
                if verbose: print(f'Episode {i+1} return: {episode_return}, length: {episode_length}')
                break

    return total_returns, episode_lengths


if __name__ == '__main__':
    # Argument parsing
    parser = argparse.ArgumentParser(description='Evaluate an agent')
    parser.add_argument('--env-id', type=str, required=True,
                        help='the id of the environment')
    parser.add_argument("--fully-obs", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
                        help="whether to use the fully observable wrapper")
    parser.add_argument('--num-episodes', type=int, default=100,
                        help='number of episodes for evaluation')
    parser.add_argument("--verbose", type=lambda x: bool(strtobool(x)), default=True, nargs="?", const=True,
                        help="whether to print metrics and training logs")
    parser.add_argument("--wandb", type=lambda x: bool(strtobool(x)), default=False, nargs="?", const=True,
                        help="whether to use wandb to log metrics")


    args = parser.parse_args()

    # Environment setup
    env = gym.make(args.env_id)
    if args.fully_obs:
        env = FullyObsWrapper(env)

    # Loading agent model
    model_dir = os.path.join('trained-models', args.env_id)
    model_files = [f for f in os.listdir(model_dir) if f.endswith('.pth')]
    agent_model_path = os.path.join(model_dir, model_files[0]) # TODO: take first one for now
    agent = torch.load(agent_model_path)

    # Wandb initialization
    if args.wandb:
        wandb.init(project="action-cost-experiments", 
                    entity="nauqs",
                    config=args)

    # Evaluation
    total_returns, episode_lengths = evaluate_agent(env, agent, args.num_episodes, verbose=args.verbose)

    # Logging results to wandb
    if args.wandb:
        wandb.log({
            "total_returns": total_returns,
            "average_return": sum(total_returns) / len(total_returns),
            "episode_lengths": episode_lengths,
            "average_episode_length": sum(episode_lengths) / len(episode_lengths)
        })

    if args.verbose:
        print(f'Average return: {sum(total_returns) / len(total_returns)}')
        print(f'Average episode length: {sum(episode_lengths) / len(episode_lengths)}')

    # Close the environment
    env.close()
