import sys
import os
import os.path as osp
import argparse
import numpy as np
import cv2
import torch

sys.path.insert(0, osp.join('..', 'main'))
sys.path.insert(0, osp.join('..', 'data'))
sys.path.insert(0, osp.join('..', 'common'))
from config import cfg
from model import Model

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu', type=int, default='0')
    parser.add_argument('--test_epoch', type=str, dest='test_epoch')
    args = parser.parse_args()

    assert args.test_epoch, 'Test epoch is required.'
    return args

def main():
    args = parse_args()
    test_folder = './test_folder'
    model_path = './snapshot_%d.pth.tar' % int(args.test_epoch)
    model=Model(resnet_version=50,mano_neurons=[512, 512, 512, 512],mano_use_pca=False,cascaded_num=3)
    ckpt=torch.load("{}".format(model_path), map_location=device)
    model.load_state_dict({k.split('.',1)[1]:v for k,v in ckpt['network'].items()})
    model.to(device)
    model.eval()
    print('load success')
    INPUT_SIZE=256
    right_face=model.mesh_reg.mano_layer['r'].faces
    left_face=model.mesh_reg.mano_layer['l'].faces
    for img_name in os.listdir(test_folder):
        img=cv2.imread(os.path.join(test_folder,img_name), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if img is None:continue
        ratio=INPUT_SIZE/max(*img.shape[:2])
        M=np.array([[ratio,0,0],[0,ratio,0]],dtype=np.float32)
        img=cv2.warpAffine(img,M,(INPUT_SIZE,INPUT_SIZE),flags=cv2.INTER_LINEAR,borderValue=[0,0,0])
        img=img[:,:,::-1].astype(np.float32)/255
        input_tensor=torch.tensor(img.copy().transpose(2,0,1),device=device,dtype=torch.float32).unsqueeze(0)
        out = model({'img':input_tensor}, None, None, 'test')
        #outputting the mano shape and pose parameters
        pose = out['pose']
        shape = out['shape']

        first9pose = pose[0][0][0 : 9] #the first 9 parameters in the pose dict entry
        first10shape = shape[0][0][0: 10] #the first 10 parameters in the shape dict entry

        joint_coord_out = out['joints3d']
        trans = out['trans']
        verts3d = out['verts3d']
        right_mano_para={
            'joints3d':joint_coord_out[:,:21,:]-joint_coord_out[:,4,None,:],
            'verts3d':verts3d[:,:verts3d.shape[1]//2,:]-joint_coord_out[:,4,None,:],
        }
        left_mano_para = {
            'joints3d':joint_coord_out[:,21:,:]-joint_coord_out[:,4+21,None,:],
            'verts3d':verts3d[:,verts3d.shape[1]//2:,:]-joint_coord_out[:,4+21,None,:],
        }

        predict_right_length=(right_mano_para['joints3d'][:,4]-right_mano_para['joints3d'][:,0]).norm(dim=1)
        predict_left_length=(left_mano_para['joints3d'][:,4]-left_mano_para['joints3d'][:,0]).norm(dim=1)
        predict_right_verts=right_mano_para['verts3d']/predict_right_length[:,None,None]
        predict_left_verts=left_mano_para['verts3d']/predict_left_length[:,None,None]
        predict_left_verts_trans=(predict_left_verts+trans[:,1:].view(-1,1,3))*torch.exp(trans[:,0,None,None])
        output_file_name=img_name.split('.')[0]
        
        with open(os.path.join(test_folder, output_file_name+'_entire_pose_array.txt'), 'w') as file_object:
            file_object.write("All poses: " + ', '.join(map(str, pose.tolist())) + "\n")
            
        with open(os.path.join(test_folder, output_file_name+'_entire_shape_array.txt'), 'w') as file_object:
            file_object.write("All shapes: " + ', '.join(map(str, shape.tolist())) + "\n")

        #outputs some of the data in the needed format
        #these likely aren't the correct parameters to output, need to find which ones are
        with open(os.path.join(test_folder, output_file_name+'_formatter_shape_and_pose.txt'), 'w') as file_object:
            file_object.write("All poses: " + ', '.join(map(str, first9pose.tolist())) + "\n")
            file_object.write("All betas: " + ', '.join(map(str, first10shape.tolist())) + "\n")
       

if __name__=='__main__':
    with torch.no_grad():
        main()

