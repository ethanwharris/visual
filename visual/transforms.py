import random
import math
import warnings

import torch
import torch.nn.functional as F

from .images import FFTImage


class Compose(object):
    """ Composes a number of Image transforms, similar to torchvision.transforms.Compose for torchvision transforms

    Args:
        transforms (list / tuple): Transforms to compose
    """
    def __init__(self, transforms):
        super(Compose, self).__init__()

        self._transforms = transforms

    def __call__(self, x):
        for transform in self._transforms:
            x = transform(x)
        return x


def _rand_select(xs, seed=None):
    xs = list(xs)
    if seed is not None:
        random.seed(a=seed)
    idx = random.randint(0, len(xs) - 1)
    return xs[idx]


def _as_4d(x):
    if x.dim() == 3:
        return x.unsqueeze(0)
    else:
        return x


def _as_3d(x):
    if x.dim() == 4:
        return x.squeeze(0)
    else:
        return x


class RandomScale(object):
    """ Transform that randomly scales the input from a set list of scales

    Args:
        scales (list / tuple): Set of scales that can be chosen
        mode (str): Interpolation mode. See `torch.nn.functional.interpolate <https://pytorch.org/docs/stable/nn.html?highlight=interpolate#torch.nn.functional.interpolate>`_
        align_corners (bool, optional): See `torch.nn.functional.interpolate`_
        seed: Random seed
    """
    def __init__(self, scales, mode='bilinear', align_corners=None, seed=None):
        self._scales = scales
        self._mode = mode
        self._align_corners = align_corners
        self._seed = seed

    @staticmethod
    def get_params(scales, seed=None):
        return _rand_select(scales, seed)

    def __call__(self, x):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Stop the annoying interpolate warning
            return _as_3d(F.interpolate(
                _as_4d(x),
                scale_factor=self.get_params(self._scales, self._seed),
                mode=self._mode,
                align_corners=self._align_corners
            ))


class RandomRotate(object):
    """ Image transform that randomly rotates the input from a set of possible angles

    Args:
        angles: Set and possible angles
        units: Rotation units. If 'degrees' ,'degs', 'deg' the use degrees, Else use radians
        mode: Interpolation mode. See `torch.nn.functional.grid_sample <https://pytorch.org/docs/stable/nn.html?highlight=grid%20sample#torch.nn.functional.grid_sample>`_
        padding_mode: Padding mode. See `torch.nn.functional.grid_sample`_
        seed: Random seed
    """
    def __init__(self, angles, units='degrees', mode='bilinear', padding_mode='zeros', seed=None):
        if units.lower() in ['degrees', 'degs', 'deg']:
            for i in range(len(angles)):
                angles[i] = math.pi * angles[i] / 180.
        self._angles = angles
        self._mode = mode
        self._padding_mode = padding_mode
        self._seed = seed

    @staticmethod
    def get_params(angles, seed=None):
        return _rand_select(angles, seed)

    def __call__(self, x):
        x = _as_4d(x)
        angle = self.get_params(self._angles, self._seed)

        theta = torch.zeros((1, 2, 3), device=x.device, dtype=x.dtype)
        theta[0, 0, 0] = math.cos(angle)
        theta[0, 1, 1] = math.cos(angle)
        theta[0, 0, 1] = math.sin(angle)
        theta[0, 1, 0] = -math.sin(angle)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Stop the annoying grid_sample warning
            grid = F.affine_grid(theta, x.size())

            return _as_3d(F.grid_sample(
                x,
                grid,
                mode=self._mode,
                padding_mode=self._padding_mode
            ))


class RandomAlpha(object):
    """ Image transform that creates a random alpha mask

    Args:
        sd:
        decay_power:
        colour: If True: Create a mask for each colour channel. Else create a single alpha channel
    """
    def __init__(self, sd=0.5, decay_power=1, colour=True):
        self._sd = sd
        self._decay_power = decay_power
        self._colour = colour

    def __call__(self, x):
        x = _as_3d(x)
        size = list(x.size())
        size[0] = size[0] - 1 if self._colour else 1
        random_image = FFTImage(size, correlate=self._colour, sd=self._sd, decay_power=self._decay_power, requires_grad=False).to(x.device).sigmoid().get_valid_image()
        alpha = x[-1].repeat(x.size(0) - 1, 1, 1)
        image = x[:-1] * alpha
        random_image = random_image * (1 - alpha)
        return image + random_image


class SpatialJitter(object):
    def __init__(self, pixels, seed=None):
        self._pixels = pixels
        self._seed = seed

    @staticmethod
    def get_params(pixels, seed=None):
        if seed is not None:
            random.seed(seed)
        return random.randint(0, pixels), random.randint(0, pixels)

    def __call__(self, img):
        img = _as_3d(img)
        x_offset, y_offset = self.get_params(self._pixels, self._seed)

        x_end = img.size(1) - (self._pixels - x_offset)
        y_end = img.size(2) - (self._pixels - y_offset)

        return img[:, x_offset:x_end, y_offset:y_end]
