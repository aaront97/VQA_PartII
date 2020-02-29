import torch
import random
import torch.nn as nn
from torch.utils.data import DataLoader
import os
import yaml
from dataset.MurelNetDataset import MurelNetDataset
from murel.models.MurelNet import MurelNet
from tensorboardX import SummaryWriter
import tqdm
import subprocess
from schedulers.schedulers import LR_List_Scheduler
from loss_functions.loss_functions import soft_cross_entropy
from evaluation.eval_vqa import VQA_Evaluator
import json
import numpy as np


def create_summary_writer(model, loader, logdir):
    batch = next(iter(loader))
    writer = SummaryWriter(logdir=logdir)
    try:
        writer.add_graph(model, batch)
    except Exception as e:
        print("Writer can't save model at {}".format(logdir))
        print(e)
    return writer


def get_model_directory(config, chosen_keys):
    res = config['name']
    for key in chosen_keys:
        res += "_{}_{}".format(key, config[key])
    return res


def val_evaluate(model, epoch, val_loader, writer, evaluator, aid_to_ans, RESULTS_FILE_PATH):
    model.eval()
    print('Running model on validation dataset..')
    with torch.no_grad():
        results = []
        for data in tqdm.tqdm(val_loader):
            item = {
                    'question_ids': data['question_ids'].cuda(),
                    'object_features_list': data['object_features_list'].cuda(),
                    'bounding_boxes': data['bounding_boxes'].cuda(),
                    'answer_id': torch.squeeze(data['answer_id']).cuda(),
                    'question_lengths': data['question_lengths'].cuda(),
            }
            inputs = item
            qids = data['question_unique_id']
            outputs = model(inputs)
            values, ans_indices = torch.max(outputs, dim=1)
            ans_indices = list(ans_indices)
            ans_indices = [tsr.item() for tsr in ans_indices]
            for qid, ans_idx in zip(qids, ans_indices):
                results.append({
                    'question_id': int(qid),
                    'answer': aid_to_ans[ans_idx]
                })
    print('Finished evaluating the model on the val dataset.')
    print('Saving results to %s' % RESULTS_FILE_PATH)
    with open(RESULTS_FILE_PATH, 'w') as f:
        json.dump(results, f)
    print('Done saving to %s' % RESULTS_FILE_PATH)
    print('Calling VQA evaluation subroutine')
    # We let the evaluator do all the tensorboard logging.
    accuracy = evaluator.evaluate(RESULTS_FILE_PATH, epoch)
    print("Validation Results - Epoch: {}  Overall  accuracy: {:.2f}".format(epoch, accuracy))
    # writer.add_scalar("validation/overall_accuracy", accuracy, epoch)
    return accuracy


def train_evaluate(model, epoch, train_loader, writer, criterion):
    model.eval()
    correct = 0
    total = 0
    running_loss = 0.0
    count = 1
    evaluator_criterion = nn.NLLLoss(reduction='sum')
    with torch.no_grad():
        for data in tqdm.tqdm(train_loader):
            item = {
                    'question_ids': data['question_ids'].cuda(),
                    'object_features_list': data['object_features_list'].cuda(),
                    'bounding_boxes': data['bounding_boxes'].cuda(),
                    'answer_id': torch.squeeze(data['answer_id']).cuda(),
                    'question_lengths': data['question_lengths'].cuda()
            }
            inputs, labels = item, item['answer_id']
            outputs = model(inputs)
            _, predicted = torch.max(outputs, dim=1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()
            running_loss += evaluator_criterion(outputs, labels).item()
            count += 1
    avg_accuracy = correct / total
    avg_cross_entropy = running_loss / total
    print("Training Results - Epoch: {}  Avg accuracy: {:.2f} Avg loss: {:.2f}"
              .format(epoch, avg_accuracy, avg_cross_entropy))
    writer.add_scalar("training/avg_loss", avg_cross_entropy, epoch)
    writer.add_scalar("training/avg_accuracy", avg_accuracy, epoch)
    return avg_accuracy


def save_checkpoint(state, info):
    config = info['config']
    checkpoint_file_name = info['checkpoint_file_name']
    best_model_file_name = info['best_model_file_name']
    if info['isBest']:
        torch.save(state, best_model_file_name)
    if (state['epoch'] % config['checkpoint_every']) == 0:
        torch.save(state, checkpoint_file_name)


def load_checkpoint(file_name, model, optimizer):
    state = torch.load(file_name)
    model.load_state_dict(state['model'])
    optimizer.load_state_dict(state['optimizer'])
    return model, optimizer, state['epoch']

def get_max_accuracy(checkpoint_file_name, best_model_file_name):
    res = -1
    if os.path.exists(checkpoint_file_name):
        res = max(torch.load(checkpoint_file_name)['accuracy'], res)
    if os.path.exists(best_model_file_name):
        res = max(torch.load(best_model_file_name)['accuracy'], res)
    return res


def get_dirs(config, include_keys=[]):
    if not include_keys:
        raise ValueError(
                'Please include keys to include for' +
                'naming model and log directories')
    root_dir = config['ROOT_DIR']
    model_name = config['name']
    for key in include_keys:
        model_name += "_{}_{}".format(key, config[key])
    log_dir = os.path.join(root_dir, 'logs', model_name)
    checkpoint_dir = os.path.join(root_dir,
                                  'trained_models',
                                  'checkpoints',
                                  model_name)
    best_model_dir = os.path.join(root_dir,
                                  'trained_models',
                                  'best_models',
                                  model_name)
    checkpoint_file_name = os.path.join(checkpoint_dir, 'checkpoint.pth')
    best_model_file_name = os.path.join(best_model_dir, 'best_model.pth')
    dir_to_check = [log_dir, checkpoint_dir, best_model_dir]
    for directory in dir_to_check:
        if not os.path.exists(directory):
            subprocess.run(['mkdir', '-p', directory])
    res = {}
    res['log_dir'] = log_dir
    res['checkpoint_dir'] = checkpoint_dir
    res['best_model_dir'] = best_model_dir
    res['checkpoint_file_name'] = checkpoint_file_name
    res['best_model_file_name'] = best_model_file_name
    return res

def set_seed(seed):
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

# Fix dirs
def run():
    with open('murel.yaml') as f:
        config = yaml.load(f)
    set_seed(config['seed'])
    ROOT_DIR = config['ROOT_DIR']
    RESULTS_FILE_PATH = config['RESULTS_FILE_PATH']
    names = get_dirs(config, include_keys=['seed',
                                           'loss_function',
                                           'txt_enc',
                                           'pooling_agg',
                                           'pairwise_agg',
                                           'batch_size',
                                           'lr',
                                           'lr_decay_rate',
                                           'unroll_steps',
                                           'fusion_type'])

    writer = SummaryWriter(logdir=names['log_dir'])
    evaluator = VQA_Evaluator(summary_writer=writer)
    if torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print('CUDA AVAILABILITY: {}, Device used: {}'
          .format(torch.cuda.is_available(), device))
    
    train_dataset = MurelNetDataset(
            split="train",
            txt_enc=config['txt_enc'],
            bottom_up_features_dir=config['bottom_up_features_dir'],
            skipthoughts_dir=config['skipthoughts_dir'],
            processed_dir=config['processed_dir'],
            ROOT_DIR=ROOT_DIR,
            vqa_dir=config['vqa_dir'])
    val_dataset = MurelNetDataset(
            split="val",
            txt_enc=config['txt_enc'],
            bottom_up_features_dir=config['bottom_up_features_dir'],
            skipthoughts_dir=config['skipthoughts_dir'],
            processed_dir=config['processed_dir'],
            ROOT_DIR=ROOT_DIR,
            vqa_dir=config['vqa_dir'])

    # https://gist.github.com/thomwolf/ac7a7da6b1888c2eeac8ac8b9b05d3d3
    reduction_factor = config['reduction_factor']
    batch_size = config['batch_size'] // reduction_factor

    train_loader = DataLoader(
            train_dataset,
            shuffle=True,
            batch_size=batch_size,
            num_workers=config['num_workers'],
            collate_fn=train_dataset.collate_fn)
    val_loader = DataLoader(
            val_dataset,
            shuffle=True,
            batch_size=batch_size,
            num_workers=config['num_workers'],
            collate_fn=val_dataset.collate_fn)

    # Construct word vocabulary
    word_vocabulary = [word for _, word in train_dataset.word_to_wid.items()]

    # Build model
    model = MurelNet(config, word_vocabulary)

    # Transfer model to GPU
    model = model.cuda()
    optimizer = torch.optim.Adam(model.parameters(), lr=config['lr'])

    checkpoint_dir = names['checkpoint_dir']
    best_model_dir = names['best_model_dir']
    checkpoint_file_name = names['checkpoint_file_name']
    best_model_file_name = names['best_model_file_name']

    if config['checkpoint_option'] == 'resume_last':
        model, optimizer, start_epoch = load_checkpoint(
                checkpoint_file_name, model, optimizer)
    elif config['checkpoint_option'] == 'best':
        model, optimizer, start_epoch = load_checkpoint(
                best_model_file_name, model, optimizer)
    else:
        start_epoch = 0

    max_accuracy = -1
    if config['checkpoint_option'] == 'resume_last' and (os.path.exists(best_model_file_name) or os.path.exists(checkpoint_file_name)):
        max_accuracy = get_max_accuracy(
                checkpoint_file_name, best_model_file_name)

    # model, optimizer, start_epoch, max_accuracy =
    # load_checkpoint(config, model, optimizer)
    print('Model loaded, all keys matched successfully')

    print('Starting training from EPOCH {}'.format(start_epoch))
    lr_scheduler = LR_List_Scheduler(config)
    if config['loss_function'] == 'NLLLoss':
        criterion = nn.NLLLoss()
    elif config['loss_function'] == 'soft_cross_entropy':
        criterion = soft_cross_entropy
    else:
        raise ValueError('Invalid loss function entered!')

    global_iteration = 0
    for epoch in tqdm.tqdm(range(start_epoch, config['epochs'])):
        model.train()
        running_loss = 0.0
        pbar = tqdm.tqdm(train_loader)
        local_iteration = 0
        lr_scheduler.update_lr(optimizer, epoch)
        print('Current learning rate {}'.format(optimizer.param_groups[0]['lr']))
        optimizer.zero_grad()
        batch_counter = 0
        total_batch_loss = 0
        for data in pbar:
            global_iteration += 1
            local_iteration += 1
            batch_counter += 1
            pbar.set_description("Epoch[{}] Iteration[{}/{}]".format(epoch,
                                 local_iteration, len(train_loader)))
            item = {
                    'question_ids': data['question_ids'].cuda(),
                    'object_features_list': data['object_features_list'].cuda(),
                    'bounding_boxes': data['bounding_boxes'].cuda(),
                    'answer_id': torch.squeeze(data['answer_id']).cuda(),
                    'question_lengths': data['question_lengths'].cuda(),
                    'id_unique': data['id_unique'].cuda(),
                    'id_weights': data['id_weights'].cuda()
            }
            
            if config['include_graph_module']:
                item['graph_batch'] = data['graph'].cuda()


            inputs, labels = item, item['answer_id']
            outputs = model(inputs)
            if config['loss_function'] == 'NLLLoss':
                loss = criterion(outputs, labels)
            else:
                loss = criterion(outputs, item['id_unique'], item['id_weights'])
            total_batch_loss += loss.item()
            loss = loss / reduction_factor
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),
                                           config['grad_clip'])
            if local_iteration % reduction_factor == 0:
                optimizer.step()
                optimizer.zero_grad()
            running_loss += loss.item() * reduction_factor

            if local_iteration % (config['log_every'] * reduction_factor) == 0:
                running_loss = running_loss / (config['log_every'] * reduction_factor)
                print("Epoch[{}] Iteration[{}/{}] Loss: {:.2f}".format(epoch,
                      local_iteration, len(train_loader), running_loss))
                writer.add_scalar("training/loss",
                                  running_loss, global_iteration)
                running_loss = 0.0

        # At the end of every epoch, 
        # run it on the validation and training dataset
        # train_evaluate(model, epoch, train_loader, writer, criterion)
        average_batch_loss = total_batch_loss / batch_counter
        print('Training Results: Epoch {} Average Epoch Loss: {:.2f}'.format(epoch, average_batch_loss))
        writer.add_scalar("training/average_epoch_loss", average_batch_loss, epoch)
        accuracy = val_evaluate(model, epoch, val_loader, writer, evaluator, train_dataset.aid_to_ans, RESULTS_FILE_PATH)

        isBest = False
        if accuracy > max_accuracy:
            print('Validation accuracy at epoch {} is higher than the max validation accuracy!'.format(epoch))
            print('')
            print('Updating max_accuracy...')
            max_accuracy = accuracy
            isBest = True
        else:
            print('Validation accuracy in epoch {} is lower than the max validation accuracy'.format(epoch))

        state = {
            'model': model.state_dict(),
            'optimizer': optimizer.state_dict(),
            'epoch': epoch + 1,
            'accuracy': accuracy,
        }

        info = {
            'isBest': isBest,
            'checkpoint_file_name': checkpoint_file_name,
            'best_model_file_name': best_model_file_name,
            'epoch': epoch + 1,
            'accuracy': accuracy,
            'config': config,
        }
        print('')
        print('Checkpointing model..')
        if ((epoch + 1) % config['checkpoint_every']) == 0 or isBest:
            save_checkpoint(state, info)


if __name__ == '__main__':
    run()
