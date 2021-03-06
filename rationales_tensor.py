
import gzip
import json
import numpy as np
import tensorflow as tf

def myio_read_rationales(path):
    data = [ ]
    fopen = gzip.open if path.endswith(".gz") else open
    with fopen(path) as fin:
        for line in fin:
            item = json.loads(line)
            data.append(item)
    return data

def read_rationales_as_array(path):
    # read in raw text
    rationale_data = myio_read_rationales(path)

    # find max data
    max_len = 0
    for i in xrange(0, len(rationale_data)):
        max_len = max(len(rationale_data[i]["x"]), max_len)

    rationale_array = np.zeros((len(rationale_data), max_len), dtype=np.int32)

    for i in xrange(0, len(rationale_data)):
        for j in xrange(0, len(rationale_data[i]["0"])):
            begin_idx = rationale_data[i]["0"][j][0]
            end_idx = rationale_data[i]["0"][j][1]
            words = rationale_data[i]["x"]
            rationale_array[i, begin_idx:end_idx] = 1

    return rationale_array


# read_rationales_as_array('/Users/henryneeb/CS224N-Project/source/rcnn-master/beer/annotations.json')
#
#
# rationale_data = myio_read_rationales('/Users/henryneeb/CS224N-Project/source/rcnn-master/beer/annotations.json')
#
# max_len = 0
# for i in xrange(0,len(rationale_data)):
#     max_len = max(len(rationale_data[i]["x"]), max_len)
#
# rationale_array = np.zeros((len(rationale_data), max_len), dtype = np.int32)
#
# for i in xrange(0,len(rationale_data)):
#     for j in xrange(0,len(rationale_data[i]["0"])):
#         begin_idx = rationale_data[i]["0"][j][0]
#         end_idx = rationale_data[i]["0"][j][1]
#         words = rationale_data[i]["x"]
#         rationale_array[i,begin_idx:end_idx] = 1
#
# rationale_tensor = tf.Variable(rationale_array, name="rationale_tensor")
