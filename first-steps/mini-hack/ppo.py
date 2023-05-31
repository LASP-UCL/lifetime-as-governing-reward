# ppo.py
import torch
import torch.nn as nn

class PPOAgent(nn.Module):
    def __init__(self, actor_net, critic_net, optimizer_lr, ppo_clip, ppo_epochs, value_epochs, entropy_beta):
        super(PPOAgent, self).__init__()

        self.actor_net = actor_net
        self.critic_net = critic_net
        self.ppo_clip = ppo_clip
        self.ppo_epochs = ppo_epochs
        self.value_epochs = value_epochs
        self.entropy_beta = entropy_beta
        self.actor_optimiser = torch.optim.Adam(self.actor_net.parameters(), lr=optimizer_lr)
        self.critic_optimiser = torch.optim.Adam(self.critic_net.parameters(), lr=optimizer_lr)

    def update_actor(self, batch, save=False, save_path="saved-models/actor.pth"):
        # Update the policy by maximising the PPO-Clip objective
        entropy = self.actor_net.get_action(batch['state'], action=batch['action'])[2]
        for epoch in range(self.ppo_epochs):
            ratio = (batch['log_prob_action'] - batch['old_log_prob_action']).exp()
            clipped_ratio = torch.clamp(ratio, min=1 - self.ppo_clip, max=1 + self.ppo_clip)
            adv = batch['advantage']
            policy_loss = -torch.min(ratio * adv, clipped_ratio * adv).mean() - self.entropy_beta * entropy.mean()
            assert adv.shape == ratio.shape == clipped_ratio.shape
            self.actor_optimiser.zero_grad()
            policy_loss.backward()
            self.actor_optimiser.step()
            _, batch['log_prob_action'], entropy = self.actor_net.get_action(batch['state'], action=batch['action'].detach())
            batch['log_prob_action'] = batch['log_prob_action'].unsqueeze(-1)
            entropy = entropy.unsqueeze(-1)
        if save:
            self.actor_net.save(filename=save_path)

    def update_critic(self, batch, save=False, save_path="saved-models/critic.pth"):
        # Fit value function by regression on mean-squared error
        for epoch in range(self.value_epochs):
            value_loss = (batch['value'] - batch['reward_to_go']).pow(2).mean()
            self.critic_optimiser.zero_grad()
            value_loss.backward(retain_graph=True)
            self.critic_optimiser.step()
            batch['value'] = self.critic_net(batch['state'])
        if save:
            self.critic_net.save(filename=save_path)


