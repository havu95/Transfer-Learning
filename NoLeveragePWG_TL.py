import numpy as np
import tensorflow as tf
import os
import solvers  as solv
import networks as net
import models as mod
import multiprocessing
import sys
import time

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

_MULTIPROCESSING_CORE_COUNT = multiprocessing.cpu_count()
print("args", sys.argv)
nbLayer = 2
print("nbLayer ", nbLayer)
rescal = 1.
T = 1.

batchSize = 1000
batchSizeVal = 10000
num_epoch = 400
num_epochExtNoLast = 200
num_epochExtLast = 100
initialLearningRateLast = 1e-2
initialLearningRateNoLast = 1e-3
nbOuterLearning = 10
nTest = 1
#ckpt_bsde = 'saved_parameters/FNL_PWG_10/BoundedFNLPWGd10nbNeur20nbHL2ndt120Alpha100BSDE_1'
ckpt_bsde = 'saved_parameters/FNL_PWG_5/BoundedFNLPWGd5nbNeur15nbHL2ndt120Alpha100BSDE_1'
#ckpt_bsde = 'saved_parameters/MA_PWG_10/MongeAmperePWGd10nbNeur20nbHL2ndt120quantile1.0BSDE_1'
# ckpt_bsde = 'saved_parameters/MA_PWG_5/MongeAmperePWGd5nbNeur15nbHL2ndt120quantile1.0BSDE_1'
weights_step = 1
n_layers_freeze = 2

lamb = np.array([1.5, 1.1, 2., 0.8, 0.5, 1.7, 0.9, 1., 0.9, 1.5], dtype=np.float32)[0:4]
eta = 0.5
theta = np.array([0.1, 0.2, 0.3, 0.4, 0.25, 0.15, 0.18, 0.08, 0.91, 0.4], dtype=np.float32)[0:4]
gamma = np.array([0.2, 0.15, 0.25, 0.31, 0.4, 0.35, 0.22, 0.4, 0.15, 0.2], dtype=np.float32)[0:4]
kappa = np.array([1., 0.8, 1.1, 1.3, 0.95, 0.99, 1.02, 1.06, 1.6, 1.], dtype=np.float32)[0:4]
sigma = np.ones(10, dtype=np.float32)[0:4]
d = lamb.shape[0] + 1

nbNeuron = d + 10
layerSize = nbNeuron * np.ones((nbLayer,), dtype=np.int32)

sigScal = np.concatenate([np.array([1.], dtype=np.float32), gamma]).reshape((d))
muScal = np.concatenate([np.array([np.sum(theta * lamb)]), np.zeros((d - 1), dtype=np.float32)]).reshape((d))
xyInit = np.concatenate([np.array([1.]), theta])

quant = 0.95

# create the model
model = mod.ModelNoLeverage(xyInit, muScal, sigScal, T, theta, sigma, lamb, eta, gamma, kappa)

print(" WILL USE " + str(_MULTIPROCESSING_CORE_COUNT) + " THREADS ")
print("REAL IS ", model.Sol(0., xyInit.reshape(1, d)), " DERIV", model.derSol(0., xyInit.reshape(1, d)), " GAMMA",
      model.der2Sol(0., xyInit.reshape(1, d)))

theNetwork = net.FeedForwardUZ(d,layerSize,tf.nn.tanh,
                                 num_layers_to_load_and_freeze=n_layers_freeze,
                                 path_saved_checkpoint=ckpt_bsde, weights_step=weights_step)

ndt = [30]

print("PDE No Leverage PWG  Full NL  Dim ", d, " layerSize ", layerSize, " rescal ", rescal, "T ", T, "batchsize ",
      batchSize, " batchSizeVal ", batchSizeVal, "num_epoch ", num_epoch, " num_epochExtNoLast ", num_epochExtNoLast,
      "num_epochExtLast ", num_epochExtLast, "VOL ", sigScal, "initialLearningRateLast", initialLearningRateLast,
      "initialLearningRateNoLast ", initialLearningRateNoLast, "quantile", quant)

# nest on ndt
for indt in ndt:

    print("NBSTEP", indt)
    # create graph
    resol = solv.PDEFullNLExplicitGamAdapt(xyInit, model, T, indt, theNetwork,
                                           initialLearningRate=initialLearningRateLast,
                                           initialLearningRateStep=initialLearningRateNoLast)

    baseFile = "NoLeveragePWGd" + str(d) + "nbNeur" + str(layerSize[0]) + "nbHL" + str(len(layerSize)) + "ndt" + str(
        indt) + "eta" + str(int(eta * 100))
    plotFile = "pictures/" + baseFile
    saveFolder = "save/"

    Y0List = []
    for i in range(nTest):
        # train
        t0 = time.time()
        Y0, Z0 = resol.BuildAndtrainML(batchSize, batchSizeVal, num_epochExt=num_epochExtNoLast, num_epoch=num_epoch,
                                       nbOuterLearning=nbOuterLearning, thePlot=plotFile, baseFile=baseFile,
                                       saveDir=saveFolder, quantile=quant)
        t1 = time.time()
        print(" NBSTEP", indt, " EstimMC Val is ", Y0, " REAL IS ", model.Sol(0., xyInit.reshape((1, d))), " Z0 ", Z0,
              " DERREAL IS  ", model.derSol(0., xyInit.reshape((1, d))), t1 - t0)

        Y0List.append(Y0)
        print(Y0List)

    print("Y0", Y0List)
    yList = np.array(Y0List)
    yMean = np.mean(yList)
    print(" DNT ", indt, "MeanVal ", yMean, " Etyp ", np.sqrt(np.mean(np.power(yList - yMean, 2.))))
