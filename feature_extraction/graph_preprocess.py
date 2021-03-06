from models.murel.networks.GraphConstructor import GraphConstructor
import argparse
import progressbar
import os
import torch
from torch_geometric.data import Data
import subprocess


def main():
    if args.graph_type == 'knn':
        constructor = GraphConstructor.getKNNConstructor(k=args.no_neighbours, force_undirected=True)
    feat_dir = '/auto/homes/bat34/2018-04-27_bottom-up-attention_fixed_36'
    graph_files_dir = '/local/scratch/bat34/graphs/preprocessed_graphs_knn_neighbours_{}'.format(args.no_neighbours)
    if not os.path.exists(graph_files_dir):
        subprocess.run(['mkdir', '-p', graph_files_dir])

    images_list = os.listdir(feat_dir)
    for i in progressbar.progressbar(range(len(images_list))):
        name = images_list[i]
        feat_path = os.path.join(feat_dir, name)
        dict_feats = torch.load(feat_path)
        data = Data(pos=dict_feats['norm_rois'])
        data = constructor(data)
        torch.save(data, os.path.join(graph_files_dir, name))
    print('Finished processing %s graphs' % args.graph_type)


parser = argparse.ArgumentParser()
parser.add_argument('-g', '--graph_type', action='store', dest='graph_type')
parser.add_argument('-k', '--no-neighbours', type=int)
args = parser.parse_args()

if __name__ == '__main__':
    main()
