# trajectory.py
import torch
import numpy as np

MAX_PATIENCE = 1000

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

class TrajectoryCollector:
    def __init__(self, env, agent, discount_factor, trace_decay):
        self.env = env
        self.agent = agent
        self.discount_factor = discount_factor
        self.trace_decay = trace_decay
        self.timestep_history = []
        self.reward_history = []
        self.length_history = []

    def collect_trajectories(self, timesteps_per_batch):
        trajectories = []
        state = self.env.reset()
        state_tensor = torch.cat([torch.tensor(state[key], dtype=torch.float32) for key in state.keys()])
        timesteps = 0
        rewards = 0

        while len(trajectories) < timesteps_per_batch or not done:
            state_tensor = state_tensor.to(device)
            action, log_prob_action, _ = self.agent.actor_net.get_action(state_tensor)
            value = self.agent.critic_net(state_tensor)
            next_state, reward, done, _ = self.env.step(action.item())

            trajectories.append({'state': state_tensor.unsqueeze(0), 
                                'action': action.unsqueeze(0), 
                                'reward': torch.tensor([reward]), 
                                'done': torch.tensor([done], dtype=torch.float32), 
                                'log_prob_action': log_prob_action.unsqueeze(0), 
                                'old_log_prob_action': log_prob_action.unsqueeze(0).detach(), 
                                'value': value.unsqueeze(0)})

            timesteps += 1
            rewards += reward
            state = next_state
            state_tensor = torch.cat([torch.tensor(state[key], dtype=torch.float32) for key in state.keys()])

            if done:
                state = self.env.reset()
                state_tensor = torch.cat([torch.tensor(state[key], dtype=torch.float32) for key in state.keys()])

            if timesteps > timesteps_per_batch + MAX_PATIENCE: break # avoid infinite loops
                
        # Compute rewards-to-go R and advantage estimates based on the current value function V
        with torch.no_grad():
            reward_to_go, advantage, next_value = torch.tensor([0.]), torch.tensor([0.]), torch.tensor([0.])
            for episode_step in trajectories[::-1]:
                reward_to_go = episode_step['reward'] + self.discount_factor * reward_to_go
                episode_step['reward_to_go'] = reward_to_go
                TD_error = episode_step['reward'] + self.discount_factor * next_value - episode_step['value']
                advantage = TD_error +  self.discount_factor * self.trace_decay * advantage
                episode_step['advantage'] = advantage
                next_value = episode_step['value']
                if episode_step["done"]:
                    reward_to_go, next_value, advantage = torch.tensor([0.]), torch.tensor([0.]), torch.tensor([0.])

        # Batch trajectories
        batch = {k: torch.cat([trajectory[k] for trajectory in trajectories], dim=0) for k in trajectories[0].keys()}
        batch['advantage'] = (batch['advantage'] - batch['advantage'].mean()) / (batch['advantage'].std() + 1e-8)

        episodes_done = float(sum([trajectory['done'].item() for trajectory in trajectories]))
        average_reward = rewards / episodes_done
        average_episode_length = float(len(trajectories)) / episodes_done

        if len(self.timestep_history) == 0:
            self.timestep_history.append(timesteps)
        else:
            self.timestep_history.append(timesteps + self.timestep_history[-1])
        self.reward_history.append(average_reward)
        self.length_history.append(average_episode_length)

        info = {"timestep_history": self.timestep_history, 
                "reward_history": self.reward_history, 
                "length_history": self.length_history,
                "episodes_done": episodes_done}

        return batch, info

