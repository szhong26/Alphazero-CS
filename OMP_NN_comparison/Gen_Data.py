#Class which generates sensing_matrices A, observed vectors y, sparse vectors x
import numpy as np
import math
from scipy.linalg import dft
import random
import csv
import os
from CSAlgorithms import CSAlgorithms

class GenData(): #Generates A, x, y. Also generates training data for neural network models with different inputs. 
    def __init__(self):
        self.A = None
        self.y = None
        self.x = None
        
    def generate_SensingMatrix(self, args):
        if args['matrix_type'] == 'sdnormal':
            self.A = np.random.normal(0,1, (args['m'], args['n']))
            for i in range(args['n']):
                self.A[:,i] = self.A[:,i]/np.linalg.norm(self.A[:,i])
        if args['matrix_type'] == 'fourier':
            DFT = dft(args['n'])
            rows = [x for x in range(args['m'])]
            random.shuffle(rows)
            self.A = DFT[np.ix_(rows)]
        
    def generate_ObsVector(self, args, sparsity): #generate y from a sparse vector x with given sparsity
        x = np.zeros(args['n'])
        if args['x_type'] == 'sdnormal':
            x[0:sparsity] = np.random.normal(0,1,sparsity)
            np.random.shuffle(x)
            self.x = x
            self.y = np.matmul(self.A, self.x)
            
    def save_SensingMatrix(self, matrix_folder, matrix_filename): #matrix_folder is usually args['matrix_folder'].
        np.save(matrix_folder + matrix_filename, self.A)
        
    
    def gen_CSData(self, args):  
    #generate matrices, sparse vectors, and observed vectors and dump them into a file. Training data will be generated from these matrices, sparse vectors, and observed vectors using methods below.
    #This method must be run for all methods below to work
        for m in range(args['matrices_generated']):
            self.generate_SensingMatrix(args)
            os.mkdir(args['matrix_folder'] + '/matrix' + str(m))
            self.save_SensingMatrix(args['matrix_folder'] + '/matrix' + str(m), '/' + args['matrix_type'] + str(m) + '.npy') 
            os.mkdir(args['matrix_folder'] + '/matrix'+ str(m) + '/y_x_data')
            for signals_generated in range(1, args['x_generated']):
                s = random.randint(1, args['max_sparsity'])
                self.generate_ObsVector(args, s)
                with open(args['matrix_folder'] +'/matrix' + str(m) + '/y_x_data/obs_y.csv', 'a') as output:
                    writer = csv.writer(output)
                    writer.writerows([self.y])
                with open(args['matrix_folder'] + '/matrix' + str(m) + '/y_x_data/sparse_x.csv', 'a') as output:
                    writer = csv.writer(output)
                    writer.writerows([self.x])
    
    def gen_naiveNNTraining(self, args): #self.gen_CSData(args) must be run first. Read in raw data and transform into something naive Net recognizes. Dump all this data into a new file.
        for m in range(args['matrices_generated']):  
            os.mkdir(args['naiveNN_training_filepath'] + '/matrix' + str(m))     
            with open(args['naiveNN_training_filepath'] + '/matrix' + str(m) + '/NNfeatures_y.csv', 'a') as output_file_features, open(args['naiveNN_training_filepath'] + '/matrix' + str(m) + '/NNlabels_x.csv', 'a') as output_file_labels:
                writer_features = csv.writer(output_file_features)
                writer_labels = csv.writer(output_file_labels)        
                with open(args['matrix_folder'] + '/matrix' + str(m) + '/y_x_data/obs_y.csv', 'r') as raw_features:
                    reader_y = csv.reader(raw_features)
                    for y in reader_y:
                        y = list(map(float, y)) #y is now a list of floats. map(float,y) turns all entries of y into floats
                        writer_features.writerows([y])
                with open(args['matrix_folder'] + '/matrix' + str(m) + '/y_x_data/sparse_x.csv', 'r') as raw_labels:
                    reader_x = csv.reader(raw_labels)
                    for x in reader_x:
                        x = list(map(float, x))
                        writer_labels.writerows([x])
             
    def gen_OMPbootstrapNNTraining(self, args): #self.gen_CSData(args) must be run first. Read in raw data and transform into something recognizable by OMPbootstrap NN. 
        algorithms = CSAlgorithms() #create algorithms object for use later...
        for m in range(args['matrices_generated']):
            #Make new directory for each matrix to save our constructed data
            if not os.path.exists(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m)): 
                os.mkdir(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m))
            if not os.path.exists(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m) + '/features'):
                os.mkdir(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m) + '/features')
            if not os.path.exists(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m) + '/labels'):
                os.mkdir(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m) + '/labels')
            with open(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m) + '/features' + '/NNfeature_xS.csv', 'a') as output_file_features1, open(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m) + '/features' + '/NNfeature_lambda.csv', 'a') as output_file_features2, open(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m) + '/labels' + '/NNlabel_pas.csv', 'a') as output_file_labels1, open(args['OMPbootstrap_training_filepath'] + '/matrix' + str(m) + '/labels' + '/NNlabel_v.csv', 'a') as output_file_labels2:
                writer_features_xS = csv.writer(output_file_features1)
                writer_features_lambda = csv.writer(output_file_features2)
                writer_labels_pas = csv.writer(output_file_labels1)
                writer_labels_v = csv.writer(output_file_labels2)
                with open(args['matrix_folder'] + '/matrix' + str(m) + '/y_x_data/obs_y.csv', 'r') as raw_features, open(args['matrix_folder'] + '/matrix' + str(m) + '/y_x_data/sparse_x.csv', 'r') as raw_labels:
                    reader_y = csv.reader(raw_features)
                    reader_x = csv.reader(raw_labels)
                    #load the sensing matrix for computing our signals when reading the raw observed signals
                    A = np.load(args['matrix_folder'] + '/matrix' + str(m) + '/' + args['matrix_type'] + str(m) + '.npy')
                    #i = 0
                    for y, x in zip(reader_y, reader_x):
                    #Convert features into a format we can feed into neural network and save
                        y = list(map(float, y))
                        y = np.asarray(y)
                        #y = y/np.linalg.norm(y) #normalize y for numerical stability purposes with orthogonal_mp
                        #linear time operation below...
                        x = list(map(float, x))
                        x = np.asarray(x)
                        s = np.count_nonzero(x)
                        #Construct new_features, new_labels for a SINGLE INSTANCE of (A, y) by calling algorithms.OMP(). Note that a single 
                        #instance of (A,y) creates many training examples. 
                        #features is of the form (x_S, lambda), and labels is the form of pi, a one-hot vector of the next column chosen. 
                        features, labels = algorithms.OMP(A, y, s)
                        #i += 1
                        #Write new features and labels into the above created files
                        for feature, label in zip(features, labels):
                            writer_features_xS.writerows([feature[0]])
                            writer_features_lambda.writerows([feature[1]])
                            writer_labels_pas.writerows([label[0]])
                            writer_labels_v.writerows([label[1]])
    
    def gen_testData(self, args):
    #INPUT: None
    #OUTPUT: generate args number of test signals and save them to testData file
    #FUNCTION: generate test data from the constructed matrices in gen_CSData above to compare OMP, l1, NN, OMPbootstrapNNTraining, etc....
        for m in range(args['matrices_generated']):
            self.A = np.load(args['matrix_folder'] + '/matrix' + str(m) + '/' + args['matrix_type'] + str(m) + '.npy')
            matrix_folder = args['testData_folder'] + '/' + 'matrix' + str(m) #make folder corresponding to matrix m
            if not os.path.exists(matrix_folder):
                os.mkdir(matrix_folder)
            for sparsity in range(1, args['max_sparsity']):
                sparsity_folder = matrix_folder + '/' + str(sparsity) + 'sparse' #make folder corresponding to sparsity
                if not os.path.exists(sparsity_folder):
                    os.mkdir(sparsity_folder)
                for signals_generated in range(args['test_signals_generated']):
                    self.generate_ObsVector(args, sparsity)
                    filename1 = '/' + str(sparsity) + 'sparse' + '_obsy.csv'
                    filename2 = '/' + str(sparsity) + 'sparse' + '_x.csv'
                    with open(sparsity_folder + filename1, 'a') as output:
                        writer = csv.writer(output)
                        writer.writerows([self.y])
                    with open(sparsity_folder + filename2, 'a') as output:
                        writer = csv.writer(output)
                        writer.writerows([self.x])
                    
                
                
 
    
           

        
        

