#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013, Colin O'Flynn <coflynn@newae.com>
# All rights reserved.
#
# Find this and more at newae.com - this file is part of the chipwhisperer
# project, http://www.assembla.com/spaces/chipwhisperer
#
#    This file is part of chipwhisperer.
#
#    chipwhisperer is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    chipwhisperer is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with chipwhisperer.  If not, see <http://www.gnu.org/licenses/>.
#=================================================


import sys
from datetime import datetime

try:
    from PySide.QtCore import *
    from PySide.QtGui import *
except ImportError:
    print "ERROR: PySide is required for this program"
    sys.exit()
    
from subprocess import Popen, PIPE
sys.path.append('../common')
sys.path.append('../../openadc/controlsw/python/common')
sys.path.append('../common/traces')

import numpy as np
import scipy as sp
from ExtendedParameter import ExtendedParameter

#from joblib import Parallel, delayed

try:
    from pyqtgraph.parametertree import Parameter
    #print pg.systemInfo()    
except ImportError:
    print "ERROR: PyQtGraph is required for this program"
    sys.exit()

import attacks.models.AES128_8bit
import attacks.models.AES_RoundKeys
from attacks.AttackBaseClass import AttackBaseClass
from attacks.AttackProgressDialog import AttackProgressDialog

from attacks.CPAProgressive import CPAProgressive
from attacks.CPASimpleLoop import CPASimpleLoop

from AttackGenericParameters import AttackGenericParameters

class CPA(AttackBaseClass, AttackGenericParameters):
    """Correlation Power Analysis Attack"""
            
    def __init__(self, parent=None, console=None):
        super(CPA, self).__init__(parent)
        self.console=console
        
    def debug(self, sr):
        if self.console is not None:
            self.console.append(sr)
        
    def setupParameters(self):      
        cpaalgos = {'Progressive':CPAProgressive, 'Simple':CPASimpleLoop}
        
        #if CPACython is not None:
        #    cpaalgos['Progressive-Cython'] = CPACython.AttackCPA_Progressive
        
        attackParams = [{'name':'CPA Algorithm', 'key':'CPA_algo', 'type':'list', 'values':cpaalgos, 'value':CPAProgressive, 'set':self.setAlgo},                   
                        {'name':'Hardware Model', 'type':'group', 'children':[
                        {'name':'Crypto Algorithm', 'key':'hw_algo', 'type':'list', 'values':{'AES-128 (8-bit)':attacks.models.AES128_8bit}, 'value':'AES-128'},
                        {'name':'Key Round', 'key':'hw_round', 'type':'list', 'values':['first', 'last'], 'value':'first'},
                        {'name':'Power Model', 'key':'hw_pwrmodel', 'type':'list', 'values':['Hamming Weight', 'Hamming Distance', 'Hamming Weight (inverse)'], 'value':'Hamming Weight'},
                        ]},
                       {'name':'Take Absolute', 'type':'bool', 'value':True},
                       
                       #TODO: Should be called from the AES module to figure out # of bytes
                       {'name':'Attacked Bytes', 'type':'group', 'children':
                         self.getByteList()                                                 
                        },                    
                      ]
        self.params = Parameter.create(name='Attack', type='group', children=attackParams)
        #Need 'showScriptParameter = None' for setupExtended call below
        self.showScriptParameter = None
        ExtendedParameter.setupExtended(self.params, self)
        
        self.setAlgo(self.findParam('CPA_algo').value())
            
    def setAlgo(self, algo):
        self.attack = algo(self.findParam('hw_algo').value())
        try:
            self.attackParams = self.attack.paramList()[0]
        except:
            self.attackParams = None

        self.paramListUpdated.emit(self.paramList())
                                                
    def processKnownKey(self, inpkey):
        if inpkey is None:
            return None
        
        if self.findParam('hw_round').value() == 'last':
            return attacks.models.AES_RoundKeys.AES_RoundKeys().getFinalKey(inpkey)
        else:
            return inpkey
            
    def doAttack(self):        
        
        start = datetime.now()
        
        #TODO: support start/end point different per byte
        (startingPoint, endingPoint) = self.getPointRange(None)
        
        self.attack.getStatistics().clear()
        
        for itNum in range(1, self.getIterations()+1):
            startingTrace = self.getTraceNum()*(itNum-1) + self.getTraceStart()
            endingTrace = self.getTraceNum()*itNum + self.getTraceStart()
            
            #print "%d-%d"%(startingPoint, endingPoint)            
            data = []
            textins = []
            textouts = []
            
            for i in range(startingTrace, endingTrace):
                d = self.trace.getTrace(i)
                
                if d is None:
                    continue
                
                d = d[startingPoint:endingPoint]
                
                data.append(d)
                textins.append(self.trace.getTextin(i))
                textouts.append(self.trace.getTextout(i)) 
            
            self.attack.setByteList(self.bytesEnabled())
            self.attack.setKeyround(self.findParam('hw_round').value())
            self.attack.setModeltype(self.findParam('hw_pwrmodel').value())
            self.attack.setStatsReadyCallback(self.statsReady)
            
            progress = AttackProgressDialog()
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(1000)
            progress.offset = startingTrace
            
            #TODO:  pointRange=self.TraceRangeList[1:17]
            try:
                self.attack.addTraces(data, textins, textouts, progress)
            except KeyboardInterrupt:
                self.debug("Attack ABORTED... stopping")
        
        end = datetime.now()
        self.debug("Attack Time: %s"%str(end-start)) 
        self.attackDone.emit()
        
        
    def statsReady(self):
        self.statsUpdated.emit()
        QApplication.processEvents()

    def passTrace(self, powertrace, plaintext=None, ciphertext=None, knownkey=None):
        pass
    
    def getStatistics(self):
        return self.attack.getStatistics()
            
    def paramList(self):
        l = [self.params, self.pointsParams, self.traceParams]
        if self.attackParams is not None:
            l.append(self.attackParams)
        return l