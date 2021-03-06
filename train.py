from __future__ import  absolute_import
# though cupy is not used but without this line, it raise errors...
import cupy as cp
import os
import random
import json
import ipdb
import matplotlib
from tqdm import tqdm
from utils.config import opt
from data.dataset import Dataset, TestDataset, PredictDataset, inverse_normalize
from model import FasterRCNNVGG16
from torch.utils import data as data_
from trainer import FasterRCNNTrainer
from utils import array_tool as at
from utils.vis_tool import visdom_bbox
from utils.eval_tool import eval_detection_voc
from data.dataset import holdout
import resource

SCENE_NAMES = [
    'continuously_visible',
    'intersection',
    'obstacle']
rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (20480, rlimit[1]))

matplotlib.use('agg')
json_dir_path = opt.predict_voc_data_dir

def eval(dataloader, faster_rcnn, test_num=10000):
    count = 0
    acc = 0.0
    pred_bboxes, pred_labels, pred_scores, pred_scenes = list(), list(), list(), list()
    gt_bboxes, gt_labels, gt_difficults, gt_scenes = list(), list(), list() ,list()
    for ii, (imgs, sizes, gt_bboxes_, gt_labels_, gt_difficults_, gt_scenes_) in tqdm(enumerate(dataloader)):
        sizes = [sizes[0][0].item(), sizes[1][0].item()]
        pred_bboxes_, pred_labels_, pred_scores_, pred_scenes_ = faster_rcnn.predict(imgs, [sizes])
        #print(pred_bboxes_)
        gt_bboxes += list(gt_bboxes_.numpy())
        gt_labels += list(gt_labels_.numpy())
        gt_difficults += list(gt_difficults_.numpy())
        gt_scenes += list(gt_scenes_.numpy())
        pred_bboxes += pred_bboxes_
        pred_labels += pred_labels_
        pred_scores += pred_scores_
        pred_scenes += pred_scenes_
        gt_scenes_ = gt_scenes_.squeeze(0)
        gt_scenes_ = gt_scenes_.numpy()
        if pred_scenes_[0] == gt_scenes_[0]:
            count+=1
        if ii == test_num:
            break
    acc = count/test_num  
    result = eval_detection_voc(
        pred_bboxes, pred_labels, pred_scores,
        gt_bboxes, gt_labels, gt_difficults,
        use_07_metric=True)
    return result,acc

def predictor(dataloader, faster_rcnn, predict_num=10000):
    pred_bboxes, pred_labels, pred_scores, pred_scenes, img_ids = list(), list(), list(), list(), list()
    for ii, (imgs, sizes, img_id) in tqdm(enumerate(dataloader)):
        sizes = [sizes[0][0].item(), sizes[1][0].item()]
        img_ids.append(str(img_id))
        pred_bboxes_, pred_labels_, pred_scores_, pred_scenes_ = faster_rcnn.predict(imgs, [sizes])
        pred_bboxes += pred_bboxes_
        #print(pred_bboxes)
        pred_labels += pred_labels_
        pred_scores += pred_scores_
        pred_scenes.append(SCENE_NAMES[pred_scenes_[0]])
    jlist = list()
    json_path = os.path.join(json_dir_path,'predic_result.json')
    json_file = open(json_path,'w')
    for i in range(len(pred_bboxes)):
        maxindex = pred_scores[i].argmax()
        jlist.append({img_ids[i]:pred_bboxes[i][maxindex].tolist()})
        #jlist.append({img_ids[i]:pred_scenes[i]})
        #print(pred_scenes[i])
    json.dump(jlist,json_file,indent=1)
    json_file.close()
    print('predict %d images successfully, the result is saved in %s/%s.\n'%(predict_num,json_dir_path,json_file))

def predict(**kwargs):
    opt._parse(kwargs)
    os.environ["CUDA_VISIBLE_DEVICES"] = str(opt.cuda_device_id)
    print('load data')
    predictset = PredictDataset(opt)
    predict_dataloader = data_.DataLoader(predictset,
                                       batch_size=1,
                                       num_workers=opt.test_num_workers,
                                       shuffle=False, \
                                       pin_memory=True
                                       )
    faster_rcnn = FasterRCNNVGG16()
    trainer = FasterRCNNTrainer(faster_rcnn).cuda()
    if opt.load_path:
        trainer.load(opt.load_path)
        print('load best_model from %s complete'%opt.load_path)
    predictor(predict_dataloader, faster_rcnn, predict_num=opt.predict_num)

def train(**kwargs):
    opt._parse(kwargs)
    os.environ["CUDA_VISIBLE_DEVICES"] = str(opt.cuda_device_id)
    dataset = Dataset(opt)
    print('load data')
    dataloader = data_.DataLoader(dataset, \
                                  batch_size=1, \
                                  shuffle=True, \
                                  # pin_memory=True,
                                  num_workers=opt.num_workers)
    testset = TestDataset(opt)
    test_dataloader = data_.DataLoader(testset,
                                       batch_size=1,
                                       num_workers=opt.test_num_workers,
                                       shuffle=False, \
                                       pin_memory=True
                                       )
    faster_rcnn = FasterRCNNVGG16()
    print('model construct completed')
    trainer = FasterRCNNTrainer(faster_rcnn).cuda()
    if opt.load_path:
        trainer.load(opt.load_path)
        print('load pretrained model from %s' % opt.load_path)
    trainer.vis.text(dataset.db.label_names, win='labels')
    best_map = 0
    best_acc = 0
    accuracy = 0
    lr_ = opt.lr
    for epoch in range(opt.epoch):
        trainer.reset_meters()
        for ii, (img, bbox_, label_, scale, scene_) in tqdm(enumerate(dataloader)):
            scale = at.scalar(scale)
            img, bbox, label, scene = img.cuda().float(), bbox_.cuda(), label_.cuda(), scene_.cuda()
            trainer.train_step(img, bbox, label, scale, scene)

            if (ii + 1) % opt.plot_every == 0:
                if os.path.exists(opt.debug_file):
                    ipdb.set_trace()

                # plot loss
                trainer.vis.plot_many(trainer.get_meter_data())

                # plot groud truth bboxes
                ori_img_ = inverse_normalize(at.tonumpy(img[0]))
                gt_img = visdom_bbox(img=ori_img_,
                                     bbox=at.tonumpy(bbox_[0]),
                                     label=at.tonumpy(label_[0]),
                                     scene=at.tonumpy(scene_[0]))
                trainer.vis.img('gt_img', gt_img)

                # plot predicti bboxes
                _bboxes, _labels, _scores, _scenes = trainer.faster_rcnn.predict([ori_img_], visualize=True)
                pred_img = visdom_bbox(img=ori_img_,
                                       bbox=at.tonumpy(_bboxes[0]),
                                       label=at.tonumpy(_labels[0]).reshape(-1),
                                       score=at.tonumpy(_scores[0]),
                                       scene=_scenes)
                trainer.vis.img('pred_img', pred_img)

                # rpn confusion matrix(meter)
                trainer.vis.text(str(trainer.rpn_cm.value().tolist()), win='rpn_cm')
                # roi confusion matrix
                trainer.vis.img('roi_cm', at.totensor(trainer.roi_cm.conf, False).float())
        eval_result, accuracy = eval(test_dataloader, faster_rcnn, test_num=opt.test_num)
        trainer.vis.plot('test_map', eval_result['map'])
        trainer.vis.plot('accuracy', accuracy)
        lr_ = trainer.faster_rcnn.optimizer.param_groups[0]['lr']
        log_info = 'lr:{}, map:{},loss:{}'.format(str(lr_),
                                                  str(eval_result['map']),
                                                  str(trainer.get_meter_data()))
        trainer.vis.log(log_info)

        if (eval_result['map'] > best_map):
            best_map = eval_result['map']
            best_path = trainer.save(best_map=best_map, accuracy = accuracy)
        if (accuracy > best_acc):
            best_acc = accuracy
            best_path = trainer.save(best_map=best_map, accuracy = accuracy)
            #predictor(test_dataloader, faster_rcnn, test_num=opt.test_num)
        
       #holdout(opt.voc_data_dir,0.3)

        if epoch == 9:
            trainer.load(best_path)
            trainer.faster_rcnn.scale_lr(opt.lr_decay)
            lr_ = lr_ * opt.lr_decay

        if epoch == 13: 
            break


if __name__ == '__main__':
    import fire

    fire.Fire()
