import numpy as np
import tensorflow as tf
import sys, traceback
import math
import os
from tensorflow.contrib.slim import fully_connected as fc
import time
from tensorflow.python.tools import inspect_checkpoint as chkp
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pylab as P
from mpl_toolkits.mplot3d import axes3d, Axes3D
from solvers.FullNonLinearBaseGPU import PDEFNLSolveBaseGPU


class PDEFNLSolve2OptGPU(PDEFNLSolveBaseGPU):

    def sizeNRG(self, iGam):
        return self.nbStepGam - iGam

    # calculate Gamma by conditionnel  expectation, Havu: added sess as input
    def buildGamStep(self, iStep, ListWeightUZ, ListBiasUZ, ListWeightGam, ListBiasGam, sess):
        is_trained_from_zero = True

        dic = {}
        dic["LRate"] = tf.compat.v1.placeholder(tf.float32, shape=[], name="learning_rate")
        dic["XPrev"] = tf.compat.v1.placeholder(dtype=tf.float32, shape=[None, self.d], name='XPrev')
        dic["RandG"] = tf.compat.v1.placeholder(dtype=tf.float32, shape=[None, self.d, self.nbStepGam - iStep],
                                                name='randG')
        sample_size = tf.shape(dic["XPrev"])[0]
        sig = self.model.sigScal
        mu = self.model.muScal
        rescale = sig * np.sqrt(self.TStepGam * iStep)
        normX0 = (dic["XPrev"] - self.xInit - mu * self.TStepGam * iStep) / rescale
        if (iStep < self.nbStepGam):
            dic["Gam"] = self.networkGam.createNetworkWithInitializer(normX0, iStep, ListWeightGam[-1], ListBiasGam[-1],
                                                                      rescale)
            is_trained_from_zero = True
        else:
            dic["Gam"] = self.networkGam.createNetwork(normX0, iStep, rescale)

        sqrtDt = np.sqrt(self.TStepGam)
        XNext = dic["XPrev"]
        XNextAnti = dic["XPrev"]
        GamTraj = tf.zeros([sample_size, self.d, self.d])
        WAccul = tf.zeros([sample_size, self.d])
        TAccul = 0.
        for i in range(len(ListWeightGam) - 1):
            iStepLoc = iStep + i + 1
            tLoc = (iStep + i + 1) * self.TStepGam
            WAccul = WAccul + sqrtDt * dic["RandG"][:, :, i]
            TAccul = TAccul + self.TStepGam
            XNext = XNext + mu * self.TStepGam + sig * sqrtDt * dic["RandG"][:, :, i]
            XNextAnti = XNextAnti + mu * self.TStepGam - sig * sqrtDt * dic["RandG"][:, :, i]
            iPosBSDE = (-i - 1) * self.nbStepGamStab
            normX = (XNext - self.xInit - mu * self.TStepGam * iStepLoc) / (sig * np.sqrt(self.TStepGam * iStepLoc))
            U, Z = self.networkUZ.createNetworkNotTrainable(normX, iStepLoc, ListWeightUZ[iPosBSDE],
                                                            ListBiasUZ[iPosBSDE])
            Gam = self.networkGam.createNetworkNotTrainable(normX, iStepLoc, ListWeightGam[-i - 1], ListBiasGam[-i - 1])
            driver = self.TStepGam * (0.5 * tf.einsum('j,ij->i', tf.constant(sig * sig, dtype=tf.float32),
                                                      tf.matrix_diag_part(Gam)) - self.model.fDW(
                                       iStepLoc * self.TStepGam, XNext, U, Z, Gam))

            normXAnti = (XNextAnti - self.xInit - mu * self.TStepGam * iStepLoc) / (
                        sig * np.sqrt(self.TStepGam * iStepLoc))
            UAnti, ZAnti = self.networkUZ.createNetworkNotTrainable(normXAnti, self.nbStepUDU + iStepLoc,
                                                                    ListWeightUZ[iPosBSDE], ListBiasUZ[iPosBSDE])
            GamAnti = self.networkGam.createNetworkNotTrainable(normXAnti, self.nbStepUDU + iStepLoc,
                                                                ListWeightGam[-i - 1], ListBiasGam[-i - 1])
            driverAnti = self.TStepGam * (0.5 * tf.einsum('j,ij->i', tf.constant(sig * sig, dtype=tf.float32),
                                                          tf.matrix_diag_part(GamAnti)) - self.model.fDW(
                iStepLoc * self.TStepGam, XNextAnti, UAnti, ZAnti, GamAnti))

            normXPrev = (dic["XPrev"] - self.xInit - mu * self.TStepGam * iStepLoc) / (
                        sig * np.sqrt(self.TStepGam * iStepLoc))
            UPrev, ZPrev = self.networkUZ.createNetworkNotTrainable(normXPrev, 2 * self.nbStepUDU + iStepLoc,
                                                                    ListWeightUZ[iPosBSDE], ListBiasUZ[iPosBSDE])
            GamPrev = self.networkGam.createNetworkNotTrainable(normXPrev, 2 * self.nbStepUDU + iStepLoc,
                                                                ListWeightGam[-i - 1], ListBiasGam[-i - 1])
            driverPrev = self.TStepGam * (0.5 * tf.einsum('j,ij->i', tf.constant(sig * sig, dtype=tf.float32),
                                                          tf.matrix_diag_part(GamPrev)) - self.model.fDW(
                iStepLoc * self.TStepGam, dic["XPrev"], UPrev, ZPrev, GamPrev))

            weight = (tf.einsum('lij,j->lij', tf.einsum('i,lij->lij', tf.constant(1 / sig, dtype=tf.float32),
                                                        tf.einsum("li,lj->lij", WAccul, WAccul) - TAccul),
                                tf.constant(1 / sig, dtype=tf.float32))) / (TAccul * TAccul)
            GamTraj = GamTraj - tf.einsum("l,lij->lij", 0.5 * (driver + driverAnti - 2 * driverPrev), weight)

        if (len(ListWeightGam) > 0):
            XNext = XNext + mu * self.TStepGam + sig * sqrtDt * dic["RandG"][:, :, len(ListWeightGam) - 1]
            XNextAnti = XNextAnti + mu * self.TStepGam - sig * sqrtDt * dic["RandG"][:, :, len(ListWeightGam) - 1]
        GamTraj = GamTraj + 0.5 * (self.model.D2gTf(XNext) + self.model.D2gTf(XNextAnti))

        dic["weightLoc"], dic["biasLoc"] = self.networkGam.getBackWeightAndBias(iStep)
        dic["Loss"] = tf.reduce_mean(tf.pow(dic["Gam"] - GamTraj, 2))

        # Havu: Freeze layers
        if is_trained_from_zero:
            self.networkUZ.freeze_layers(iStep)
            self.networkGam.freeze_layers(iStep)

        dic["train"] = tf.compat.v1.train.AdamOptimizer(learning_rate=dic["LRate"]).minimize(dic["Loss"])
        # Init weights
        sess.run(tf.compat.v1.global_variables_initializer())
        # Havu: pretrained parameters
        if is_trained_from_zero:
            self.networkUZ.preload_weights(iStep, sess)
            self.networkGam.preload_weights(iStep, sess)

        return dic

    # calculate Gamma by conditionnal expectation
    def buildGamStep0(self, ListWeightUZ, ListBiasUZ, ListWeightGam, ListBiasGam, Gam0_initializer, sess):
        dic = {}
        dic["LRate"] = tf.compat.v1.placeholder(tf.float32, shape=[], name="learning_rate")
        dic["RandG"] = tf.compat.v1.placeholder(dtype=tf.float32, shape=[None, self.d, self.nbStepGam], name='randG')
        dic["Gam0"] = tf.compat.v1.get_variable("Gam0", [self.d, self.d], tf.float32, Gam0_initializer)
        sample_size = tf.shape(dic["RandG"])[0]
        sig = self.model.sigScal
        mu = self.model.muScal
        sqrtDt = np.sqrt(self.TStepGam)
        XPrev = tf.tile(tf.expand_dims(tf.convert_to_tensor(self.xInit, dtype=tf.float32), axis=0), [sample_size, 1])
        XNext = XPrev
        XNextAnti = XNext
        GamTraj = tf.zeros([sample_size, self.d, self.d])
        WAccul = tf.zeros([sample_size, self.d])
        TAccul = 0.
        for i in range(len(ListWeightGam) - 1):
            iStepLoc = i + 1
            tLoc = (i + 1) * self.TStepGam
            WAccul = WAccul + sqrtDt * dic["RandG"][:, :, i]
            TAccul = TAccul + self.TStepGam
            XNext = XNext + mu * self.TStepGam + sig * sqrtDt * dic["RandG"][:, :, i]
            XNextAnti = XNextAnti + mu * self.TStepGam - sig * sqrtDt * dic["RandG"][:, :, i]
            iPosBSDE = (-i - 1) * self.nbStepGamStab
            print("len( ListWeightGam)", len(ListWeightGam), " ListWeightUZ ", len(ListWeightUZ), " IPO", iPosBSDE)
            normX = (XNext - self.xInit - mu * self.TStepGam * iStepLoc) / (sig * np.sqrt(self.TStepGam * iStepLoc))
            U, Z = self.networkUZ.createNetworkNotTrainable(normX, iStepLoc, ListWeightUZ[iPosBSDE],
                                                            ListBiasUZ[iPosBSDE])
            Gam = self.networkGam.createNetworkNotTrainable(normX, iStepLoc, ListWeightGam[-i - 1], ListBiasGam[-i - 1])
            einsum_arg2_0 = tf.matrix_diag_part(Gam)
            einsum_arg2_1 = self.model.fDW(iStepLoc * self.TStepGam, XNext, U, Z, Gam)
            einsum_arg2 = einsum_arg2_0 - einsum_arg2_1
            # Need to perform concatenation since einsum requires the summation
            # dimensions be of the same length
            if len(sig) < 2:
                # Concatenation is conditional since when training BoundedFNLM2DBDP sig has only 1 element
                # while when training OneAssetM2DBDP sig has 2 elements
                sig = np.concatenate([sig]*2, axis=0)
            driver = self.TStepGam * (0.5 * tf.einsum('j,ij->i', tf.constant(sig * sig, dtype=tf.float32),
                                                      einsum_arg2))
            print('sig', sig)
            normXAnti = (XNextAnti - self.xInit - mu * self.TStepGam * iStepLoc) / (
                        sig * np.sqrt(self.TStepGam * iStepLoc))
            UAnti, ZAnti = self.networkUZ.createNetworkNotTrainable(normXAnti, self.nbStepUDU + iStepLoc,
                                                                    ListWeightUZ[iPosBSDE], ListBiasUZ[iPosBSDE])
            GamAnti = self.networkGam.createNetworkNotTrainable(normXAnti, self.nbStepUDU + iStepLoc,
                                                                ListWeightGam[-i - 1], ListBiasGam[-i - 1])
            #print('sig', sig)
            #print('GamAnti', GamAnti)
            einsum_arg2_0 = tf.matrix_diag_part(GamAnti)
            einsum_arg2_1 = self.model.fDW(iStepLoc * self.TStepGam, XNextAnti, UAnti, ZAnti, GamAnti)
            einsum_arg2 =  einsum_arg2_0 -  einsum_arg2_1
            driverAnti = self.TStepGam * (0.5 * tf.einsum('j,ij->i', tf.constant(sig * sig, dtype=tf.float32),
                                                          einsum_arg2))

            normXPrev = (XPrev - self.xInit - mu * self.TStepGam * iStepLoc) / (sig * np.sqrt(self.TStepGam * iStepLoc))
            UPrev, ZPrev = self.networkUZ.createNetworkNotTrainable(normXPrev, 2 * self.nbStepUDU + iStepLoc,
                                                                    ListWeightUZ[iPosBSDE], ListBiasUZ[iPosBSDE])
            GamPrev = self.networkGam.createNetworkNotTrainable(normXPrev, 2 * self.nbStepUDU + iStepLoc,
                                                                ListWeightGam[-i - 1], ListBiasGam[-i - 1])
            einsum_arg2_0 = tf.matrix_diag_part(GamPrev)
            einsum_arg2_1 = self.model.fDW(
                iStepLoc * self.TStepGam, XPrev, UPrev, ZPrev, GamPrev)
            einsum_arg2 = einsum_arg2_0 - einsum_arg2_1
            driverPrev = self.TStepGam * (0.5 * tf.einsum('j,ij->i', tf.constant(sig * sig, dtype=tf.float32),
                                                          einsum_arg2))

            weight = (tf.einsum('lij,j->lij', tf.einsum('i,lij->lij', tf.constant(1 / sig, dtype=tf.float32),
                                                        tf.einsum("li,lj->lij", WAccul, WAccul) - TAccul),
                                tf.constant(1 / sig, dtype=tf.float32))) / (TAccul * TAccul)
            GamTraj = GamTraj - tf.einsum("l,lij->lij", 0.5 * (driver + driverAnti - 2 * driverPrev), weight)

        # Havu: Bugfix
        sig = sig[0]
        XNext = XNext + mu * self.TStepGam + sig * sqrtDt * dic["RandG"][:, :, len(ListWeightGam) - 1]
        XNextAnti = XNextAnti + mu * self.TStepGam - sig * sqrtDt * dic["RandG"][:, :, len(ListWeightGam) - 1]
        print(XNext)

        GamTraj = GamTraj + 0.5 * (self.model.D2gTf(XNext) + self.model.D2gTf(XNextAnti))

        dic["Loss"] = tf.reduce_mean(tf.pow(dic["Gam0"] - GamTraj, 2))
        dic["train"] = tf.compat.v1.train.AdamOptimizer(learning_rate=dic["LRate"]).minimize(dic["Loss"])
        # initialize variables
        sess.run(tf.compat.v1.global_variables_initializer())
        # Load weights if needed
        #from networks.global_vars import CKPT_PATH_BSDE_UZSTEP0, CKPT_PATH_BSDE_UZSTEP0_STEPVAL, \
        #    CKPT_PATH_GAM_UZSTEP0_STEPVAL, CKPT_PATH_GAM_UZSTEP0
        #if CKPT_PATH_BSDE_UZSTEP0 is not None:
        #    self.networkUZ.preload_weights(CKPT_PATH_BSDE_UZSTEP0_STEPVAL, sess, name_of_scope=f'NetWorkUZNonTrain_',
        #                                   weights_path=CKPT_PATH_BSDE_UZSTEP0)
        #if CKPT_PATH_GAM_UZSTEP0 is not None:
        #    self.networkGam.preload_weights(CKPT_PATH_GAM_UZSTEP0_STEPVAL, sess, name_of_scope=f'NetWorkGamNotTrain_',
        #                                    weights_path=CKPT_PATH_GAM_UZSTEP0)
        return dic
