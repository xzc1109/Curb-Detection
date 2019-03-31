from __future__ import  absolute_import
from __future__ import  division
import torch as t
from data.voc_dataset import CurbROIDataset
from skimage import transform as sktsf
from torchvision import transforms as tvtsf
from data import util
import numpy as np
from utils.config import opt


def inverse_normalize(img):
    if opt.caffe_pretrain:
        img = img + (np.array([122.7717, 115.9465, 102.9801]).reshape(3, 1, 1))
        return img[::-1, :, :]
    # approximate un-normalize for visualize
    return (img * 0.225 + 0.45).clip(min=0, max=1) * 255


def pytorch_normalze(img):
    """
    https://github.com/pytorch/vision/issues/223
    return appr -1~1 RGB
    """
    normalize = tvtsf.Normalize(mean=[0.485, 0.456, 0.406],
                                std=[0.229, 0.224, 0.225])
    img = normalize(t.from_numpy(img))
    return img.numpy()


def caffe_normalize(img):
    """
    return appr -125-125 BGR
    """
    img = img[[2, 1, 0], :, :]  # RGB-BGR
    img = img * 255
    mean = np.array([122.7717, 115.9465, 102.9801]).reshape(3, 1, 1)
    img = (img - mean).astype(np.float32, copy=True)
    return img


def preprocess(img, min_size=224, max_size=224):
    """Preprocess an image for feature extraction.

    The length of the shorter edge is scaled to :obj:`self.min_size`.
    After the scaling, if the length of the longer edge is longer than
    :param min_size:
    :obj:`self.max_size`, the image is scaled to fit the longer edge
    to :obj:`self.max_size`.

    After resizing the image, the image is subtracted by a mean image value
    :obj:`self.mean`.

    Args:
        img (~numpy.ndarray): An image. This is in CHW and RGB format.
            The range of its value is :math:`[0, 255]`.

    Returns:
        ~numpy.ndarray: A preprocessed image.

    """
    C, H, W = img.shape
    scale1 = min_size / H
    scale2 = max_size / W
    #scale = min(scale1, scale2)
    img = img / 255.
    img = sktsf.resize(img, (C, H * scale1, W * scale2), mode='reflect',anti_aliasing=False)
    # both the longer and shorter should be less than
    # max_size and min_size
    if opt.caffe_pretrain:
        normalize = caffe_normalize
    else:
        normalize = pytorch_normalze
    return normalize(img)

def holdout(dataset_dir,ratio=0.3):
    test_percent = ratio
    xmlfilepath = os.path.join(dataset_dir,'Annotations')
    testpath = os.path.join(xmlfilepath,'test.txt')
    trainpath = os.path.join(xmlfilepath,'train.txt')
    total_xml = os.listdir(xmlfilepath)
    num = len(total_xml)
    list = range(num)
    num_test = int(num * test_percent)
    test = random.sample(list, num_test)
    ftest = open(testpath, 'w')
    ftrain = open(trainpath, 'w')

    for i in list:
        if total_xml[i].endswith('xml'):
            name = total_xml[i][:-4] + '\n'
            if i in test:
                ftest.write(name)
            else:
                ftrain.write(name)

    ftrain.close()
    ftest.close()

class Transform(object):

    def __init__(self, min_size=224, max_size=224):
        self.min_size = min_size
        self.max_size = max_size

    def __call__(self, in_data):
        img, bbox, label = in_data
        _, H, W = img.shape
        img = preprocess(img, self.min_size, self.max_size)
        _, o_H, o_W = img.shape
        scale = o_H / H
        bbox = util.resize_bbox(bbox, (H, W), (o_H, o_W))

        # horizontally flip
        img, params = util.random_flip(
            img, x_random=True, return_param=True)
        bbox = util.flip_bbox(
            bbox, (o_H, o_W), x_flip=params['x_flip'])

        return img, bbox, label, scale


class Dataset:
    def __init__(self, opt):
        self.opt = opt
        self.db = CurbROIDataset(opt.voc_data_dir)
        self.tsf = Transform(opt.min_size, opt.max_size)

    def __getitem__(self, idx):
        ori_img, bbox, label, difficult, scene,__ = self.db.get_example(idx)

        img, bbox, label, scale = self.tsf((ori_img, bbox, label))
        # TODO: check whose stride is negative to fix this instead copy all
        # some of the strides of a given numpy array are negative.
        return img.copy(), bbox.copy(), label.copy(), scale, scene.copy()

    def __len__(self):
        return len(self.db)


class TestDataset:
    def __init__(self, opt, split='test', use_difficult=True):
        self.opt = opt
        self.db = CurbROIDataset(opt.voc_data_dir, split=split, use_difficult=use_difficult)

    def __getitem__(self, idx):
        ori_img, bbox, label, difficult, scene,__ = self.db.get_example(idx)
        img = preprocess(ori_img,opt.min_size, opt.max_size)
        return img, ori_img.shape[1:], bbox, label, difficult ,scene

    def __len__(self):
        return len(self.db)

class PredictDataset:
    def __init__(self, opt, split='predict', use_difficult=False):
        self.opt = opt
        self.db = CurbROIDataset(opt.predict_voc_data_dir, split=split, use_difficult=use_difficult)

    def __getitem__(self, idx):
        ori_img, img_id = self.db.get_example(idx)
        img = preprocess(ori_img,opt.min_size, opt.max_size)
        return img, ori_img.shape[1:],img_id

    def __len__(self):
        return len(self.db)
