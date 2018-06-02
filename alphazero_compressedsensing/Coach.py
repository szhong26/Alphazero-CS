from collections import deque
from Arena import Arena
from MCTS import MCTS
import numpy as np
from pytorch_classification.utils import Bar, AverageMeter
import time, os, sys
from pickle import Pickler, Unpickler
from random import shuffle
from compressed_sensing.Game_Args import Game_args


class Coach():
    """
    This class executes the self-play + learning. It uses the functions defined
    in Game and NeuralNet. args are specified in main.py.  Game_args specified in Game_Args.py
    """
    def __init__(self, game, nnet, args, game_args):
        self.args = args
        self.game_args = game_args #Game_args object contains information about matrix A and observed vector y. THIS SINGLE GAME ARGS IS USED FOR GENERATING THE A AND y FOR SELF PLAY GAMES!!! ONLY. 
        self.arena_game_args = Game_args() #object used to generate instances of A and y across all arenas objects in learn
        self.game = game
        self.nnet = nnet    #new neural network wrapper object
        # the competitor network. SZ: Our competitor network is just another network which plays the same game as another network 
        # and we compare which network picks the sparsest vector. The network which picks the sparsest vector is chosen and we remember these weights.
        self.pnet = self.nnet.__class__(self.args)  #past neural network. self.nnet is a NNetWrapper object, and self.pnet = self.nnet.__class__(self.args) instantiates another instance of the NNetWrapper object with self.args as input. self.pnet and self.nnet are not pointing to the same thing.                              
        self.mcts = MCTS(self.game, self.nnet, self.args, self.game_args) #THIS MCTS OBJECT IS REINITIALIZED(Qsa, Nsa, Ns, Es, etc.... to empty dics) WHENEVER WE PLAY A NEW SELF PLAY GAME IN learn()
        self.trainExamplesHistory = []    # history of examples from args.numItersForTrainExamplesHistory latest iterations
        self.skipFirstSelfPlay = False # can be overriden in loadTrainExamples()

    def executeEpisode(self): 
    #NOTE CURRENTLY THAT IF THE STOPPING ACTION IS CHOSEN, THEN THE STATE WITH STOPPING ACTION SET TO 1 WILL NOT BE IN trainExamples!!
    #WHAT IF STOPPING ACTION IS TAKEN IMMEDIATELY AFTER INITIAL GAME STATE?
        #INPUT: None
        #
        #OUTPUT: list of state objects, where for every state, state.pi_as, state.z, and state.feature_dic have all been
        #updated
        #FUNCTION:We play a single game until we reach a end/terminal state. Each state
        #is saved and the policy distribution is also saved. When we reach a terminal state,
        #we propagate the final result z to each state object. In this method, each state object 
        #has state.feature_dic, state.pi_as, and state.z updated. Finally every state in states is
        #converted into a format recognizable by the Neural Network. 
        
        state = self.game.getInitBoard(self.args, self.game_args) #State Object
        action_size = self.game.getActionSize(self.args)
        states = [] #will convert all states into X using NNet.convertStates
        trainExamples = []
        
        #After episodeStep number of played moves into a single game (>= tempTHreshold), MCTS.getActionProb
        #starts returning deterministic policies pi. Hence, the action chosen to get the next state
        #for our root node will be deterministic. The higher the integer tempThreshold is,
        #the more randomness introduced in generating our training samples before move tempThreshold.
        
        episodeStep = 0
        
        while True: #construct a list of states objects, where each state has state.p_as, state.z, and state.feature_dic updated. These are needed for conversion into training samples in NNetWrapper.constructTraining
            episodeStep += 1
            temp = int(episodeStep < self.args['tempThreshold']) #int(True) = 1, o.w. 0
            
            #Note that MCTS.getActionProb runs a fixed number of MCTS.search determined by 
            #args['numMCTSSims']
            pi = self.mcts.getActionProb(state, temp=temp)
            state.pi_as = pi #update the label pi_as since getActionProb does not do this
            #Construct the States_List and Y
            states.append(state)
            #choose a random action (integer) with prob in pi.
            action = np.random.choice(len(pi), p=pi)
            #FOR TESTING------------------
            #print('The next action taken is: ' + str(action))
            #-----------------------------
            #Given the randomly generated action, move the root node to the next state.   
            state = self.game.getNextState(state, action)

            r = self.game.getGameEnded(state, self.args, self.game_args) #float value
            #FOR TESTING------------------
            #print('The reward for the next state ' + str(state.col_indices) + ' is: ' + str(r))
            #-----------------------------
            
            #return breaks out of the while loop. If r not equal to 0, that means the state we are
            #on is a terminal state, which implies we should propagate the rewards up to every 
            #state in states
            if r!=0:
                states.append(state) #append the last state with nonzero reward. Note that p_as of the last terminal state is a vector of zeros. Refer to the default constructor of the State object
                for state in states:
                    #compute state.feature_dic
                    state.compute_x_S_and_res(self.args, self.game_args)
                    #compute the label state.z
                    state.z = r
                trainExamples = states 
                return trainExamples #returns a list of state objects with features, labels all computed
                
    
    #learn() IS THE PRIMARY METHOD WHICH STARTS ALPHAZERO!!!
    def learn(self):
        """
        Performs numIters iterations with numEps episodes of self-play in each
        iteration. After every iteration, it retrains neural network with
        examples in trainExamples (which has a maximium length of maxlenofQueue).
        It then pits the new neural network against the old one and accepts it
        only if it wins >= updateThreshold fraction of games.
        """
        #IF A is fixed, then generate A here before loop below. Also, set arena_game_args.sensing_matrix to be equal to that of coach.game_args
        if self.args['fixed_matrix'] == True:
            self.game_args.generateSensingMatrix(self.args['m'], self.args['n'], self.args['matrix_type'])
            self.arena_game_args.sensing_matrix = self.game_args.sensing_matrix
            #Save the fixed matrix
            self.game_args.save_Matrix(self.args['fixed_matrix_filepath'])

        for i in range(1, self.args['numIters']+1):
            print('------ITER ' + str(i) + '------')
            if not self.skipFirstSelfPlay or i>1: #default of self.skipFirstSelfPlay is False. If loading training from file then skipFirstSelfPlay is set to True. skipFirstSelfPlay allows us to load the latest nn_model with latest set of TrainingExamples
                iterationTrainExamples = deque([], maxlen=self.args['maxlenOfQueue'])
                #bookkeeping objects contained in pytorch_classification.utils
                eps_time = AverageMeter()
                bar = Bar('Self Play', max=self.args['numEps'])
                end = time.time()
                #IMPORTANT PART OF THE CODE. GENERATE NEW A AND NEW y HERE. EACH SELF-PLAY GAME HAS DIFFERENT A AND y. 
                #-----------------------------------------------------
                for eps in range(self.args['numEps']):
                    #Initialize a new game by setting A, x, y, and then execute a single game of self play with self.executeEpisode()
                    if self.args['fixed_matrix'] == False:
                        self.game_args.generateSensingMatrix(self.args['m'], self.args['n'], self.args['matrix_type']) #generate a new sensing matrix
                    self.game_args.generateNewObsVec(self.args['x_type'], self.args['sparsity'])#generate a new observed vector y
                    self.mcts = MCTS(self.game, self.nnet, self.args, self.game_args)#create new search tree for each game we play
                    iterationTrainExamples += self.executeEpisode() #Play a new game with newly generated y. iterationTrainExamples is a deque containing states each generated self play game
                #-----------------------------------------------------
                    # bookkeeping + plot progress
                    eps_time.update(time.time() - end)
                    end = time.time()
                    bar.suffix  = '({eps}/{maxeps}) Eps Time: {et:.3f}s | Total: {total:} | ETA: {eta:}'.format(eps=eps+1, maxeps=self.args['numEps'], et=eps_time.avg, total=bar.elapsed_td, eta=bar.eta_td)
                    bar.next()
                bar.finish()

                # save the iteration examples to the history 
                #self.trainExamplesHistory is a list of deques, where each deque contains all the states from numEps number of self-play games
                self.trainExamplesHistory.append(iterationTrainExamples)
                
            if len(self.trainExamplesHistory) > self.args['numItersForTrainExamplesHistory']:
                print("len(trainExamplesHistory) =", len(self.trainExamplesHistory), " => remove the oldest trainExamples")
                self.trainExamplesHistory.pop(0)
            # backup history to a file by calling saveTrainExamples method
            # The examples were collected using the model from the previous iteration, so (i-1)  
            self.saveTrainExamples(i-1) #save examples to self.args['checkpoint'] folder with given iteration name of i-1
            
            # shuffle examples before training
            #trainExamples is the list form of trainExamplesHistory. Note that trainExamplesHistory is a list of deques,
            #where each deque contains training examples. trainExamples gets rid of the deque, and instead puts all training
            #samples in a single list, shuffled
            trainExamples = []
            for e in self.trainExamplesHistory: #Each e is a deque
                trainExamples.extend(e)
            shuffle(trainExamples)
            
            #The Arena--------------------------------------------------------
            if self.args['Arena'] == True:
                self.nnet.save_checkpoint(folder=self.args['network_checkpoint'], filename='temp') #copy old neural network into new one
                self.pnet.load_checkpoint(folder=self.args['network_checkpoint'], filename='temp')
            
                #convert trainExamples into a format recognizable by Neural Network and train
                trainExamples = self.nnet.constructTraining(trainExamples)
                self.nnet.train(trainExamples[0], trainExamples[1])#Train the new neural network self.nnet. The weights are now updated
            
                #Pit the two neural networks self.pnet and self.nnet in the arena            
                print('PITTING AGAINST PREVIOUS VERSION')
            
                arena = Arena(self.pnet, self.nnet, self.game, self.args, self.arena_game_args) #note that Arena will pit pnet with nnet, and Game_args A and y will change constantly. Note that next iteration, arena is a reference to a different object, so old object is deleted when there are no other references to it. 
                pwins, nwins, draws = arena.playGames()
            
                print('NEW/PREV WINS : %d / %d ; DRAWS : %d' % (nwins, pwins, draws))
                if pwins+nwins > 0 and float(nwins)/(pwins+nwins) < self.args['updateThreshold']:
                    print('REJECTING NEW MODEL')
                    self.nnet.load_checkpoint(folder=self.args['network_checkpoint'], filename='temp')
                else:#saves the weights(.h5) and model(.json) twice. Creates nnet_checkpoint(i-1)_model.json and nnet_checkpoint(i-1)_weights.h5, and rewrites best_model.json and best_weights.h5
                    print('ACCEPTING NEW MODEL')
                    self.nnet.save_checkpoint(folder=self.args['network_checkpoint'], filename='nnet_checkpoint' + str(i-1))
                    self.nnet.save_checkpoint(folder=self.args['network_checkpoint'], filename='best')
            #-----------------------------------------------------------------
            
            else:
                print('TRAINING NEW NEURAL NETWORK...')
                trainExamples = self.nnet.constructTraining(trainExamples)
                self.nnet.train(trainExamples[0], trainExamples[1])          
                self.nnet.save_checkpoint(folder = self.args['network_checkpoint'], filename='nnet_checkpoint' + str(i-1))
                self.nnet.save_checkpoint(folder=self.args['network_checkpoint'], filename = 'best')

    def getCheckpointFile(self, iteration): #return a string which gives information about current checkpoint iteration
    #and file type (.tar)
        return 'checkpoint_' + str(iteration) + '.pth.tar'

    def saveTrainExamples(self, iteration): #save training examples (self.trainExamplesHistory to 
        #args['checkpoint'] folder with name of self.getCheckpointFile with given iteration. 
        folder = self.args['checkpoint']
        if not os.path.exists(folder): #if folder specified by args['checkpoint'] does not exist, then make it. 
            os.makedirs(folder)
        filename = os.path.join(folder, self.getCheckpointFile(iteration)+".examples")
        with open(filename, "wb+") as f:
            Pickler(f).dump(self.trainExamplesHistory)
        f.closed

    def loadTrainExamples(self): #Not used above in learn(), but will be of use in main.py
    #load training examples from folder args['load_folder_(folder)'], with filename args['load_folder_(filename)'] + '.examples'
    #OUTPUT: set self.trainExamplesHistory as the training samples in the above file, and set skipFirstSelfPlay = True
        modelFile = os.path.join(self.args['load_folder_(folder)'], self.args['load_folder_(filename)'])
        examplesFile = modelFile+".examples"
        if not os.path.isfile(examplesFile):
            print(examplesFile)
            r = input("File with trainExamples not found. Continue? [y|n]")
            if r != "y":
                sys.exit()
        else:
            print("File with trainExamples found. Read it.")
            with open(examplesFile, "rb") as f:
                self.trainExamplesHistory = Unpickler(f).load()
            f.closed
            # examples based on the model were already collected (loaded)
            self.skipFirstSelfPlay = True



    
