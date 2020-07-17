import math
import os

import numpy as np
import scipy as sp
from scipy.optimize import minimize

import scqubits.core.descriptors as descriptors
from scqubits.core.vchos import VCHOS


# Current Mirror using VCHOS. Truncation scheme used is defining a cutoff num_exc
# of the number of excitations kept for each mode. The dimension of the hilbert space
# is then m*(num_exc+1)**(2*N - 1), where m is the number of inequivalent minima in 
# the first unit cell and N is the number of big capacitors.

class CurrentMirrorVCHOS(VCHOS):
    N = descriptors.WatchedProperty('QUANTUMSYSTEM_UPDATE')
    ECB = descriptors.WatchedProperty('QUANTUMSYSTEM_UPDATE')
    ECJ = descriptors.WatchedProperty('QUANTUMSYSTEM_UPDATE')
    ECg = descriptors.WatchedProperty('QUANTUMSYSTEM_UPDATE')
    EJlist = descriptors.WatchedProperty('QUANTUMSYSTEM_UPDATE')
    nglist = descriptors.WatchedProperty('QUANTUMSYSTEM_UPDATE')
    flux = descriptors.WatchedProperty('QUANTUMSYSTEM_UPDATE')

    def __init__(self, N, ECB, ECJ, ECg, EJlist, nglist, flux, kmax, num_exc, truncated_dim=None):
        VCHOS.__init__(self, EJlist, nglist, flux, kmax, num_exc)
        self.N = N
        self.ECB = ECB
        self.ECJ = ECJ
        self.ECg = ECg
        V_m = self._build_V_m()
        self.nglist = np.dot(sp.linalg.inv(V_m).T, nglist)[0:-1]
        self.boundary_coeffs = np.ones(2 * N - 1)
        self.truncated_dim = truncated_dim
        self._sys_type = type(self).__name__
        self._evec_dtype = np.complex_
        self._image_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                            'qubit_pngs/currentmirrorvchos.png')

    @staticmethod
    def default_params():
        return {
            'N': 3,
            'ECB': 0.2,
            'ECJ': 20.0 / 2.7,
            'ECg': 20.0,
            'EJlist': np.array(5 * [18.95]),
            'nglist': np.array(5 * [0.0]),
            'flux': 0.0,
            'kmax': 1,
            'num_exc': 2,
            'squeezing': False,
            'truncated_dim': 6
        }

    @staticmethod
    def nonfit_params():
        return ['N', 'nglist', 'flux', 'kmax', 'num_exc', 'truncated_dim']
    
    def build_Cmat_full(self):
        N = self.N
        CB = self.e ** 2 / (2. * self.ECB)
        CJ = self.e ** 2 / (2. * self.ECJ)
        Cg = self.e ** 2 / (2. * self.ECg)

        Cmat = np.diagflat([Cg + 2 * CJ + CB for _ in range(2 * N)], 0)
        Cmat += np.diagflat([- CJ for _ in range(2 * N - 1)], +1)
        Cmat += np.diagflat([- CJ for _ in range(2 * N - 1)], -1)
        Cmat += np.diagflat([- CB for _ in range(N)], +N)
        Cmat += np.diagflat([- CB for _ in range(N)], -N)
        Cmat[0, -1] = Cmat[-1, 0] = - CJ
        
        return Cmat

    def build_capacitance_matrix(self):
        Cmat = self.build_Cmat_full()

        V_m_inv = sp.linalg.inv(self._build_V_m())
        Cmat = np.matmul(V_m_inv.T, np.matmul(Cmat, V_m_inv))

        return Cmat[0:-1, 0:-1]

    def _build_V_m(self):
        N = self.N
        V_m = np.diagflat([-1 for _ in range(2 * N)], 0)
        V_m += np.diagflat([1 for _ in range(2 * N - 1)], 1)
        V_m[-1] = np.array([1 for _ in range(2 * N)])

        return V_m

    def build_EC_matrix(self):
        """Return the charging energy matrix"""
        Cmat = self.build_capacitance_matrix()
        return 0.5 * self.e ** 2 * sp.linalg.inv(Cmat)

    def number_degrees_freedom(self):
        return 2 * self.N - 1

    def find_minima(self):
        """
        Index all minima
        """
        minima_holder = []
        N = self.N
        for m in range(int(math.ceil(N / 2 - np.abs(self.flux))) + 1):
            guess_pos = np.array([np.pi * (m + self.flux) / N for _ in range(self.number_degrees_freedom())])
            guess_neg = np.array([np.pi * (-m + self.flux) / N for _ in range(self.number_degrees_freedom())])
            result_pos = minimize(self.potential, guess_pos)
            result_neg = minimize(self.potential, guess_neg)
            new_minimum_pos = self._check_if_new_minima(result_pos.x, minima_holder)
            if new_minimum_pos and result_pos.success:
                minima_holder.append(np.array([np.mod(elem, 2 * np.pi) for elem in result_pos.x]))
            new_minimum_neg = self._check_if_new_minima(result_neg.x, minima_holder)
            if new_minimum_neg and result_neg.success:
                minima_holder.append(np.array([np.mod(elem, 2 * np.pi) for elem in result_neg.x]))
        return minima_holder

    def sorted_minima(self):
        """Sort the minima based on the value of the potential at the minima """
        minima_holder = self.find_minima()
        value_of_potential = np.array([self.potential(minima_holder[x])
                                       for x in range(len(minima_holder))])
        sorted_value_holder = np.array([x for x, _ in
                                        sorted(zip(value_of_potential, minima_holder), key=lambda x: x[0])])
        sorted_minima_holder = np.array([x for _, x in
                                         sorted(zip(value_of_potential, minima_holder), key=lambda x: x[0])])
        # For efficiency purposes, don't want to displace states into minima
        # that are too high energy. Arbitrarily set a 40 GHz cutoff
        global_min = sorted_value_holder[0]
        dim = len(sorted_minima_holder)
        sorted_minima_holder = np.array([sorted_minima_holder[i] for i in range(dim)
                                         if sorted_value_holder[i] < global_min + 40.0])
        return sorted_minima_holder
