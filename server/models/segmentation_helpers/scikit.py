#!/usr/bin/env python
# -*- coding: utf-8 -*-

import collections
import itertools
from six import BytesIO

import numpy
import skimage.io
import skimage.measure
import skimage.morphology
import skimage.segmentation

from .base import BaseSegmentationHelper


class ScikitSegmentationHelper(BaseSegmentationHelper):
    @classmethod
    def loadImage(cls, image_data_stream):
        """
        Load an image into an RGB array.
        :param image_data_stream: A file-like object containing the encoded
        (JPEG, etc.) image data.
        :type image_data_stream: file-like object
        :return: A Numpy array with the RGB image data.
        :rtype: numpy.ndarray
        """
        return skimage.io.imread(image_data_stream)


    @classmethod
    def writeImage(cls, image, encoding='png'):
        image_stream = BytesIO()
        skimage.io.imsave(image_stream, image, format_str=encoding)
        return image_stream


    @classmethod
    def segment(cls, image, seed_coord, tolerance):
        mask_image = cls._floodFill(
            image,
            seed_coord,
            tolerance,
            connectivity=8
        )
        # mask_image = cls._binaryOpening(mask_image)
        contour_coords = cls._maskToContour(mask_image)
        return contour_coords


    @classmethod
    def _clippedAdd(cls, array, value):
        type_info = numpy.iinfo(array.dtype)
        new_array = array.astype(int)
        new_array += value
        return new_array.clip(type_info.min, type_info.max).astype(array.dtype)


    @classmethod
    def _floodFill(cls, image, seed_coord, tolerance, connectivity=8):
        seed_value = image[seed_coord[1], seed_coord[0]]
        seed_value_min = cls._clippedAdd(seed_value, -tolerance)
        seed_value_max = cls._clippedAdd(seed_value, tolerance)

        if connectivity == 4:
            connectivity_arg = 1
            pass
        elif connectivity == 8:
            connectivity_arg = 2
        else:
            raise ValueError('Unknown connectivity value.')

        mask_image = skimage.measure.label(
            numpy.all(
                numpy.logical_and(
                    image >= seed_value_min,
                    image <= seed_value_max
                ),
                2
            ).astype(int),
            return_num=False,
            connectivity=connectivity_arg
        )

        mask_image = numpy.equal(
            mask_image, mask_image[seed_coord[1], seed_coord[0]])
        return mask_image


    @classmethod
    def _binaryOpening(cls, image, element_shape='circle', element_radius=5):
        element_size = (element_radius * 2) - 1
        element_type = image.dtype

        if element_shape == 'circle':
            element = skimage.morphology.disk(element_size, element_type)
        elif element_shape == 'cross':
            element = numpy.zeros((element_size, element_size), element_type)
            element[:, element_size // 2] = element_type.type(True)
            element[element_size // 2, :] = element_type.type(True)
        elif element_shape == 'square':
            element = skimage.morphology.square(element_size, element_type)
        else:
            raise ValueError('Unknown element shape value.')

        morphed_image = skimage.morphology.binary_opening(
            image=image,
            selem=element
        )
        return morphed_image


    @classmethod
    def _collapseCoords(cls, coords):
        collapsed_coords = [coords[0]]
        collapsed_coords.extend([
            coord
            for prev_coord, coord, next_coord in itertools.izip(coords[0:], coords[1:], coords[2:])
            if numpy.cross(next_coord - prev_coord, coord - prev_coord) != 0
        ])
        collapsed_coords.append(coords[-1])
        collapsed_coords = numpy.array(collapsed_coords)
        return collapsed_coords


    @classmethod
    def _maskToContour(cls, mask_image):
        """
        Extract the contour line within a segmented label mask, using
        Scikit-Image.

        :param mask_image: A binary label mask.
        :type mask_image: numpy.ndarray of bool
        :return: An array of point pairs.
        :rtype: numpy.ndarray
        """
        if mask_image.dtype != bool:
            raise TypeError('mask_image must be an array of bool.')

        coords = skimage.measure.find_contours(
            array=mask_image.astype(numpy.double),
            level=0.5,
            fully_connected='low',
            positive_orientation='low'
        )
        coords = numpy.fliplr(coords[0])
        coords = cls._collapseCoords(coords)
        return coords


    @classmethod
    def _contourToMask(cls, image, coords):
        mask_image = skimage.measure.grid_points_in_poly(
            shape=image.shape[:2],
            verts=numpy.fliplr(coords)
        )
        return mask_image


    @classmethod
    def _slic(cls, image, segment_size):
        compactness = 0.01  # make superpixels highly deformable
        max_iter = 10
        sigma = 2.0

        num_segments = (image.shape[0] * image.shape[1]) / (segment_size ** 2)

        label_image = skimage.segmentation.slic(
            image,
            n_segments=num_segments,
            compactness=compactness,
            max_iter=max_iter,
            sigma=sigma,
            enforce_connectivity=True,
            min_size_factor=0.5,
            slic_zero=True
        )
        return label_image


    class _PersistentCounter(object):
        def __init__(self):
            self.value = 0

        def __call__(self):
            ret = self.value
            self.value += 1
            return ret


    @classmethod
    def _uint64ToRGB(cls, val):
        return numpy.dstack((
            numpy.bitwise_and(numpy.uint64(val), numpy.uint64(0xff)
            ).astype(numpy.uint8),
            numpy.right_shift(
                numpy.bitwise_and(numpy.uint64(val), numpy.uint64(0xff00)),
                numpy.uint64(8)
            ).astype(numpy.uint8),
            numpy.right_shift(
                numpy.bitwise_and(numpy.uint64(val), numpy.uint64(0xff0000)),
                numpy.uint64(16)
            ).astype(numpy.uint8)
        ))


    @classmethod
    def superpixels(cls, image, coords):
        mask_image = ScikitSegmentationHelper._contourToMask(image, coords)

        # TODO: remove
        mask_image = ScikitSegmentationHelper._binaryOpening(
            mask_image, element_shape='circle', element_radius=5)

        inside_image = image.copy()
        inside_image[numpy.logical_not(mask_image)] = 0
        inside_superpixel_labels = cls._slic(inside_image, segment_size=20)

        outside_image = image.copy()
        outside_image[mask_image] = 0
        outside_superpixel_labels = cls._slic(outside_image, segment_size=60)

        # https://stackoverflow.com/questions/16210738/implementation-of-numpy-in1d-for-2d-arrays
        inside_superpixel_mask = numpy.in1d(
            inside_superpixel_labels.flat,
            numpy.unique(inside_superpixel_labels[mask_image])
        ).reshape(inside_superpixel_labels.shape)

        combined_superpixel_labels = outside_superpixel_labels.copy()
        combined_superpixel_labels[inside_superpixel_mask] = \
            inside_superpixel_labels[inside_superpixel_mask] + \
            outside_superpixel_labels.max() + 10000

        label_values = collections.defaultdict(cls._PersistentCounter())
        for value in numpy.nditer(combined_superpixel_labels, op_flags=['readwrite']):
            value[...] = label_values[value.item()]

        combined_superpixels = cls._uint64ToRGB(combined_superpixel_labels)
        return combined_superpixels