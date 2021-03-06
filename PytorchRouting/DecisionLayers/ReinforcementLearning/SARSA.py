"""
This file defines class REINFORCE.

@author: Clemens Rosenbaum :: cgbr@cs.umass.edu
@created: 6/7/18
"""
import torch.nn.functional as F

from .QLearning import QLearning


class SARSA(QLearning):
    """
    SARSA on-policy q-function learning.
    """
    def _loss(self, sample):
        if sample.next_action is not None:
            target = sample.next_state.data[:, sample.next_action] - sample.reward
        else:
            target = sample.cum_return
        target = target.detach()
        return self.bellman_loss_func(sample.state[:, sample.action].squeeze(), target.squeeze()).unsqueeze(0)
