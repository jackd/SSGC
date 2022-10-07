import time
import argparse
import numpy as np
import torch
import torch.nn.functional as F
import torch.optim as optim
from utils import load_citation, sgc_precompute, set_seed
from models import get_model
from metrics import accuracy
import pickle as pkl
from args_cora import get_citation_args
from time import perf_counter

# Arguments
args = get_citation_args()

if args.tuned:
    if args.model == "SGC":
        with open("{}-tuning/{}.txt".format(args.model, args.dataset), 'rb') as f:
            args.weight_decay = pkl.load(f)['weight_decay']
            print("using tuned weight decay: {}".format(args.weight_decay))
    else:
        raise NotImplemented

# setting random seeds
set_seed(args.seed, args.cuda)

adj, features, labels, idx_train, idx_val, idx_test = load_citation(args.dataset, args.normalization, args.cuda)

model = get_model(args.model, features.size(1), labels.max().item()+1, args.hidden, args.dropout, args.cuda)

if args.model == "SGC": features, precompute_time = sgc_precompute(features, adj, args.degree, args.alpha)
print("{:.4f}s".format(precompute_time))

def train_regression(model,
                     train_features, train_labels,
                     val_features, val_labels,
                     epochs=args.epochs, weight_decay=args.weight_decay,
                     lr=args.lr, dropout=args.dropout):

    optimizer = optim.Adam(model.parameters(), lr=lr,
                           weight_decay=weight_decay)
    t = perf_counter()
    best_acc_val = torch.zeros((1))
    best_loss_val = 100.
    best_model = None
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        output = model(train_features)
        loss_train = F.cross_entropy(output, train_labels)
        loss_train.backward()
        optimizer.step()
        with torch.no_grad():
            model.eval()
            output = model(val_features)
            acc_val = accuracy(output, val_labels).item()
            loss_val = F.cross_entropy(output, val_labels).item()
            if best_acc_val < acc_val:
                 best_acc_val = acc_val
            #     best_model = model
            if best_loss_val > loss_val:
                best_loss_val = loss_val
                best_model = model

    train_time = perf_counter()-t

    # with torch.no_grad():
    #     model.eval()
    #     output = model(val_features)
    #     acc_val = accuracy(output, val_labels)

    return best_model, best_acc_val, train_time

def test_regression(model, test_features, test_labels):
    model.eval()
    return accuracy(model(test_features), test_labels)

acc_tests = []
acc_vals = []
for _ in range(args.repeats):
    model.reset_parameters()
    if args.model == "SGC":
        model, acc_val, train_time = train_regression(model, features[idx_train], labels[idx_train], features[idx_val], labels[idx_val],
                        args.epochs, args.weight_decay, args.lr, args.dropout)
        acc_test = test_regression(model, features[idx_test], labels[idx_test]).item()
        acc_tests.append(acc_test)
        acc_vals.append(acc_val)
    print("Validation Accuracy: {:.4f} Test Accuracy: {:.4f}".format(acc_val, acc_test))
    print("Pre-compute time: {:.4f}s, train time: {:.4f}s, total: {:.4f}s".format(precompute_time, train_time, precompute_time+train_time))

print("Overall")
print(f"test_acc = {np.mean(acc_tests):.4f} +- {np.std(acc_tests):.4f}")
print(f"val_acc  = {np.mean(acc_vals):.4f} +- {np.std(acc_vals):.4f}")
