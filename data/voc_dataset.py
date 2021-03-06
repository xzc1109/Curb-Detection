import os
import xml.etree.ElementTree as ET

import numpy as np

from .util import read_image


class CurbROIDataset:
    """Bounding box dataset for Curb ROI
    The index corresponds to each image.

    When queried by an index, if :return_difficult == False,
    this dataset returns a corresponding
    obj:img, bbox, label, a tuple of an image, bounding boxes and labels.
    This is the default behaviour.
    If :obj:return_difficult == True, this dataset returns corresponding
    :obj:img, bbox, label, difficult. :obj:difficult is a boolean array
    that indicates whether bounding boxes are labeled as difficult or not.

    The bounding boxes are packed into a two dimensional tensor of shape
    :math:(R, 4), where :math:R is the number of bounding boxes in
    the image. The second axis represents attributes of the bounding box.
    They are :math:(y_{min}, x_{min}, y_{max}, x_{max}), where the
    four attributes are coordinates of the top left and the bottom right
    vertices.

    The labels are packed into a one dimensional tensor of shape :math:(R,).
    :math:R is the number of bounding boxes in the image.
    The class name of the label :math:`l` is :math:`l` th element of
    :obj:`VOC_BBOX_LABEL_NAMES`.

    The array :obj:`difficult` is a one dimensional boolean array of shape
    :math:`(R,)`. :math:`R` is the number of bounding boxes in the image.
    If :obj:`use_difficult` is :obj:`False`, this array is
    a boolean array with all :obj:`False`.

    The type of the image, the bounding boxes and the labels are as follows.

    * :obj:`img.dtype == numpy.float32`
    * :obj:`bbox.dtype == numpy.float32`
    * :obj:`label.dtype == numpy.int32`
    * :obj:`difficult.dtype == numpy.bool`

    Args:
        data_dir (string): Path to the root of the training data. 
            i.e. "/data/image/voc/VOCdevkit/VOC2007/"
            i.e. "/data/image/Day/CURB2019"
        split ({'train', 'val', 'trainval', 'test','predict'}): Select a split of the
            dataset. :obj:`test` split is only available for
            2007 dataset.
            obj:`predict` split is only available for
            CURB2019.
        year ({'2007', '2012'}): Use a dataset prepared for a challenge
            held in :obj:`year`.
        use_difficult (bool): If :obj:`True`, use images that are labeled as
            difficult in the original annotation.
        return_difficult (bool): If :obj:`True`, this dataset returns
            a boolean array
            that indicates whether bounding boxes are labeled as difficult
            or not. The default value is :obj:`False`.

    """

    def __init__(self, data_dir,split = 'train'
                 ,use_difficult=False, return_difficult=False,
                 ):

        id_list_file = os.path.join(
            data_dir, 'ImageSets/Main/{0}.txt'.format(split))

        self.ids = [id_.strip() for id_ in open(id_list_file)]
        self.data_dir = data_dir
        self.use_difficult = use_difficult
        self.return_difficult = return_difficult
        self.label_names = CURB_BBOX_LABEL_NAMES
        self.split = split
    def __len__(self):
        return len(self.ids)

    def get_example(self, i):
        """Returns the i-th example.

        Returns a color image and bounding boxes. The image is in CHW format.
        The returned image is RGB.

        Args:
            i (int): The index of the example.

        Returns:
            tuple of an image and bounding boxes

        """
        if self.split != 'predict':
            id_ = self.ids[i]
            anno = ET.parse(
                os.path.join(self.data_dir, 'Annotations', id_ + '.xml'))
            bbox = list()
            label = list()
            difficult = list()
            scene = list()
            for obj in anno.findall('object'):
                # when in not using difficult split, and the object is
                # difficult, skipt it.
                if not self.use_difficult and int(obj.find('difficult').text) == 1:
                    continue

                difficult.append(int(obj.find('difficult').text))
                bndbox_anno = obj.find('bndbox')
                # subtract 1 to make pixel indexes 0-based
                bbox.append([
                    int(bndbox_anno.find(tag).text) - 1
                    for tag in ('ymin', 'xmin', 'ymax', 'xmax')])
                name = obj.find('name').text.lower().strip()
                label.append(CURB_BBOX_LABEL_NAMES.index(name))
                #_type = obj.find('type')
                #if _type is None:print(id_,'  ',_type,'\n')
                scene_type = obj.find('type').text.lower().strip()
                scene.append(SCENE_NAMES.index(scene_type))
            bbox = np.stack(bbox).astype(np.float32)
            label = np.stack(label).astype(np.int32)
            scene = np.stack(scene).astype(np.int32)
            # When `use_difficult==False`, all elements in `difficult` are False.
            difficult = np.array(difficult, dtype=np.bool).astype(np.uint8)  # PyTorch don't support np.bool

            # Load a image
            img_file = os.path.join(self.data_dir, 'JPEGImages', id_ + '.jpg')
            img = read_image(img_file, color=True)

            # if self.return_difficult:
            #     return img, bbox, label, difficult
            return img, bbox, label, difficult, scene, id_
        else:
            id_ = self.ids[i]
            img_file = os.path.join(self.data_dir, 'JPEGImages', id_ + '.jpg')
            img = read_image(img_file, color=True)
            return img, id_
            
    __getitem__ = get_example


CURB_BBOX_LABEL_NAMES = (
    'curb')

SCENE_NAMES = (
    'continuously_visible',
    'intersection',
    'obstacle')
