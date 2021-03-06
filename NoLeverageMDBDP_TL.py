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
num_epochExtNoLast = 10
num_epochExtLast = 200
initialLearningRateLast = 1e-2
initialLearningRateNoLast = 1e-3
nbOuterLearning = 10
nTest = 10
#ckpt_bsde = 'saved_parameters/FNL_MDBDP_10/BoundedFNLMDBDPd10nbNeur20nbHL2ndt12030Alpha100BSDE_1'
#ckpt_gam = 'saved_parameters/FNL_MDBDP_10/BoundedFNLMDBDPd10nbNeur20nbHL2ndt12030Alpha100Gam_1'
#ckpt_bsde = 'saved_parameters/FNL_MDBDP_5/BoundedFNLMDBDPd5nbNeur15nbHL2ndt12030Alpha100BSDE_1'
#ckpt_gam = 'saved_parameters/FNL_MDBDP_5/BoundedFNLMDBDPd5nbNeur15nbHL2ndt12030Alpha100Gam_1'

#ckpt_bsde = 'saved_parameters/FNL_PWG_10/BoundedFNLPWGd10nbNeur20nbHL2ndt120Alpha100BSDE_1'
#ckpt_bsde = 'saved_parameters/FNL_EMDBDP_10/BoundedFNLEMDBDPd10nbNeur20nbHL2ndt120Alpha100BSDE_1'
#ckpt_gam = 'saved_parameters/FNL_PWG_10/BoundedFNLMDBDPd10nbNeur20nbHL2ndt12030Alpha100Gam_1'

#ckpt_bsde = 'saved_parameters/OA_MDBDP_2/OneAssetMDBDPd2nbNeur12nbHL2ndt12030eta50BSDE_1'
#ckpt_gam = 'saved_parameters/OA_MDBDP_2/OneAssetMDBDPd2nbNeur12nbHL2ndt12030eta50Gam_1'
ckpt_bsde = 'saved_parameters/OA_PWG_2/OneAssetPWGd2nbNeur12nbHL2ndt120eta50BSDE_1'




#ckpt_bsde = 'saved_parameters/MA_MDBDP_10/MongeAmpereMDBDPd10nbNeur20nbHL2ndt12030BSDE_1'
#ckpt_gam = 'saved_parameters/MA_MDBDP_10/MongeAmpereMDBDPd10nbNeur20nbHL2ndt12030Gam_1'
#ckpt_bsde = 'saved_parameters/MA_MDBDP_5/MongeAmpereMDBDPd5nbNeur15nbHL2ndt12030BSDE_1'
#ckpt_gam = 'saved_parameters/MA_MDBDP_5/MongeAmpereMDBDPd5nbNeur15nbHL2ndt12030Gam_1'
weights_step = 1
n_layers_freeze = 2

#lamb = np.array([1.5, 1.1, 2., 0.8, 0.5, 1.7, 0.9, 1., 0.9], dtype=np.float32)[0:9]
lamb = np.array([1.5], dtype=np.float32)
eta = 0.5
#theta = np.array([0.1, 0.2, 0.3, 0.4, 0.25, 0.15, 0.18, 0.08, 0.91], dtype=np.float32)[0:9]
theta = np.array([0.4], dtype=np.float32)
#gamma = np.array([0.2, 0.15, 0.25, 0.31, 0.4, 0.35, 0.22, 0.4, 0.15], dtype=np.float32)[0:9]
gamma = np.array([0.2], dtype=np.float32)[0:1]
#kappa = np.array([1., 0.8, 1.1, 1.3, 0.95, 0.99, 1.02, 1.06, 1.6], dtype=np.float32)[0:9]
kappa = np.array([1.], dtype=np.float32)[0:1]
sigma = np.ones(9, dtype=np.float32)[0:9]
d = lamb.shape[0] + 1
nbNeuron = d + 10
sigScal = np.concatenate([np.array([1.], dtype=np.float32), gamma]).reshape((d))

muScal = np.concatenate([np.array([np.sum(theta * lamb)]), np.zeros((d - 1), dtype=np.float32)]).reshape((d))
layerSize = nbNeuron * np.ones((nbLayer,), dtype=np.int32)

xyInit = np.concatenate([np.array([1.]), theta])

# create the model
model = mod.ModelNoLeverage(xyInit, muScal, sigScal, T, theta, sigma, lamb, eta, gamma, kappa)

print(" WILL USE " + str(_MULTIPROCESSING_CORE_COUNT) + " THREADS ")
print("REAL IS ", model.Sol(0., xyInit.reshape(1, d)), " DERIV", model.derSol(0., xyInit.reshape(1, d)), " GAMMA",
      model.der2Sol(0., xyInit.reshape(1, d)))

theNetwork = net.FeedForwardUZ(d,layerSize,tf.nn.tanh,
                                 num_layers_to_load_and_freeze=n_layers_freeze,
                                 path_saved_checkpoint=ckpt_bsde, weights_step=weights_step)
#theNetworkGam = net.FeedForwardGam(d,layerSize,tf.nn.tanh,
#                                num_layers_to_load_and_freeze=n_layers_freeze,
#                                path_saved_checkpoint=ckpt_gam, weights_step=weights_step)
theNetworkGam = net.FeedForwardGam(d,layerSize,tf.nn.tanh)

ndt = [(30, 10)]

print("PDE No Leverage MDBDP  Dim ", d, " layerSize ", layerSize, " rescal ", rescal, "T ", T, "batchsize ", batchSize,
      " batchSizeVal ", batchSizeVal, "num_epoch ", num_epoch, " num_epochExtNoLast ", num_epochExtNoLast,
      "num_epochExtLast ", num_epochExtLast, "VOL ", sigScal, "initialLearningRateLast", initialLearningRateLast,
      "initialLearningRateNoLast ", initialLearningRateNoLast)

# nest on ndt
for indt in ndt:

    print("NBSTEP", indt)
    # create graph
    resol = solv.PDEFNLSolve2OptZGPU(model, T, indt[0], indt[1], theNetwork, theNetworkGam,
                                     initialLearningRateLast=initialLearningRateLast,
                                     initialLearningRateNoLast=initialLearningRateNoLast)

    baseFile = "NoLeverageMDBDPd" + str(d) + "nbNeur" + str(layerSize[0]) + "nbHL" + str(len(layerSize)) + "ndt" + str(
        indt[0]) + str(indt[1]) + "eta" + str(int(eta * 100))
    plotFile = "pictures/" + baseFile
    saveFolder = "save/"

    Y0List = []
    for i in range(nTest):
        # train
        t0 = time.time()
        Y0, Z0, Gamma0 = resol.BuildAndtrainML(batchSize, batchSizeVal, num_epochExtNoLast=num_epochExtNoLast,
                                               num_epochExtLast=num_epochExtLast, num_epoch=num_epoch,
                                               nbOuterLearning=nbOuterLearning, thePlot=plotFile, baseFile=baseFile,
                                               saveDir=saveFolder)
        t1 = time.time()
        print(" NBSTEP", indt, " EstimMC Val is ", Y0, " REAL IS ", model.Sol(0., xyInit.reshape(1, d)), " Z0 ", Z0,
              " DERREAL IS  ", model.derSol(0., xyInit.reshape(1, d)), "Gamma0 ", Gamma0, " GAMMA",
              model.der2Sol(0., xyInit.reshape(1, d)), t1 - t0)

        Y0List.append(Y0)
        print(Y0List)

    print("Y0", Y0List)
    yList = np.array(Y0List)
    yMean = np.mean(yList)
    print(" DNT ", indt, "MeanVal ", yMean, " Etyp ", np.sqrt(np.mean(np.power(yList - yMean, 2.))))
