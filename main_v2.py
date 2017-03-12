import numpy as np
import tensorflow as tf
from tensorflow.contrib import rnn
from preprocess import readOurData
from model import Model
import time

# from util import print_sentence, write_conll, read_conll
from data_util import load_and_preprocess_data
from utils.general_utils import Progbar
from utils.parser_utils import minibatches, load_and_preprocess_data
from rnncell import RNNCell
from config import Config

''' 
Set up classes and functions 
'''
# class Config(object):
#
#     drop_out = 0.5
#     hidden_size = 200
#     batch_size = 32
#     epochs = 10
#     lr = 0.001
#     l2Reg = 1.0e-6
#     # built when we construct the model
#     max_sentence = 0
#     n_class = 0
#     embedding_size = 0

###############
### RNN Cell ##
###############

# class RNNCell(tf.nn.rnn_cell.RNNCell):
#     """Wrapper around our RNN cell implementation that allows us to play
#     nicely with TensorFlow.
#     """
#     def __init__(self, input_size, state_size, name_suffix):
#         self.input_size = input_size
#         self._state_size = state_size
#         self._name_suffix = name_suffix
#
#     @property
#     def state_size(self):
#         return self._state_size
#
#     @property
#     def output_size(self):
#         return self._state_size
#
#     def __call__(self, inputs, state, scope=None):
#         """Updates the state using the previous @state and @inputs.
#         Args:
#             inputs: is the input vector of size [None, self.input_size]
#             state: is the previous state vector of size [None, self.state_size]
#             scope: is the name of the scope to be used when defining the variables inside.
#         Returns:
#             a pair of the output vector and the new state vector.
#         """
#         scope = scope or type(self).__name__
#
#         # It's always a good idea to scope variables in functions lest they
#         # be defined elsewhere!
#         with tf.variable_scope(scope):
#             ## layer one
#             W_x = tf.get_variable(name = "W_x" + str(self._name_suffix),
#                                   shape = (self.input_size, self._state_size),
#                                   dtype = tf.float32,
#                                   initializer = tf.contrib.layers.xavier_initializer())
#
#             W_h = tf.get_variable(name = "W_h" + str(self._name_suffix),
#                                   shape = (self._state_size, self._state_size),
#                                   dtype = tf.float32,
#                                   initializer = tf.contrib.layers.xavier_initializer())
#             b = tf.get_variable(name = "b" + str(self._name_suffix),
#                                 shape = (self._state_size,),
#                                 dtype = tf.float32,
#                                 initializer = tf.constant_initializer(0.0))
#
#             output = tf.tanh(tf.matmul(inputs, W_x) + tf.matmul(state, W_h) + b)
#         return output

#################
### RNN Model ###
#################

class RNNModel(Model):

    def _read_data(self, train_path, dev_path, embedding_path):
        '''
        Helper function to read in our data. Used to construct our RNNModel
        :param train_path: path to training data
        :param dev_path: path to development data
        :param embedding_path: path to embeddings
        :return: read in training/development data with padding masks and
        embedding dictionaries
        '''
        from preprocess import readOurData
        train_x_pad, train_y, train_mask, dev_x_pad, dev_y, dev_mask, embeddingDictPad = readOurData(
            train_path, dev_path, embedding_path)
        return train_x_pad, train_y, train_mask, dev_x_pad, dev_y, dev_mask, embeddingDictPad

    def add_placeholders(self):
        # batchSize X sentence X numClasses
        self.inputPH = tf.placeholder(dtype = tf.int32,
                                 shape = (None, self.config.max_sentence),
                                 name = 'input')
        # batchSize X numClasses
        self.labelsPH = tf.placeholder(dtype = tf.float32,
                                  shape = (None, self.config.n_class),
                                  name = 'labels')
        # mask over sentences not long enough
        self.maskPH = tf.placeholder(dtype = tf.bool,
                                shape = (None, self.config.max_sentence),
                                name = 'mask')
        # # batchSize X sentence X numClasses
        # self.inputPH = tf.placeholder(dtype = tf.int32,
        #                          shape = (self.config.batch_size, self.config.max_sentence),
        #                          name = 'input')
        # # batchSize X numClasses
        # self.labelsPH = tf.placeholder(dtype = tf.float32,
        #                           shape = (self.config.batch_size, self.config.n_class),
        #                           name = 'labels')
        # # mask over sentences not long enough
        # self.maskPH = tf.placeholder(dtype = tf.bool,
        #                         shape = (self.config.batch_size, self.config.max_sentence),
        #                         name = 'mask')
        self.dropoutPH = tf.placeholder(dtype = tf.float32,
                                   shape = (),
                                   name = 'dropout')
        # self.seqPH = tf.placeholder(dtype = tf.float32,
        #                        shape = (self.config.batch_size,),
        #                        name = 'sequenceLen')
        self.l2RegPH = tf.placeholder(dtype = tf.float32,
                                 shape = (),
                                 name = 'l2Reg')

    def create_feed_dict(self, inputs_batch, mask_batch, labels_batch=None, dropout=1, l2_reg=0):

        feed_dict = {
            self.inputPH: inputs_batch,
            self.maskPH: mask_batch,
            self.dropoutPH: dropout,
            self.l2RegPH: l2_reg
        }

        # Add labels if not none
        if labels_batch is not None:
            feed_dict[self.labelsPH] = labels_batch

        return feed_dict

    def add_embedding(self):
        embedding_shape = (-1,
                           self.config.max_sentence,
                           self.config.embedding_size)
        # embedding_shape = (self.config.batch_size,
        #                    self.config.max_sentence,
        #                    self.config.embedding_size)

        pretrainEmbeds = tf.Variable(self.pretrained_embeddings,
                                     dtype = tf.float32)
        embeddings = tf.nn.embedding_lookup(pretrainEmbeds, self.inputPH)
        embeddings = tf.reshape(embeddings, shape=embedding_shape)

        return embeddings

    def add_prediction_op(self):
        # preds = [] # predicted output at each timestep

        # get relevent embedding data
        x = self.add_embedding()
        mask = self.train_mask
        currBatch = tf.shape(x)[0]

        # Extract sizes
        hidden_size = self.config.hidden_size
        n_class = self.config.n_class
        batch_size = self.config.batch_size
        max_sentence = self.config.max_sentence
        embedding_size = self.config.embedding_size

        # Define internal RNN Cells
        cell1 = RNNCell(embedding_size, hidden_size, "cell1")
        cell2 = RNNCell(hidden_size, hidden_size, "cell2")

        # Define our prediciton layer variables
        W = tf.get_variable(name = 'W',
                            shape = ((2 * hidden_size), n_class),
                            dtype = tf.float32,
                            initializer = tf.contrib.layers.xavier_initializer())

        b = tf.get_variable(name = 'b',
                            shape = (n_class,),
                            dtype = tf.float32,
                            initializer = tf.constant_initializer(0.0))

        # Initialize our hidden state for each RNN layer
        h1_Prev = tf.zeros(shape = (currBatch, hidden_size),
                           dtype = tf.float32)
        h2_Prev = tf.zeros(shape = (currBatch, hidden_size),
                           dtype = tf.float32)

        # # Store last hidden state before mask for each sentence in embedding
        # h1_last = tf.zeros(shape = (currBatch, hidden_size),
        #                    dtype = tf.float32)
        # h2_last = tf.zeros(shape = (currBatch, hidden_size),
        #                    dtype = tf.float32)

        for time_step in range(max_sentence):
            if time_step > 0:
                tf.get_variable_scope().reuse_variables()

            # check if complete
            # complete = True
            # i = tf.constant(0)
            # while_condition = lambda i: tf.less(i, currBatch)
            # def body(i):
            #     complete = complete and mask[i, time_step]
            #     return complete
            # for i in range(currBatch):
            #     complete = complete and mask[i, time_step]
            # if complete:
            #     break
            # complete = tf.constant(True)
            # for i in range(self.config.batch_size):
            #     complete = tf.logical_and(complete, mask[i, time_step])
            #         # complete and mask[i, time_step]
            #     if tf.less(tf.constant(i), currBatch):
            #         break
            # tf.cond(tf.equal(complete, tf.constant(True)), lambda: break, lambda: pass)
            # tf.control_flow_ops.cond(complete, lambda: break, lambda: pass)
            # tf.case(tf.equal(complete, tf.constant(True)), break)
            # if tf.equal(complete, tf.constants(True)):
            #     break


            # First RNN Layer - uses embeddings
            h1_t = cell1(x[:, time_step, :], h1_Prev)
            h1_drop_t = tf.nn.dropout(h1_t, keep_prob = self.dropoutPH)

            # over-write with prior states
            # for i in range(currBatch):
            #     if mask[i, time_step] == False:
            #         h1_t[i, :] = h1_Prev[i, :]

            # Second RNN Layer - uses First layer hidden states
            h2_t = cell2(h1_drop_t, h2_Prev)
            h2_drop_t = tf.nn.dropout(h2_t, keep_prob = self.dropoutPH)

            h1_Prev = h1_t
            h2_Prev = h2_t

            # for i in range(currBatch):
            #     if mask[i, time_step] == False:
            #         h1_last[i, :] = h1_drop_t[i, :]
            #         h2_last[i, :] = h2_drop_t[i, :]

        # Concatenate last states of first and second layer for prediction layer
        h_t = tf.concat(concat_dim = 1, values = [h1_drop_t, h2_drop_t])
        y_t = tf.tanh(tf.matmul(h_t, W) + b)
        # preds.append(y_t)
        return y_t

    def add_loss_op(self, pred):
        # Compute L2 loss
        L2loss = tf.nn.l2_loss(self.labelsPH - pred)
        L2loss = tf.reduce_mean(L2loss)

        # Apply L2 regularization
        reg_by_var = [tf.nn.l2_loss(v) for v in tf.trainable_variables()]
        regularization = tf.reduce_sum(reg_by_var)

        loss = (10.0 * L2loss) + (self.l2RegPH * regularization)
        return loss

    def add_training_op(self, loss):
        opt = tf.train.AdamOptimizer(learning_rate = self.config.lr)
        train_op = opt.minimize(loss)
        return train_op

    ## TODO: Add def evaluate(test_set)
    def evaluate(self, pred):
        diff = self.labelsPH - pred
        prod = tf.matmul(diff, diff, transpose_a=True)
        se = tf.reduce_sum(prod)
        return se

    def evaluate_on_batch(self, sess, inputs_batch, labels_batch, mask_batch):
        feed = self.create_feed_dict(inputs_batch = inputs_batch,
                                     mask_batch = mask_batch,
                                     labels_batch=labels_batch,
                                     dropout=self.config.drop_out,
                                     l2_reg=self.config.l2Reg)
        se = sess.run(self.eval, feed_dict=feed)
        return se

    ### NO NEED TO UPDATE BELOW 
    def train_on_batch(self, sess, inputs_batch, labels_batch, mask_batch):
        feed = self.create_feed_dict(inputs_batch = inputs_batch,
                                     mask_batch = mask_batch,
                                     labels_batch=labels_batch,
                                     dropout=self.config.drop_out,
                                     l2_reg=self.config.l2Reg)
        _, loss = sess.run([self.train_op, self.loss], feed_dict=feed)
        return loss

    def run_epoch(self, sess):
        train_se = 0.0
        prog = Progbar(target=1 + self.train_x.shape[0] / self.config.batch_size)
        for i, (train_x, train_y, mask) in enumerate(minibatches(self.train_x, self.train_y, self.train_mask, self.config.batch_size)):
            loss = self.train_on_batch(sess, train_x, train_y, mask)
            train_se += self.evaluate_on_batch(sess, train_x, train_y, mask)
            prog.update(i + 1, [("train loss", loss)])

        train_obs = self.train_x.shape[0]
        train_mse = train_se / train_obs

        print 'Training MSE is {0}'.format(train_mse)

        print "Evaluating on dev set",
        dev_se = 0.0
        for i, (dev_x, dev_y, dev_mask) in enumerate(minibatches(self.dev_x, self.dev_y, self.dev_mask, self.config.batch_size)):
            dev_se += self.evaluate_on_batch(sess, dev_x, dev_y, dev_mask)

        dev_obs = self.dev_x.shape[0]
        dev_mse = dev_se / dev_obs

        print "- dev MSE: {:.2f}".format(dev_mse)
        return dev_mse

    # def run_epoch(self, sess, parser, train_examples, dev_set):
    #     prog = Progbar(target=1 + len(train_examples) / self.config.batch_size)
    #     for i, (train_x, train_y) in enumerate(minibatches(train_examples, self.config.batch_size)):
    #         loss = self.train_on_batch(sess, train_x, train_y)
    #         prog.update(i + 1, [("train loss", loss)])
    #
    #     print "Evaluating on dev set",
    #     dev_UAS, _ = parser.parse(dev_set)
    #     print "- dev UAS: {:.2f}".format(dev_UAS * 100.0)
    #     return dev_UAS

    def fit(self, sess, saver):
        best_dev_mse = np.inf
        for epoch in range(self.config.epochs):
            print "Epoch {:} out of {:}".format(epoch + 1, self.config.epochs)
            dev_mse = self.run_epoch(sess)
            if dev_mse < best_dev_mse:
                best_dev_mse = dev_mse
                if saver:
                    print "New best dev MSE! Saving model in ./encoder.weights"
                    # saver.save(sess, './encoder.weights', write_meta_graph = False)
                    saver.save(sess, './encoder.weights')
            print

    ## add def eval here

    def __init__(self, config, embedding_path, train_path, dev_path):
        train_x_pad, train_y, train_mask, dev_x_pad, dev_y, dev_mask, embeddingDictPad = self._read_data(
            train_path, dev_path, embedding_path)
        self.train_x = train_x_pad
        self.train_y = train_y
        self.train_mask = train_mask
        self.dev_x = dev_x_pad
        self.dev_y = dev_y
        self.dev_mask = dev_mask
        self.pretrained_embeddings = embeddingDictPad
        # Update our config with data parameters
        self.config = config
        self.config.max_sentence = max(train_x_pad.shape[1], dev_x_pad.shape[1])
        # self.config.max_sentence = train_x_pad.shape[1]
        self.config.n_class = train_y.shape[1]
        self.config.embedding_size = embeddingDictPad.shape[1]
        self.build()

'''
Evaluate model
'''
# def do_evaluate(model):
#     config = model.config
#     dev_x = model.dev_x
#     dev_y = model.dev_y
#     embedding = model.pretrained_embeddings
#
#     with tf.Graph().as_default():
#         start = time.time()



''' 
Creates Batch Data
'''
#
# def data_iterator(data, labels, batch_size, sentLen):
#     """ A simple data iterator """
#     numObs = data.shape[0]
#     while True:
#         # shuffle labels and features
#         idxs = np.arange(0, numObs)
#         np.random.shuffle(idxs)
#         shuffledData = data[idxs]
#         shuffledLabels = labels[idxs]
#         shuffledSentLen = sentLen[idxs]
#         for idx in range(0, numObs, batch_size):
#             dataBatch = shuffledData[idx:idx + batch_size]
#             labelsBatch = shuffledLabels[idx:idx + batch_size]
#             seqLenBatch = shuffledSentLen[idx:idx + batch_size]
#             yield dataBatch, labelsBatch, seqLenBatch
            

'''
Read in Data
'''

train = '/Users/henryneeb/CS224N-Project/source/rcnn-master/beer/reviews.aspect1.small.train.txt.gz'
dev = '/Users/henryneeb/CS224N-Project/source/rcnn-master/beer/reviews.aspect1.small.heldout.txt.gz'
embedding = '/Users/henryneeb/CS224N-Project/source/rcnn-master/beer/review+wiki.filtered.200.txt.gz'

# train_x_pad, train_y, train_mask, dev_x_pad, dev_y, dev_mask,embeddingDictPad = readOurData(train, dev, embedding)


# model = RNNModel(Config(), embedding, train, dev)

# exit()

'''
Get Embeddings
'''
# embeddings = tf.constant(embeddingDictPad, dtype = tf.float32)
# embedInput = tf.nn.embedding_lookup(embeddings, inputPH)
# embedInput = tf.reshape(embedInput,
#                         shape = (batch_size, max_sentence, embedding_size))
# revEmbedInput = tf.reverse(embedInput, dims = [False, True, False])
# embedInput = tf.unstack(embedInput, axis = 1)
# revEmbedInput = embedInput[::-1]

'''
Batch our Data
'''
# iter = data_iterator(train_x_pad, train_y, batch_size, sentLen)


##################
# GENERATOR STEP #
##################

'''
TODO: Fill this in. 
'''
# output2Rev = tf.reverse(output2, axis = 1)
# hFinal = tf.concat(concat_dim = 0, values = [output1, output2Rev])


def main(debug=False):
    print 80 * "="
    print "INITIALIZING"
    print 80 * "="
    config = Config()
    ## this is where we add our own data 
    # parser, embeddings, train_examples, dev_set, test_set = load_and_preprocess_data(debug)
    # if not os.path.exists('./data/weights/'):
    #     os.makedirs('./data/weights/')

    with tf.Graph().as_default():
        print "Building model...",
        start = time.time()
        ## this is where we add our model class name 
        ## config is also a class name
        model = RNNModel(config, embedding, train, dev)
        # rnn.model = model
        print "took {:.2f} seconds\n".format(time.time() - start)

        init = tf.global_variables_initializer()
        # If you are using an old version of TensorFlow, you may have to use
        # this initializer instead.
        # init = tf.initialize_all_variables()
        saver = tf.train.Saver()

        with tf.Session() as session:
            session.run(init)

            print 80 * "="
            print "TRAINING"
            print 80 * "="
            ## this is a function is the model class
            # model.run_epoch(session)
            model.fit(session, saver)
            # model.train_on_batch(session, model.train_x[0:32,:], model.train_y[0:32,:], model.train_mask[0:32,:])
            # train_on_batch(self, sess, inputs_batch, labels_batch, mask_batch)
            # model.fit(session, None)
            # model.fit(session, saver)
            #
            # # train_on_batch(self, sess, inputs_batch, labels_batch, mask_batch)
            # # model.fit(session, saver, parser, train_examples, dev_set)
            #
            # if not debug:
            #     print 80 * "="
            #     print "TESTING"
            #     print 80 * "="
            #     print "Restoring the best model weights found on the dev set"
            #     saver.restore(session, './parser.weights')
            #     print "Final evaluation on test set",
            #     ## we won't have this. we need function in our model that will evaluate on test set
            #     ## this is a function that will only calculate loss, "Evaluate function" takes inputs and compares to labels
            #     ## ie model.evaluate(test_set)
            #     loss = model.evaluate(test_set)
            #     print "- test UAS: {:.2f}".format(UAS * 100.0)
            #     print "Writing predictions"
            #     with open('q2_test.predicted.pkl', 'w') as f:
            #         cPickle.dump(dependencies, f, -1)
            #     print "Done!"

if __name__ == '__main__':
    main()

