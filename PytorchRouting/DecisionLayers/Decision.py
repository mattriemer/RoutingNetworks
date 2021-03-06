"""
This file defines class DecisionModule.

@author: Clemens Rosenbaum :: cgbr@cs.umass.edu
@created: 6/7/18
"""
import abc
import copy
import torch
import torch.nn as nn
import torch.nn.functional as F

from torch.distributions.distribution import Distribution

from .PolicyStorage import ApproxPolicyStorage, TabularPolicyStorage
from PytorchRouting.RewardFunctions.PerAction.PerActionBaseReward import PerActionBaseReward


class Decision(nn.Module, metaclass=abc.ABCMeta):
    """
    Class DecisionModule defines the base class for all decision modules.
    """

    def __init__(
            self,
            num_selections,
            in_features,
            num_agents=1,
            exploration=0.1,
            policy_storage_type='approx',
            detach=True,
            approx_hidden_dims=(),
            approx_module=None,
            additional_reward_func=PerActionBaseReward(),
            bellman_loss_func=F.smooth_l1_loss
        ):
        nn.Module.__init__(self)
        self._in_features = in_features
        self._num_selections = num_selections
        self._num_agents = num_agents
        self._exploration = exploration
        self._detach = detach
        self._pol_type = policy_storage_type
        self._pol_hidden_dims = approx_hidden_dims
        self._policy = self._construct_policy_storage(
            self._num_selections, self._pol_type, approx_module, self._pol_hidden_dims)
        self.additional_reward_func = additional_reward_func
        self.bellman_loss_func = bellman_loss_func

    def set_exploration(self, exploration):
        self._exploration = exploration

    @abc.abstractmethod
    def _forward(self, xs, mxs, prior_action):
        return torch.FloatTensor(1, 1), [], torch.FloatTensor(1, 1)

    @staticmethod
    @abc.abstractmethod
    def _loss(sample):
        pass

    def _construct_policy_storage(self, out_dim, policy_storage_type, approx_module, approx_hidden_dims):
        if policy_storage_type in ('approx', 0):
            if approx_module:
                policy = nn.ModuleList(
                    [ApproxPolicyStorage(approx=copy.deepcopy(approx_module), detach=self._detach)
                     for _ in range(self._num_agents)]
                )
            else:
                policy = nn.ModuleList(
                    [ApproxPolicyStorage(
                        in_features=self._in_features,
                        num_selections=out_dim,
                        hidden_dims=approx_hidden_dims,
                        detach=self._detach)
                        for _ in range(self._num_agents)]
                )
        else:
            policy = nn.ModuleList(
                [TabularPolicyStorage(num_selections=out_dim)
                for _ in range(self._num_agents)]
            )
        return policy

    def forward(self, xs, mxs, prior_actions=None):
        """
        The forward method of DecisionModule takes a batch of inputs, and a list of metainformation, and
        append the decision made to the metainformation objects.
        :param xs:
        :param mxs:
        :return:
        """
        if self._num_agents > 1:
            if prior_actions is None:
                raise ValueError('If multiple agents are available, argument '
                                 '`prior_actions` must be provided as a long Tensor of size '
                                 '(batch_size),\nwhere each entry determines the agent for '
                                 'that sample.')
            actions, dists, ys = [], [], []
            for x, mx, pa in zip(xs.split(1, dim=0), mxs, prior_actions):
                y, action, generating_dist = self._forward(x, [mx], pa)
                if len(generating_dist.size()) < 3:
                    # some "states" can be rank 2 (e.g. actor critic's policy value tuple). to make indexing
                    #   work the same all over, we thus want all states be of shape (batch x actiondim x sth)
                    generating_dist = generating_dist.unsqueeze(-1)
                actions.append(action)
                dists.append(generating_dist)
                ys.append(y)
            actions = torch.cat(actions, dim=0)
            dists = torch.cat(dists, dim=0)
            ys = torch.cat(ys, dim=0)
        else:
            ys, actions, dists = self._forward(xs, mxs, 0)

        actions = actions.reshape(-1)  # flattens the actions tensor, but does not produce a scalar

        for a, d, mx in zip(actions, dists.split(1, dim=0), mxs):
            mx.append('actions', a)
            mx.append('states', d)
            mx.append('loss_funcs', self._loss)
            mx.append('reward_func', self.additional_reward_func)
            # if len(d.size()) > 2 and d.size()[1] == 2:
            #     self.additional_reward_func.register(d[:, 0], actions)
            # else:
            self.additional_reward_func.register(d, a)
        return ys, mxs, actions

