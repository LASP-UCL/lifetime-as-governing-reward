import torch
import numpy as np
import time
from utils import get_state_tensor

MAX_PATIENCE = 1000

class TrajectoryCollector:
    def __init__(self, envs, obs_dim, agent, args, device, is_boxes_env=False):
        self.envs = envs
        self.agent = agent
        self.args = args
        self.device = device
        self.obs_dim = tuple(obs_dim)
        self.is_boxes_env = is_boxes_env

        self.obs = torch.zeros((self.args.num_steps, self.args.num_envs) + self.obs_dim).to(device)
        self.actions = torch.zeros((self.args.num_steps, self.args.num_envs) + envs.single_action_space.shape).to(device)
        self.logprobs = torch.zeros((self.args.num_steps, self.args.num_envs)).to(device)
        self.rewards = torch.zeros((self.args.num_steps, self.args.num_envs)).to(device)
        self.dones = torch.zeros((self.args.num_steps, self.args.num_envs)).to(device)
        self.values = torch.zeros((self.args.num_steps, self.args.num_envs)).to(device)
        self.global_step = 0

    def collect_trajectories(self):
        
        stats = {'initial_timestep': self.global_step}
        episode_returns, episode_lengths, episode_timesteps = [], [], []
        if self.is_boxes_env: 
            red_counts, blue_counts, agent_distances, consecutive_boxes, mix_rates = [], [], [], [], []
        goal_counts = []
        state = self.envs.reset()[0]
        next_obs = get_state_tensor(state).to(self.device)
        next_done = torch.zeros(self.args.num_envs).to(self.device)

        for step in range(0, self.args.num_steps):
            self.global_step += 1 * self.args.num_envs
            self.obs[step] = next_obs
            self.dones[step] = next_done

            with torch.no_grad():
                action, logprob, _, value = self.agent.get_action_and_value(next_obs)
                self.values[step] = value.flatten()
            self.actions[step] = action
            self.logprobs[step] = logprob

            next_state, reward, truncated, terminated, info = self.envs.step(action.cpu().numpy())
            next_obs = get_state_tensor(next_state)
            done = truncated | terminated
            self.rewards[step] = torch.tensor(reward).to(self.device).view(-1)
            next_obs = next_obs.to(self.device)
            next_done = torch.Tensor(done).to(self.device)

            # info is a dict with final_info and final_observation for the envs which reached a terminal state
            # everything else is None in the others
            if 'final_info' in info:
                for env_final_info in info['final_info']:
                    if env_final_info is not None:
                        if self.is_boxes_env: 
                            red_counts.append(env_final_info['red_count'])
                            blue_counts.append(env_final_info['blue_count'])
                            agent_distances.append(env_final_info['agent_distance'])
                            consecutive_boxes.append(env_final_info['consecutive_boxes'])
                            mix_rates.append(env_final_info['mix_rate'])

                        episode_returns.append(env_final_info['episode']['r'].item())
                        episode_lengths.append(env_final_info['episode']['l'].item())
                        episode_timesteps.append(self.global_step)
                        if "goal_counts" in env_final_info:
                            goal_counts.append(env_final_info['goal_counts'])

        with torch.no_grad():
            next_value = self.agent.get_value(next_obs).reshape(1, -1)
            advantages = torch.zeros_like(self.rewards).to(self.device)
            lastgaelam = 0
            for t in reversed(range(self.args.num_steps)):
                if t == self.args.num_steps - 1:
                    nextnonterminal = 1.0 - next_done
                    nextvalues = next_value
                else:
                    nextnonterminal = 1.0 - self.dones[t + 1]
                    nextvalues = self.values[t + 1]
                delta = self.rewards[t] + self.args.gamma * nextvalues * nextnonterminal - self.values[t]
                advantages[t] = lastgaelam = delta + self.args.gamma * self.args.gae_lambda * nextnonterminal * lastgaelam
            returns = advantages + self.values

        batch = {'obs': self.obs.reshape((-1,) + self.obs_dim),
                    'log_probs': self.logprobs.reshape(-1),
                    'actions': self.actions.reshape((-1,) + self.envs.single_action_space.shape),
                    'advantages': advantages.reshape(-1),
                    'returns': returns.reshape(-1),
                    'values': self.values.reshape(-1)}
        
        stats['episode_returns'] = np.array(episode_returns)
        stats['episode_lengths'] = np.array(episode_lengths)
        stats['episode_timesteps'] = np.array(episode_timesteps)
        stats['final_timestep'] = self.global_step
        if self.is_boxes_env: 
            stats['red_counts'] = np.array(red_counts)
            stats['blue_counts'] = np.array(blue_counts)
            stats['eat_counts'] = stats['red_counts']+stats['blue_counts']
            stats['agent_distances'] = np.array(agent_distances)
            stats['consecutive_boxes'] = np.array(consecutive_boxes)
            stats['mix_rate'] = np.array(mix_rates)
        if len(goal_counts) > 0:
            stats['goal_counts'] = np.array(goal_counts)
        
        return batch, stats