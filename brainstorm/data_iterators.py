#!/usr/bin/env python
# coding=utf-8
from __future__ import division, print_function, unicode_literals
from datetime import datetime
import math
import numpy as np
import sys
from brainstorm.randomness import Seedable
from brainstorm.utils import IteratorValidationError
from brainstorm.handlers._cpuop import _crop_images


def progress_bar(maximum, prefix='[',
                 bar='====1====2====3====4====5====6====7====8====9====0',
                 suffix='] Took: {0}\n'):
    i = 0
    start_time = datetime.utcnow()
    out = prefix
    while i < len(bar):
        progress = yield out
        j = math.trunc(progress / maximum * len(bar))
        out = bar[i: j]
        i = j
    elapsed_str = str(datetime.utcnow() - start_time)[: -5]
    yield out + suffix.format(elapsed_str)


def silence():
    while True:
        _ = yield ''


class DataIterator(object):
    def __init__(self, data_names):
        self.data_names = data_names

    def __call__(self, handler, verbose=False):
        pass


class AddGaussianNoise(DataIterator, Seedable):
    """
    Adds Gaussian noise to data generated by another iterator, which must
    provide named data items (such as Online, Minibatches, Undivided). Only
    Numpy data is supported,

    Supports usage of different means and standard deviations for different
    named data items.
    """

    def __init__(self, iter, std_dict, mean_dict=None, seed=None):
        """
        :param iter: any DataIterator to which noise is to be added
        :type iter: DataIterator
        :param std_dict: specifies the standard deviation of noise added to
        each named data item
        :type std_dict: dict[unicode, int]
        :param mean_dict: specifies the mean of noise added to each named
        data item
        :type mean_dict: dict[unicode, int]
        :param seed: random seed
        """
        Seedable.__init__(self, seed=seed)
        DataIterator.__init__(self, iter.data_names)
        if mean_dict is not None:
            assert set(mean_dict.keys()) == set(std_dict.keys()), \
                "means and standard deviations must be provided for " \
                "the same data names"
        for key in std_dict.keys():
            if key not in iter.data.keys():
                raise IteratorValidationError(
                    "key {} is not present in iterator. Available keys: {"
                    "}".format(key, iter.data.keys()))
            if not isinstance(iter.data[key], np.ndarray):
                raise IteratorValidationError(
                    "data with name {} is not a numpy.ndarray".format(key))

        self.mean_dict = {} if mean_dict is None else mean_dict
        self.std_dict = std_dict
        self.iter = iter

    def __call__(self, handler, verbose=False):
        for data in self.iter(handler, verbose=verbose):
            for key in self.std_dict.keys():
                mean = self.mean_dict.get(key, 0.0)
                std = self.std_dict.get(key)
                data[key] = data[key] + std * self.rnd.standard_normal(
                    data[key].shape) + mean
            yield data


class Flip(DataIterator, Seedable):
    """
    Randomly flip images horizontally. Images are generated by another
    iterator, which must provide named data items (such as Online,
    Minibatches, Undivided). Only 5D Numpy data is supported.

    Defaults to flipping the 'default' named data item with a probability
    of 0.5. Note that the last dimension is flipped, which typically
    corresponds to flipping images horizontally.
    """

    def __init__(self, iter, prob_dict=None, seed=None):
        """

        :param iter: any DataIterator which iterates over data to be flipped
        :type iter: DataIterator
        :param prob_dict: specifies the probability of flipping for some
        named data items
        :type prob_dict: dict[unicode, float]
        :param seed: random seed
        """
        Seedable.__init__(self, seed=seed)
        DataIterator.__init__(self, iter.data_names)
        prob_dict = {'default': 0.5} if prob_dict is None else prob_dict
        for key in prob_dict.keys():
            if key not in iter.data.keys():
                raise IteratorValidationError(
                    "key {} is not present in iterator. Available keys: {"
                    "}".format(key, iter.data.keys()))
            if prob_dict[key] > 1.0 or prob_dict[key] < 0.0:
                raise IteratorValidationError("Invalid probability")
            if not isinstance(iter.data[key], np.ndarray):
                raise IteratorValidationError(
                    "data with name {} is not a numpy.ndarray".format(key))
            if len(iter.data[key].shape) != 5:
                raise IteratorValidationError("Only 5D data is supported")
        self.prob_dict = prob_dict
        self.iter = iter

    def __call__(self, handler, verbose=False):
        for data in self.iter(handler, verbose=verbose):
            for name in self.prob_dict.keys():
                if self.rnd.random_sample() < self.prob_dict[name]:
                    data[name] = data[name][..., ::-1]
            yield data


class Pad(DataIterator, Seedable):
    """
    Pads images equally on all sides. Images are generated by another
    iterator, which must provide named data items (such as Online,
    Minibatches, Undivided). Only 5D Numpy data is supported.

    5D data corresponds to sequences of multi-channel images, which is the
    typical use case. Zero-padding is used unless specified otherwise.
    """

    def __init__(self, iter, size_dict, value_dict=None, seed=None):
        """

        :param iter: any DataIterator which iterates over data to be flipped
        :type iter: DataIterator
        :param size_dict: specifies the padding sizes for some named data items
        :type size_dict: dict[unicode, int]
        :param value_dict: specifies the pad values for some named data items
        :type value_dict: dict[unicode, int]
        :param seed: random seed
        """
        Seedable.__init__(self, seed=seed)
        DataIterator.__init__(self, iter.data_names)
        if value_dict is not None:
            if set(size_dict.keys()) != set(value_dict.keys()):
                raise IteratorValidationError(
                    "padding sizes and values must be provided for the same "
                    "data names")
        for key in size_dict.keys():
            if key not in iter.data.keys():
                raise IteratorValidationError(
                    "key {} is not present in iterator. Available keys: {"
                    "}".format(key, iter.data.keys()))
            if not isinstance(iter.data[key], np.ndarray):
                raise IteratorValidationError(
                    "data with name {} is not a numpy.ndarray".format(key))
            if len(iter.data[key].shape) != 5:
                raise IteratorValidationError("Only 5D data is supported")
        self.value_dict = {} if value_dict is None else value_dict
        self.size_dict = size_dict
        self.iter = iter

    def __call__(self, handler, verbose=False):
        for data in self.iter(handler, verbose=verbose):
            for name in self.size_dict.keys():
                t, b, c, h, w = data[name].shape
                size = self.size_dict[name]
                val = self.value_dict.get(name, 0.0)
                new_data = val * np.ones((t, b, c, h + 2 * size, w + 2 * size))
                new_data[:, :, :, size: -size, size: -size] = data[name]
                data[name] = new_data
            yield data


class RandomCrop(DataIterator, Seedable):
    """
    Randomly crops image data. Images are generated by another
    iterator, which must provide named data items (such as Online,
    Minibatches, Undivided). Only 5D Numpy data is supported.

    5D data corresponds to sequences of multi-channel images, which is the
    typical use case.
    """

    def __init__(self, iter, shape_dict, seed=None):
        """

        :param iter: any DataIterator which iterates over data to be flipped
        :type iter: DataIterator
        :param shape_dict: specifies the crop shapes for some named data items
        :type shape_dict: dict[unicode, tuple]
        :param seed: random seed
        """
        Seedable.__init__(self, seed=seed)
        DataIterator.__init__(self, iter.data_names)
        for key, val in shape_dict.items():
            if key not in iter.data.keys():
                raise IteratorValidationError(
                    "key {} is not present in iterator. Available keys: {"
                    "}".format(key, iter.data.keys()))
            if not isinstance(iter.data[key], np.ndarray):
                raise IteratorValidationError(
                    "data with name {} is not a numpy.ndarray".format(key))
            if len(iter.data[key].shape) != 5:
                raise IteratorValidationError("Only 5D data is supported")
            if not (isinstance(val, tuple) and len(val) == 2):
                raise IteratorValidationError("Shape must be a size 2 tuple")
            data_shape = iter.data[key].shape
            if val[0] > data_shape[3] or val[0] < 0:
                raise IteratorValidationError("Invalid crop height")
            if val[1] > data_shape[4] or val[1] < 0:
                raise IteratorValidationError("Invalid crop width")
        self.shape_dict = shape_dict
        self.iter = iter

    def __call__(self, handler, verbose=False):
        for data in self.iter(handler, verbose=verbose):
            for name in self.shape_dict.keys():
                crop_h, crop_w = self.shape_dict[name]
                batch_size = data[name].shape[1]
                max_r = data[name].shape[3] - crop_h
                max_c = data[name].shape[4] - crop_w
                row_indices = self.rnd.random_integers(0, max_r, batch_size)
                col_indices = self.rnd.random_integers(0, max_c, batch_size)
                cropped = np.zeros(data[name].shape[:3] + (crop_h, crop_w))
                _crop_images(data[name], crop_h, crop_w, row_indices,
                             col_indices, cropped)
                data[name] = cropped
            yield data


class Undivided(DataIterator):
    """
    Processes the entire data in one block (only one iteration).
    """

    def __init__(self, **named_data):
        """
        :param named_data: named arrays with 3+ dimensions ('T', 'B', ...)
        :type named_data: dict[str, ndarray]
        """
        super(Undivided, self).__init__(named_data.keys())
        _ = _assert_correct_data_format(named_data)
        self.data = named_data
        self.total_size = int(sum(d.size for d in self.data.values()))

    def __call__(self, handler, verbose=False):
        yield self.data


class Online(DataIterator, Seedable):
    """
    Online (one sample at a time) iterator for inputs and targets.
    """

    def __init__(self, shuffle=True, verbose=None, seed=None, **named_data):
        Seedable.__init__(self, seed=seed)
        DataIterator.__init__(self, named_data.keys())
        self.nr_sequences = _assert_correct_data_format(named_data)
        self.data = named_data
        self.shuffle = shuffle
        self.verbose = verbose
        self.sample_size = int(sum(d.shape[0] * np.prod(d.shape[2:])
                                   for d in self.data.values()))

    def __call__(self, handler, verbose=False):
        if (self.verbose is None and verbose) or self.verbose:
            p_bar = progress_bar(self.nr_sequences)
        else:
            p_bar = silence()

        print(next(p_bar), end='')
        sys.stdout.flush()
        indices = np.arange(self.nr_sequences)
        if self.shuffle:
            self.rnd.shuffle(indices)
        for i, idx in enumerate(indices):
            data = {k: v[:, idx: idx + 1]
                    for k, v in self.data.items()}
            yield data
            print(p_bar.send(i + 1), end='')
            sys.stdout.flush()


class Minibatches(DataIterator, Seedable):
    """
    Minibatch iterator for inputs and targets.

    Only randomizes the order of minibatches, doesn't shuffle between
    minibatches.
    """

    def __init__(self, batch_size=10, shuffle=True, verbose=None,
                 seed=None, **named_data):
        Seedable.__init__(self, seed=seed)
        DataIterator.__init__(self, named_data.keys())
        self.nr_sequences = _assert_correct_data_format(named_data)
        self.data = named_data
        self.shuffle = shuffle
        self.verbose = verbose
        self.batch_size = batch_size
        self.sample_size = int(
            sum(d.shape[0] * np.prod(d.shape[2:]) * batch_size
                for d in self.data.values()))

    def __call__(self, handler, verbose=False):
        if (self.verbose is None and verbose) or self.verbose:
            p_bar = progress_bar(self.nr_sequences)
        else:
            p_bar = silence()

        print(next(p_bar), end='')
        sys.stdout.flush()
        indices = np.arange(
            int(math.ceil(self.nr_sequences / self.batch_size)))
        if self.shuffle:
            self.rnd.shuffle(indices)
        for i, idx in enumerate(indices):
            chunk = (slice(None),
                     slice(idx * self.batch_size, (idx + 1) * self.batch_size))

            data = {k: v[chunk] for k, v in self.data.items()}
            yield data
            print(p_bar.send((i + 1) * self.batch_size), end='')
            sys.stdout.flush()


def _assert_correct_data_format(named_data):
    nr_sequences = {}
    nr_timesteps = {}
    for name, data in named_data.items():
        if not hasattr(data, 'shape'):
            raise IteratorValidationError(
                "{} has a wrong type. (no shape attribute)".format(name)
            )
        if len(data.shape) < 3:
            raise IteratorValidationError(
                'All inputs have to have at least 3 dimensions, where the '
                'first two are time_size and batch_size.')
        nr_sequences[name] = data.shape[1]
        nr_timesteps[name] = data.shape[0]

    if min(nr_sequences.values()) != max(nr_sequences.values()):
        raise IteratorValidationError(
            'The number of sequences of all inputs must be equal, but got {}'
                .format(nr_sequences))
    if min(nr_timesteps.values()) != max(nr_timesteps.values()):
        raise IteratorValidationError(
            'The number of time steps of all inputs must be equal, '
            'but got {}'.format(nr_timesteps))

    return min(nr_sequences.values())
