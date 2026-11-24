"""Set the random seed of the project in one place."""

import random

import numpy as np


def set_seed(config: dict) -> int:
    """Seed the random number generators and return the seed.

    Input: the config dictionary, with a whole number under seed.
    Output: the seed, so a run can write it into its results. The standard
        library generator and the global numpy generator are seeded.
    """
    seed = config["seed"]
    random.seed(seed)
    np.random.seed(seed)
    return seed
