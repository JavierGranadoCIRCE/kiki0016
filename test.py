import os
import random
# third-party library
import torch
import torch.nn as nn
import torch.utils.data as Data
import torchvision
import matplotlib.pyplot as plt
import scipy.io
from datetime import datetime
import math
from math import sqrt

import time
from sklearn import metrics
from sklearn.metrics import mean_absolute_error
from sklearn.metrics import mean_squared_error

 
import numpy as np
import pandas as pd
import torch.nn.functional as F
import pickle

from tqdm import tqdm
from tensorboardX import SummaryWriter

# pylint: disable=arguments-differ

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')



# convert str to datatime 
def convert_to_time(hmm):
    year, month, day, hour, minute, second = int(hmm[0]), int(hmm[1]), int(hmm[2]), int(hmm[3]), int(hmm[4]), int(hmm[5])
    return datetime(year=year, month=month, day=day, hour=hour, minute=minute, second=second)


# load data
batch1 = pickle.load(open(r'C:/Data/batch1.pkl', 'rb'))
#remove batteries that do not reach 80% capacity
del batch1['b1c8']
del batch1['b1c10']
del batch1['b1c12']
del batch1['b1c13']
del batch1['b1c22']

numBat1 = len(batch1.keys())

batch2 = pickle.load(open(r'C:/Data/batch2.pkl','rb'))

# There are four cells from batch1 that carried into batch2, we'll remove the data from batch2
# and put it with the correct cell from batch1
batch2_keys = ['b2c7', 'b2c8', 'b2c9', 'b2c15', 'b2c16']
batch1_keys = ['b1c0', 'b1c1', 'b1c2', 'b1c3', 'b1c4']
add_len = [662, 981, 1060, 208, 482];

for i, bk in enumerate(batch1_keys):
    batch1[bk]['cycle_life'] = batch1[bk]['cycle_life'] + add_len[i]
    for j in batch1[bk]['summary'].keys():
        if j == 'cycle':
            batch1[bk]['summary'][j] = np.hstack((batch1[bk]['summary'][j], batch2[batch2_keys[i]]['summary'][j] + len(batch1[bk]['summary'][j])))
        else:
            batch1[bk]['summary'][j] = np.hstack((batch1[bk]['summary'][j], batch2[batch2_keys[i]]['summary'][j]))
    last_cycle = len(batch1[bk]['cycles'].keys())
    for j, jk in enumerate(batch2[batch2_keys[i]]['cycles'].keys()):
        batch1[bk]['cycles'][str(last_cycle + j)] = batch2[batch2_keys[i]]['cycles'][jk]


del batch2['b2c7']
del batch2['b2c8']
del batch2['b2c9']
del batch2['b2c15']
del batch2['b2c16']    


batch3 = pickle.load(open(r'C:/Data/batch3.pkl','rb'))
# remove noisy channels from batch3
del batch3['b3c37']
del batch3['b3c2']
del batch3['b3c23']
del batch3['b3c32']
del batch3['b3c42']
del batch3['b3c43']

#bat_dict = {**batch1, **batch2, **batch3}
#bat_dict = {**batch1, **batch2}
bat_dict = {**batch3}
#print(bat_dict.keys())
#print(len(bat_dict))


# get capacity data
def getBatteryCapacity(bat_dict, name):
    cycle, capacity = [], []
    capacity = bat_dict[name]['summary']['QD']
    if len(capacity) < 400:
    # calculate the number of zeros to be filled
        padding_length = 400 - len(capacity)
    # create a list of 0's using [0] * padding_length
        padding = [0] * padding_length
    # joins the original list to the 0-filled list
        #capacity = np.r_[capacity, padding]
    #print(len(capacity))
    
    for i in range(len(capacity)):
        if name in bat_dict.keys():
            cycle.append(i)
    return [cycle, capacity]


Battery_list = ['b3c0', 'b3c1', 'b3c3', 'b3c4', 'b3c5', 'b3c6', 
                'b3c7', 'b3c8', 'b3c9', 'b3c10', 'b3c11', 'b3c12', 
                'b3c13', 'b3c14', 'b3c15', 'b3c16', 'b3c17', 'b3c18', 
                'b3c19', 'b3c20', 'b3c21', 'b3c22',  'b3c24', 'b3c25', 
                'b3c26', 'b3c27', 'b3c28', 'b3c29', 'b3c30', 'b3c31', 
                'b3c33', 'b3c34', 'b3c35', 'b3c36', 'b3c38', 'b3c39', 
                'b3c40', 'b3c41', 'b3c44', 'b3c45']
print(len(Battery_list))
Battery = {}
for name in Battery_list:
    Battery[name] = getBatteryCapacity(bat_dict, name)


def build_sequences(text, window_size):
    #text:list of capacity
    x, y = [],[]
    for i in range(len(text) - window_size):
        sequence = text[i:i+window_size]
        target = text[i+1:i+1+window_size]

        x.append(sequence)
        y.append(target)
        #arr_x, arr_y = np.array(x), np.array(y)
    #return arr_x.astype(np.float32), arr_y.astype(np.float32)
    return np.array(x), np.array(y)

def split_dataset(data_sequence, train_ratio=0.0, capacity_threshold=0.0):
    if capacity_threshold > 0:
        max_capacity = max(data_sequence)
        capacity = max_capacity * capacity_threshold
        point = [i for i in range(len(data_sequence)) if data_sequence[i] < capacity]
    else:
        point = int(train_ratio + 1)
        if 0 < train_ratio <= 1:
            point = int(len(data_sequence) * train_ratio)
    train_data, test_data = data_sequence[:point], data_sequence[point:]
    return train_data, test_data


# leave-one-out evaluation: one battery is sampled randomly; the remainder are used for training.
def get_train_test(data_dict, name, window_size=8):
    data_sequence=data_dict[name][1]
    #print(len(data_sequence))
    train_data, test_data = data_sequence[:5*window_size+1], data_sequence[5*window_size+1:]
    X_train, y_train = build_sequences(text=train_data, window_size=window_size)
    #print(X_train.dtype)
    for k, v in data_dict.items():
        if k != name:
            data_x, data_y = build_sequences(text=v[1], window_size=window_size)
            X_train, y_train = np.r_[X_train, data_x], np.r_[y_train, data_y]
    #print(X_train.dtype,y_train.dtype)
    print(len(test_data))
            
    return X_train, y_train, list(train_data), list(test_data)


def relative_positional_error(y_test, y_predict, threshold):
    true_rpe, pred_rpe = len(y_test), 0 #len(y_predict)
    for i in range(1,len(y_test)):
        if y_test[i-1] >= threshold and threshold >= y_test[i]:
            true_rpe = i 
            break
    for i in range(1,len(y_predict)):
        if y_predict[i-1] >= threshold and threshold >= y_predict[i]:
            pred_rpe = i 
            break
    return abs(true_rpe - pred_rpe)/true_rpe

def evaluation(y_test, y_predict):
    mse = mean_squared_error(y_test, y_predict)
    rmse = sqrt(mean_squared_error(y_test, y_predict))
    #precision = precision_score(y_test, y_predict, average=None)
    return rmse


def setup_seed(seed):
    np.random.seed(seed)  # Numpy module.
    random.seed(seed)  # Python random module.
    os.environ['PYTHONHASHSEED'] = str(seed)
    torch.manual_seed(seed) 
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed) 
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True


class Autoencoder(nn.Module):
    def __init__(self, input_size=16, hidden_dim=8, noise_level=0.01):
        super(Autoencoder, self).__init__()
        self.input_size, self.hidden_dim, self.noise_level = input_size, hidden_dim, noise_level
        self.fc1 = nn.Linear(self.input_size, self.hidden_dim)
        self.fc2 = nn.Linear(self.hidden_dim, self.input_size)
        
    def encoder(self, x):
        x = self.fc1(x)
        h1 = F.relu(x)
        return h1
    
    def mask(self, x):
        corrupted_x = x + self.noise_level * torch.randn_like(x)
        return corrupted_x
    
    def decoder(self, x):
        h2 = self.fc2(x)
        return h2
    
    def forward(self, x):
        out = self.mask(x)
        encode = self.encoder(out)
        decode = self.decoder(encode)
        return encode, decode

 
class PositionalEncoding(nn.Module):
    
    def __init__(self, d_model, max_len=5000):
        
        super(PositionalEncoding, self).__init__()      
        
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        #pe.requires_grad = False
        self.register_buffer('pe', pe)
 
    def forward(self, x):
        x = x + self.pe[:x.size(1), :].squeeze(1)
        return x

          
 
class Net(nn.Module):
    def __init__(self, feature_size=16, hidden_dim=32, num_layers=1, nhead=8, dropout=0.0, noise_level=0.01):
        super(Net, self).__init__()
        self.auto_hidden = int(feature_size/2)
        input_size = self.auto_hidden 
        self.pos = PositionalEncoding(d_model=input_size, max_len=input_size)
        encoder_layers = nn.TransformerEncoderLayer(d_model=input_size, nhead=nhead, dim_feedforward=hidden_dim, dropout=dropout)
        self.cell = nn.TransformerEncoder(encoder_layers, num_layers=num_layers)
        self.linear = nn.Linear(input_size, 1)
        self.autoencoder = Autoencoder(input_size=feature_size, hidden_dim=self.auto_hidden, noise_level=noise_level)
 
    def forward(self, x): 
        batch_size, feature_num, feature_size  = x.shape 
        encode, decode = self.autoencoder(x.reshape(batch_size, -1))# batch_size*seq_len
        out = encode.reshape(batch_size, -1, self.auto_hidden)
        out = self.pos(out)
        out = out.reshape(1, batch_size, -1) # (1, batch_size, feature_size)
        out = self.cell(out)  
        out = out.reshape(batch_size, -1) # (batch_size, hidden_dim)
        out = self.linear(out)            # out shape: (batch_size, 1)
        
        return out, decode

           
def test(lr=0.01, feature_size=8, hidden_dim=32, num_layers=1, nhead=8, weight_decay=0.0, EPOCH=1000, seed=0, 
         alpha=0.0, noise_level=0.0, dropout=0.0, metric='re', is_load_weights=True):
    score_list, result_list = [], []
    setup_seed(seed)
    for i in range(40):
        name = Battery_list[i]
        window_size = feature_size
        train_x, train_y, train_data, test_data = get_train_test(Battery, name, window_size) #size:train_x=17,train_y=151,train_data=17,test_data=151
        np.savetxt('Data/Test/train_data_' + str(i) + '.csv', train_data, delimiter=',')
        np.savetxt('Data/Test/test_data_' + str(i) + '.csv', test_data, delimiter=',')
        train_size = len(train_x)
        print('sample size: {}'.format(train_size))

        model = Net(feature_size=feature_size, hidden_dim=hidden_dim, num_layers=num_layers, nhead=nhead, dropout=dropout,
                    noise_level=noise_level)
        model = model.to(device)
        if is_load_weights: 
            if torch.__version__.split('+')[0] >= '1.6.0':
                #model.load_state_dict(torch.load('Data/Transformer_12/Transformer_12_15.pth'))
                model = torch.load('Data/DeTransformer.pkl')
            else:
                model.load_state_dict(torch.load(''))
        
        
        '''
        # save ramdom data for repetition
        if torch.__version__.split('+')[0] >= '1.6.0':
            torch.save(model.state_dict(), 'Data/Test_seed'+str(seed)+'.pth')
        else:
            torch.save(model.state_dict(), 'Data/Test.pth', _use_new_zipfile_serialization=False)        
        '''
        '''
        # load the random data generated by my device
        if is_load_weights: 
            if torch.__version__.split('+')[0] >= '1.6.0':
                model.load_state_dict(torch.load('initial_weights/model_NASA.pth')) 
            else:
                model.load_state_dict(torch.load('initial_weights/model_NASA_1.5.0.pth'))
        '''
        

        test_x = train_data.copy()
        loss_list, y_ = [], []
        rpe, rmse, mae = 0, 0, 0
        score = [],[]
        
        
        
        point_list = []
        while (len(test_x) - len(train_data)) < len(test_data): #0~[161:-1]
            x = np.reshape(np.array(test_x[-feature_size:])/Rated_Capacity,(-1, 1, feature_size)).astype(np.float32)
            x = torch.from_numpy(x).to(device)   # shape (batch_size,feature_size=1,input_size)
            pred, _ = model(x)                   # pred shape: (batch_size=1, feature_size=1)
            next_point = pred.data.cpu().numpy()[0,0] * Rated_Capacity
            test_x.append(next_point)      # The test values are added to the original sequence to continue to predict the next point
            point_list.append(next_point)  # Saves the predicted value of the last point in the output sequence
        y_ = point_list.copy()           # Save all the predicted values
        print(len(y_))
                
        rpe = relative_positional_error(y_test=test_data, y_predict=y_, threshold=Rated_Capacity*0.8)
        rmse = evaluation(y_test=test_data, y_predict=y_)
        mae = mean_absolute_error(test_data, y_)
        #print('Epoch:{:<2d} | loss:{:<6.4f} | RPE:{:<6.4f} | RMSE:{:<6.4f} | MAE:{:<6.4f}'.format(epoch, loss, rpe, rmse, mae))
        if metric == 'rpe':
            score = [rpe]
        elif metric == 'rmse':
            score = [rmse]
        elif metric == 'mae':
            score =[mae]
        else:
            score = [rpe, rmse, mae]
        
            
        print('------------------------------------------------------------------')
        print('Battery_list:{:<2d} | RPE:{:<6.4f} | RMSE:{:<6.4f} | MAE:{:<6.4f}'.format(i, rpe, rmse, mae))
        np.savetxt('Data/Test/predict_list_test_' + str(i) + '.csv', y_, delimiter=',')   
        with open('Data/Test/predict_list_test_' + str(i) + '.pkl', 'wb') as fp:
            pickle.dump(y_, fp)
        score_list.append(score)
        result_list.append(y_)
    return score_list, result_list, y_, loss_list


Rated_Capacity = 1.1
window_size = 16
feature_size = window_size
dropout = 0.0
EPOCH = 10000
nhead = 8
hidden_dim = 64
num_layers = 1
lr = 0.0043    # learning rate
weight_decay = 0.0
noise_level = 0.0
alpha = 1e-5
is_load_weights = True
metric = 'error'
seed = 0


SCORE_rpe, SCORE_rmse, SCORE_mae  = [], [], []
print('seed:{}'.format(seed))
score_list, result_list, predict_list, loss_list= test(lr=lr, feature_size=feature_size, hidden_dim=hidden_dim, num_layers=num_layers, nhead=nhead, 
                      weight_decay=weight_decay, EPOCH=EPOCH, seed=seed, dropout=dropout, alpha=alpha, 
                      noise_level=noise_level, metric=metric, is_load_weights=is_load_weights)
with open('Data/Test/predict_list.pkl', 'wb') as fp:
            pickle.dump(result_list, fp)
print(np.array(score_list))
np.savetxt('Data/Test/score_list_test.csv', score_list, delimiter=',')
for s in score_list:
    SCORE_rpe.append(s[0])
    SCORE_rmse.append(s[1])
    SCORE_mae.append(s[2])
print('------------------------------------------------------------------')
#print(metric + ' mean: {:<6.4f}'.format(np.mean(np.array(SCORE))))
print('rpe mean:{:<6.4f} | rmse mean:{:<6.4f} | mae mean:{:<6.4f}'.format(np.mean(np.array(SCORE_rpe)), np.mean(np.array(SCORE_rmse)), np.mean(np.array(SCORE_mae))))
# Calculate the means
mean_rpe = np.mean(np.array(SCORE_rpe))
mean_rmse = np.mean(np.array(SCORE_rmse))
mean_mae = np.mean(np.array(SCORE_mae))

# Stack the means into a single array
mean_values = np.array([mean_rpe, mean_rmse, mean_mae])

# Save the means to a CSV file
np.savetxt('Data/Test/Test_Score.csv', mean_values, delimiter=',')
