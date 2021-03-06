import yaml
from models.murel.networks.MurelNet import MurelNet
from models.baseline.networks.AttentionNet import AttentionNet
from models.baseline.networks.FRCNNConcat import FRCNNConcat
from models.baseline.networks.ResnetConcat import ResnetConcat


class ModelFactory:
    def create_model(self, model_name, config, word_vocabulary):
        if model_name == 'murel':
            return MurelNet(config, word_vocabulary)
        elif model_name == 'attention':
            return AttentionNet(config, word_vocabulary)
        elif model_name == 'frcnn_concat':
            return FRCNNConcat(config, word_vocabulary)
        elif model_name == 'resnet_concat':
            return ResnetConcat(config, word_vocabulary)
        elif model_name == 'graph_conv':
            return MurelNet(config, word_vocabulary)
        else:
            raise ValueError()


    def create_config(self, model_name):
        ROOT_DIR = '/auto/homes/bat34/VQA_PartII/models/{}'
        if model_name == 'murel':
            with open(ROOT_DIR.format('murel/configs/murel.yaml')) as f:
                config = yaml.load(f)
            return config
        elif model_name == 'attention':
            with open(ROOT_DIR.format('baseline/configs/attention_baseline.yaml')) as f:
                config = yaml.load(f)
            return config
        elif model_name == 'frcnn_concat':
            with open(ROOT_DIR.format('baseline/configs/agg_baseline.yaml')) as f:
                config = yaml.load(f)
            return config
        elif model_name == 'resnet_concat':
            with open(ROOT_DIR.format('baseline/configs/resnet_concat.yaml')) as f:
                config = yaml.load(f)
            return config
        elif model_name == 'graph_conv':
            with open(ROOT_DIR.format('murel/configs/graph_conv.yaml')) as f:
                config = yaml.load(f)
            return config
        else:
            raise ValueError('Unrecognised model name. Please choose one of murel, attention, frcnn_concat, or resnet_concat')


