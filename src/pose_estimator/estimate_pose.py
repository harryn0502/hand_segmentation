import sys
import os
import os.path as osp
import argparse
import numpy as np
import cv2
import torch

curr_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(curr_dir, 'main'))
sys.path.insert(0, os.path.join(curr_dir, 'data'))
sys.path.insert(0, os.path.join(curr_dir, 'common'))

from config import cfg
from model import Model

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

def estimate_pose(input_folder, output_folder, model_path):
    model = Model(
        resnet_version=50,
        mano_neurons=[512, 512, 512, 512],
        mano_use_pca=False,
        cascaded_num=3,
    )
    ckpt = torch.load("{}".format(model_path), map_location=device)
    model.load_state_dict({k.split(".", 1)[1]: v for k, v in ckpt["network"].items()})
    model.to(device)
    model.eval()
    print("load success")
    INPUT_SIZE = 256
    right_face = model.mesh_reg.mano_layer["r"].faces
    left_face = model.mesh_reg.mano_layer["l"].faces
    for img_name in os.listdir(input_folder):
        img = cv2.imread(
            os.path.join(input_folder, img_name),
            cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION,
        )
        if img is None:
            continue
        ratio = INPUT_SIZE / max(*img.shape[:2])
        M = np.array([[ratio, 0, 0], [0, ratio, 0]], dtype=np.float32)
        img = cv2.warpAffine(
            img,
            M,
            (INPUT_SIZE, INPUT_SIZE),
            flags=cv2.INTER_LINEAR,
            borderValue=[0, 0, 0],
        )
        img = img[:, :, ::-1].astype(np.float32) / 255
        input_tensor = torch.tensor(
            img.copy().transpose(2, 0, 1), device=device, dtype=torch.float32
        ).unsqueeze(0)
        out = model({"img": input_tensor}, None, None, "test")

        # outputting the mano shape and pose parameters
        joint_coord_out = out["joints3d"]
        trans = out["trans"]
        verts3d = out["verts3d"]
        right_mano_para = {
            "joints3d": joint_coord_out[:, :21, :] - joint_coord_out[:, 4, None, :],
            "verts3d": verts3d[:, : verts3d.shape[1] // 2, :]
            - joint_coord_out[:, 4, None, :],
        }
        left_mano_para = {
            "joints3d": joint_coord_out[:, 21:, :]
            - joint_coord_out[:, 4 + 21, None, :],
            "verts3d": verts3d[:, verts3d.shape[1] // 2 :, :]
            - joint_coord_out[:, 4 + 21, None, :],
        }

        ljoints = joint_coord_out[0][0:21]
        rjoints = joint_coord_out[0][22:42]

        predict_right_length = (
            right_mano_para["joints3d"][:, 4] - right_mano_para["joints3d"][:, 0]
        ).norm(dim=1)
        predict_left_length = (
            left_mano_para["joints3d"][:, 4] - left_mano_para["joints3d"][:, 0]
        ).norm(dim=1)
        predict_right_verts = (
            right_mano_para["verts3d"] / predict_right_length[:, None, None]
        )
        predict_left_verts = (
            left_mano_para["verts3d"] / predict_left_length[:, None, None]
        )
        predict_left_verts_trans = (
            predict_left_verts + trans[:, 1:].view(-1, 1, 3)
        ) * torch.exp(trans[:, 0, None, None])
        output_file_name = img_name.split(".")[0]

        with open(
            os.path.join(output_folder, output_file_name + "_right_joints3D.txt"), "w"
        ) as file_object:
            file_object.write(
                "Joints3D Right: " + ", ".join(map(str, rjoints.tolist())) + "\n"
            )

        with open(
            os.path.join(output_folder, output_file_name + "_left_joints3D.txt"), "w"
        ) as file_object:
            file_object.write(
                "Joints3D left: " + ", ".join(map(str, ljoints.tolist())) + "\n"
            )


if __name__ == "__main__":
    with torch.no_grad():
        input_folder = "input"
        output_folder = "output"
        epochs = 99
        model_path = "model/snapshot_%d.pth.tar" % int(epochs)
        estimate_pose(input_folder, output_folder, model_path)