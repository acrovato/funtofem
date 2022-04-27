#!/usr/bin/env python

# This file is part of the package FUNtoFEM for coupled aeroelastic simulation
# and design optimization.

# Copyright (C) 2015 Georgia Tech Research Corporation.
# Additional copyright (C) 2015 Kevin Jacobson, Jan Kiviaho and Graeme Kennedy.
# All rights reserved.

# FUNtoFEM is licensed under the Apache License, Version 2.0 (the "License");
# you may not use this software except in compliance with the License.
# You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


class Variable(object):
    """
    Design variable type for FUNtoFEM
    """
    def __init__(self,name='unknown', value=0.0, lower=0.0, upper=1.0, scaling=1.0, active=True, coupled=False, id=0):
        """

        Parameters
        ----------
        name: str
            name of the variable
        value: float
            current value of the variable
        lower: float
            lower bound of the design variable
        upper: float
            upper bound of the design variable
        scaling: float
            scaling of the variable for an optimizer
        active: bool
            whether or not the design variable is active
        coupled: bool
            whether or not the design variable is coupled
        id: int
            id number of the design variable

        Examples
        --------
        thickness = Variable(name='thickness 0', value=0.004, lower=0.001, upper=0.1)
        """

        self.name       = name
        self.value      = value
        self.lower      = lower
        self.upper      = upper
        self.scaling    = scaling
        self.active     = active
        self.coupled    = coupled
        self.id         = id
        self.body       = None
        self.scenario   = None
        self.analysis_type = None

    def assign(self,value=None, lower=None, upper=None, scaling=None, active=None, coupled=None):
        """
        Update the one or more of the attributes of the design variable

        Parameters
        ----------
        value: float
            new value of the variable
        lower: float
            lower bound of the design variable
        upper: float
            upper bound of the design variable
        scaling: float
            scaling of the variable for an optimizer
        active: bool
            whether or not the design variable is active
        coupled: bool
            whether or not the design variable is coupled
        """

        if value is not None:
            self.value = value
        if lower is not None:
            self.lower = lower
        if upper is not None:
            self.upper = upper
        if scaling is not None:
            self.scaling = scaling
        if active is not None:
            self.active = active
        if coupled is not None:
            self.coupled = coupled
