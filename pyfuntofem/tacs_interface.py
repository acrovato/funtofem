#!/usr/bin/env python
"""
This file is part of the package FUNtoFEM for coupled aeroelastic simulation
and design optimization.

Copyright (C) 2015 Georgia Tech Research Corporation.
Additional copyright (C) 2015 Kevin Jacobson, Jan Kiviaho and Graeme Kennedy.
All rights reserved.

FUNtoFEM is licensed under the Apache License, Version 2.0 (the "License");
you may not use this software except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import print_function, division
from tacs             import TACS, functions
from .solver_interface import SolverInterface
import numpy as np


class TacsSteadyInterface(SolverInterface):
    """
    A base class to do coupled steady simulations with TACS
    """
    def __init__(self, comm, tacs_comm, model=None,ndof=1):

        # Needs to the set in the child class
        self.assembler = None
        self.res = None
        self.ans = None
        self.ext_force = None
        self.update = None
        self.mat = None
        self.pc = None
        self.struct_X_vec = None
        self.struct_nnodes = None
        self.struct_X = None
        self.svsenslist = None
        self.dvsenslist = None
        self.struct_rhs_vec = None
        self.psi_S_vec = None
        self.psi_S = None
        self.psi_T_S_vec = None
        self.psi_T_S = None
        self.ans_array = None
        self.comm = comm
        self.func_grad = None
        self.vol = 1.0 # required for AverageTemp function, not sure if needed on body level
        self.tacs = None
        self.svsens = None

        # Set by the base class
        self.gmres = None
        self.funclist = None
        self.functag = None
        self.num_components = None
        self.nfunc = model.count_functions() if model else 1

        # FIXME number of dof dependent on element type
        self.dof = ndof

        # FIXME assume temperature/heat flux entry is last entry
        self.thermal_index = self.dof-1

        self.struct_disps_all = {}
        self.struct_temps_all = {}
        self.struct_vars_all = {} # saved displacements and temps
        self.first_pass = True

    def set_mesh(self,body):
        if self.tacs_proc:
            struct_X = self.struct_X_vec.getArray()
            struct_X[:] = body.struct_X[:]

            self.assembler.setNodes(self.struct_X_vec)

            alpha = 1.0
            beta = 0.0
            gamma = 0.0
            self.assembler.assembleJacobian(alpha,beta,gamma,self.res,self.mat)
            self.pc.factor()

    def get_mesh(self,body):
        if self.tacs_proc:
            body.struct_X =  self.struct_X_vec.getArray().copy()
            body.struct_nnodes = int(body.struct_X.size/3)
        else:
            body.struct_nnodes = 0
            body.struct_X = np.array([],dtype=TACS.dtype)

    def set_variables(self,scenario,bodies):
        if bodies[0].analysis_type=='aerothermal':
            self.num_components = 0

            x = []
            for body in bodies:
                if 'structural' in body.variables:
                    for var in body.variables['structural']:
                        x.append(var.value)
                        self.num_components += 1
            x_vec = self.assembler.createDesignVec()
            x_arr = x_vec.getArray()
            x_arr[:] = x[:]
            if self.tacs_proc:
                self.assembler.setDesignVars(x_vec)
                alpha = 1.0
                beta = 0.0
                gamma = 0.0
                self.assembler.assembleJacobian(alpha,beta,gamma,self.res,self.mat)
                self.pc.factor()

        elif bodies[0].analysis_type=='aerothermoelastic':
            self.num_components = 0

            x = []
            for body in bodies:
                if 'structural' in body.variables:
                    for var in body.variables['structural']:
                        x.append(var.value)
                        self.num_components += 1

            # Set the design variable values on the processors that
            # have an instance of TACSAssembler
            if self.tacs_proc:
                x_vec = self.assembler.createDesignVec()
                x_arr = x_vec.getArray()
                x_arr[:] = x[:]
                self.assembler.setDesignVars(x_vec)

        elif bodies[0].analysis_type=='aeroelastic':
            if self.tacs_proc:
                for body in bodies:
                    if 'structural' in body.variables:

                        self.num_components = 0
                        x = np.zeros(len(body.variables['structural']),dtype=TACS.dtype)

                        for i,var in enumerate(body.variables['structural']):
                            x[i] = var.value
                            self.num_components += 1

                        self.tacs.setDesignVars(x)

                        alpha = 1.0
                        beta = 0.0
                        gamma = 0.0
                        self.tacs.assembleJacobian(alpha,beta,gamma,self.res,self.mat)
                        self.pc.factor()

    def set_functions(self,scenario,bodies):
        if bodies[0].analysis_type=='aerothermal' or bodies[0].analysis_type=='aerothermoelastic':
            if self.tacs_proc:
                self.funclist = []
                self.functag = []
                for func in scenario.functions:
                    if func.analysis_type != 'structural':
                        # use mass as a placeholder for nonstructural functions
                        self.funclist.append(functions.StructuralMass(self.assembler))
                        self.functag.append(0)

                    elif func.name.lower() == 'ksfailure':
                        if func.options:
                            ksweight = func.options['ksweight'] if 'ksweight' in func.options else 50.0
                        else:
                            ksweight = 50.0
                        self.funclist.append(functions.KSFailure(self.assembler, ksweight))
                        self.functag.append(1)

                    elif func.name.lower() == 'compliance':
                        self.funclist.append(functions.Compliance(self.assembler))
                        self.functag.append(1)

                    elif func.name.lower() == 'temperature':
                        print("TACS vol: ", self.vol)
                        self.funclist.append(functions.AverageTemperature(self.assembler, self.vol))
                        self.functag.append(1)

                    elif func.name.lower() == 'heatflux':
                        self.funclist.append(functions.HeatFlux(self.assembler))
                        self.functag.append(1)

                    elif func.name == 'mass':
                        self.funclist.append(functions.StructuralMass(self.assembler))
                        self.functag.append(-1)

                    else:
                        print('WARNING: Unknown function being set into TACS set to mass')
                        self.funclist.append(functions.StructuralMass(self.assembler))
                        self.functag.append(-1)

        elif bodies[0].analysis_type=='aeroelastic':
            if self.tacs_proc:
                self.funclist = []
                self.functag = []
                for func in scenario.functions:
                    if func.analysis_type != 'structural':
                        # use mass as a placeholder for nonstructural functions
                        self.funclist.append(functions.StructuralMass(self.tacs))
                        self.functag.append(0)

                    elif func.name.lower() == 'ksfailure':
                        if func.options:
                            ksweight = func.options['ksweight'] if 'ksweight' in func.options else 50.0
                        else:
                            ksweight = 50.0
                        self.funclist.append(functions.KSFailure(self.tacs, ksweight))
                        self.functag.append(1)

                    elif func.name.lower() == 'compliance':
                        self.funclist.append(functions.Compliance(self.tacs))
                        self.functag.append(1)

                    elif func.name == 'mass':
                        self.funclist.append(functions.StructuralMass(self.tacs))
                        self.functag.append(-1)

                    else:
                        print('WARNING: Unknown function being set into TACS set to mass')
                        self.funclist.append(functions.StructuralMass(self.tacs))
                        self.functag.append(-1)

    def get_functions(self,scenario,bodies):
        if self.tacs_proc:
            if bodies[0].analysis_type=='aerothermal' or bodies[0].analysis_type=='aerothermoelastic':
                feval = self.assembler.evalFunctions(self.funclist)
            elif bodies[0].analysis_type=='aeroelastic':
                feval = self.tacs.evalFunctions(self.funclist)
            for i, func in enumerate(scenario.functions):
                if func.analysis_type == 'structural':
                    func.value = feval[i]
        for func in scenario.functions:
            func.value = self.comm.bcast(func.value,root=0)

    def get_function_gradients(self,scenario,bodies,offset):
        for ifunc, func in enumerate(scenario.functions):
            for body in bodies:
                for vartype in body.variables:
                    if vartype == 'structural':
                        for i, var in enumerate(body.variables[vartype]):
                            if var.active:
                                if self.tacs_proc:
                                    body.derivatives[vartype][offset+ifunc][i] = self.func_grad[ifunc][i]
                                body.derivatives[vartype][offset+ifunc][i] = self.comm.bcast(body.derivatives[vartype][offset+ifunc][i],root=0)

    def eval_gradients(self,scenario,bodies):
        """ Evaluate gradients with respect to structural design variables"""
        if bodies[0].analysis_type=='aerothermal'or bodies[0].analysis_type=='aerothermoelastic':
            if self.tacs_proc:
                self.func_grad = []

                for func, dvsens in enumerate(self.dvsenslist):
                    dvsens.zeroEntries()

                # get df/dx if the function is a structural function
                self.assembler.addDVSens(self.funclist, self.dvsenslist, 1.0)

                for func, dvsens in enumerate(self.dvsenslist):
                    if self.functag[func] == 0:
                        dvsens.zeroEntries()

                    # get psi_T_S * dS/dx if a structural function that requires an adjoint
                    adjResProduct = self.assembler.createDesignVec()
                    adjResProduct_array  = adjResProduct.getArray()
                    adjResProduct_array[:] = 0.0

                    if bodies[0].analysis_type=='aerothermal':
                        if self.functag[func] > -1:
                            psi_T_S_array = self.psi_T_S_vec.getArray()
                            psi_T_S_array[:] = self.psi_T_S[:,func]

                            # addAdjointResProducts also requires a list
                            self.assembler.addAdjointResProducts([self.psi_T_S_vec], [adjResProduct])
                    elif bodies[0].analysis_type=='aerothermoelastic':
                        if self.functag[func] > -1:
                            psi_S_array = self.psi_S_vec.getArray()
                            psi_S_array[:] = self.psi_S[:,func]

                            # addAdjointResProducts also requires a list
                            self.assembler.addAdjointResProducts([self.psi_S_vec], [adjResProduct])


                    self.func_grad.append(dvsens.getArray()[:] + adjResProduct.getArray()[:])

        elif bodies[0].analysis_type=='aeroelastic':
            if self.tacs_proc:
                self.func_grad = []
                dvsens = np.zeros(self.num_components)
                for func in scenario.functions:

                    # get df/dx if the function is a structural function
                    self.tacs.evalDVSens(self.funclist[func], dvsens)
                    if self.functag[func] == 0:
                        dvsens.zeroEntries()

                    # get psi_S * dS/dx if a structural function that requires an adjoint
                    adjResProduct = np.zeros(dvsens.size)
                    if self.functag[func] > -1:
                        psi_S_array = self.psi_S_vec.getArray()
                        psi_S_array[:] = self.psi_S[:,func]
                        self.tacs.evalAdjointResProduct(self.psi_S_vec, adjResProduct)

                    self.func_grad.append(dvsens[:] + adjResProduct[:])

        return

    # FIXME function not yet updated for aerothermal coordinate derivatives
    # old eval_Sens functions still used currently
    def get_coordinate_derivatives(self,scenario,bodies,step):
        """ Evaluate gradients with respect to structural design variables"""

        #FIXME assuming only body
        if bodies[0].shape:
            if self.tacs_proc:

                if bodies[0].analysis_type=='aerothermal' or bodies[0].analysis_type=='aerothermoelastic':

                    fXptSens = self.assembler.createNodeVec()
                    adjResProduct_vec = self.assembler.createNodeVec()

                    for func in range(len(scenario.functions)):
                        # get df/dx if the function is a structural function
                        self.assembler.addXptSens(self.funclist[func], fXptSens)
                        df = fXptSens.getArray()

                        if bodies[0].analysis_type=='aerothermal':
                            if self.functag[func] == 0:
                                df *= 0.0

                            # get psi_T_S * dS/dx if a structural function that requires an adjoint
                            if self.functag[func] > -1:
                                psi_T_S_array = self.psi_T_S_vec.getArray()
                                psi_T_S_array[:] = self.psi_T_S[:,func]
                                self.assembler.addAdjointResXptSensProduct(self.psi_T_S_vec, adjResProduct_vec)
                                adjResProduct = adjResProduct_vec.getArray()
                            else:
                                adjResProduct = np.zeros(df.size,dtype=TACS.dtype)

                        elif bodies[0].analysis_type=='aerothermoelastic':
                            if self.functag[func] == 0:
                                df[:] = 0.0

                            # get psi_T_S * dS/dx if a structural function that requires an adjoint
                            if self.functag[func] > -1:
                                psi_S_array = self.psi_S_vec.getArray()
                                psi_S_array[:] = self.psi_S[:,func]
                                self.assembler.addAdjointResXptSensProduct(self.psi_S_vec, adjResProduct_vec)
                                adjResProduct = adjResProduct_vec.getArray()
                            else:
                                adjResProduct = np.zeros(df.size,dtype=TACS.dtype)


                        bodies[0].struct_shape_term[:,func] += df[:] + adjResProduct[:]

                elif bodies[0].analysis_type=='aeroelastic':
                    fXptSens = self.tacs.createNodeVec()
                    adjResProduct_vec = self.tacs.createNodeVec()

                    for func,_ in enumerate(scenario.functions):

                        # get df/dx if the function is a structural function
                        self.tacs.evalXptSens(self.funclist[func], fXptSens)
                        df = fXptSens.getArray()
                        if self.functag[func] == 0:
                            df[:] = 0.0

                        # get psi_S * dS/dx if a structural function that requires an adjoint
                        if self.functag[func] > -1:
                            psi_S_array = self.psi_S_vec.getArray()
                            psi_S_array[:] = self.psi_S[:,func]
                            self.tacs.evalAdjointResXptSensProduct(self.psi_S_vec, adjResProduct_vec)
                            adjResProduct = adjResProduct_vec.getArray()
                        else:
                            adjResProduct = np.zeros(df.size,dtype=TACS.dtype)

                        bodies[0].struct_shape_term[:,func] += df[:] + adjResProduct[:]

    def initialize(self, scenario, bodies):
        if bodies[0].analysis_type=='aerothermal':
            if self.first_pass:
                for body in bodies:
                    self.get_mesh(body)
                    # FIXME need initial temperatures defined to pass to fluid solver
                    # currently initializing to the TACS reference temperature
                    body.struct_temps = np.ones(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype) * body.T_ref
                self.first_pass = False
            else:
                for body in bodies:
                    self.set_mesh(body)
                    body.struct_temps = np.ones(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype) * body.T_ref

        elif bodies[0].analysis_type=='aerothermoelastic':
            if self.first_pass:
                for body in bodies:
                    self.get_mesh(body)
                    # Need initial temperatures defined to pass to fluid solver
                    # currently initializing to the TACS reference temperature
                    body.struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof, dtype=TACS.dtype)
                    body.struct_temps = np.ones(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype) * body.T_ref
                self.first_pass = False
            else:
                for body in bodies:
                    self.set_mesh(body)
                    body.struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof, dtype=TACS.dtype)
                    body.struct_temps = np.ones(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype) * body.T_ref

            if self.tacs_proc:
                # Assemble and factor the Jacobian matrix
                alpha = 1.0 # Jacobian coefficient for the state variables
                beta = 0.0 # Jacobian coeff. for the first time derivative of the state variables
                gamma = 0.0 # Coeff. for the second time derivative of the state variables
                self.assembler.assembleJacobian(alpha, beta, gamma, self.res, self.mat)
                self.pc.factor()

                # Set the boundary conditions
                self.assembler.setBCs(self.ans)
                self.assembler.setVariables(self.ans)

        elif bodies[0].analysis_type=='aeroelastic':
            if self.first_pass:
                for body in bodies:
                    self.get_mesh(body)
                self.first_pass = False
            else:
                for body in bodies:
                    self.set_mesh(body)

        return 0

    def iterate(self, scenario, bodies, step):
        fail = 0

        if bodies[0].analysis_type=='aerothermal':
            if self.tacs_proc:
                # Compute the residual from tacs self.res = K*u
                self.assembler.assembleRes(self.res)
                res_array = self.res.getArray()
                res_array[:] = 0.0

                for body in bodies:
                    # Set heat flux on structure
                    res_array[self.thermal_index::self.dof] += body.struct_heat_flux[:]

                # Add the aerodynamic heat flux in the residual
                self.assembler.setBCs(self.res)

                # Solve
                self.gmres.solve(self.res, self.ans)
                self.assembler.setVariables(self.ans)

                ans_array = self.ans.getArray()

                # Extract displacements and temperatures
                for body in bodies:
                    body.struct_temps = np.zeros(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype)
                    body.struct_temps[:] = ans_array[self.thermal_index::self.dof]
            else:
                for body in bodies:
                    body.struct_temps = np.zeros(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype)

        elif bodies[0].analysis_type=='aerothermoelastic':
            if self.tacs_proc:
                # Compute the residual from tacs self.res = K*u - f_internal
                self.assembler.assembleRes(self.res)

                # Add the external forces into a TACS vector that will be added to
                # the residual
                self.ext_force.zeroEntries()
                ext_force_array = self.ext_force.getArray()

                # Add the external load and heat fluxes on the structure
                for body in bodies:
                    for i in range(body.xfer_ndof):
                        ext_force_array[i::self.dof] += body.struct_loads[i::body.xfer_ndof]
                    ext_force_array[self.thermal_index::self.dof] += body.struct_heat_flux[:]

                # Zero the contributions at the DOF associated with boundary
                # conditions so that it doesn't interfere with Dirichlet BCs
                self.assembler.applyBCs(self.ext_force)

                # Add the contribution to the residuals from the external forces
                self.res.axpy(-1.0, self.ext_force)

                # Solve for the update
                self.gmres.solve(self.res, self.update)

                # Apply the update to the solution vector and reset the boundary condition
                # data so that it is precisely statisfied
                self.ans.axpy(-1.0, self.update)
                self.assembler.setBCs(self.ans)

                # Set the variables into the assembler object
                self.assembler.setVariables(self.ans)

                # Extract displacements and temperatures for each body
                ans_array = self.ans.getArray()
                for body in bodies:
                    body.struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof,dtype=TACS.dtype)
                    for i in range(body.xfer_ndof):
                        body.struct_disps[i::body.xfer_ndof] = ans_array[i::self.dof]

                    body.struct_temps = np.zeros(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype)
                    body.struct_temps[:] = ans_array[self.thermal_index::self.dof]
            else:
                for body in bodies:
                    body.struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof,dtype=TACS.dtype)
                    body.struct_temps = np.zeros(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype)

        elif bodies[0].analysis_type=='aeroelastic':
            if self.tacs_proc:
                # Compute the residual from tacs self.res = K*u
                self.tacs.assembleRes(self.res)
                res_array = self.res.getArray()
                res_array[:] = 0.0

                for body in bodies:
                    # Set loads on structure
                    #FIXME: set into only body indices
                    for i in range(body.xfer_ndof):
                        res_array[i::self.dof] += body.struct_loads[i::body.xfer_ndof]

                # Add the aerodynamic loads in the residual
                self.tacs.applyBCs(self.res)

                # Solve
                self.pc.applyFactor(self.res, self.ans)
                self.tacs.setVariables(self.ans)

                ans_array = self.ans.getArray()

                # Extract displacements
                for body in bodies:
                    body.struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof,dtype=TACS.dtype)
                    for i in range(body.xfer_ndof):
                        body.struct_disps[i::body.xfer_ndof] = ans_array[i::self.dof]
            else:
                for body in bodies:
                    body.struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof,dtype=TACS.dtype)

        return fail

    def post(self,scenario,bodies):
        if self.tacs_proc:
            if bodies[0].analysis_type=='aerothermal':
                self.struct_temps_all[scenario.id]=self.ans.getArray().copy()
            elif bodies[0].analysis_type=='aerothermoelastic':
                self.struct_vars_all[scenario.id]=self.ans.getArray().copy()
            elif bodies[0].analysis_type=='aeroelastic':
                self.struct_disps_all[scenario.id]=self.ans.getArray().copy()

            # export the f5 file
            try:
                self.post_export_f5()
            except:
                print("No f5 export set up")

    def initialize_adjoint(self,scenario,bodies):

        if bodies[0].analysis_type=='aerothermal':
            nfunctions = scenario.count_adjoint_functions()
            if self.tacs_proc:
                ans_array = self.ans.getArray()
                # FIXME both self.struct_disps_all and self.struct_temps_all store all ans data
                # made separate variable for naming consistency
                ans_array[:] = self.struct_temps_all[scenario.id]

                self.assembler.setVariables(self.ans)
                self.assembler.evalFunctions(self.funclist)

                for body in bodies:
                    body.struct_temps = np.zeros(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype)
                    body.struct_temps[:] = ans_array[self.thermal_index::self.dof]
            else:
                for body in bodies:
                    body.struct_temps = np.zeros(body.struct_nnodes*body.therm_xfer_ndof)

        elif bodies[0].analysis_type=='aerothermoelastic':
            nfunctions = scenario.count_adjoint_functions()
            if self.tacs_proc:
                ans_array = self.ans.getArray()
                ans_array[:] = self.struct_vars_all[scenario.id]

                self.assembler.setVariables(self.ans)
                self.assembler.evalFunctions(self.funclist)

                # Extract the displacements and temperatures for each body
                for body in bodies:
                    struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof,dtype=TACS.dtype)
                    body.struct_temps = np.zeros(body.struct_nnodes*body.therm_xfer_ndof, dtype=TACS.dtype)
                    for i in range(body.xfer_ndof):
                        struct_disps[i::body.xfer_ndof] = ans_array[i::self.dof]
                    body.struct_temps[:] = ans_array[self.thermal_index::self.dof]

            else:
                for body in bodies:
                    struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof)
                    body.struct_temps = np.zeros(body.struct_nnodes*body.therm_xfer_ndof)

            if self.tacs_proc:
                # Assemble the transpose of the Jacobian matrix for the adjoint
                # computations. Note that for thermoelastic computations, the Jacobian
                # matrix is non-symmetric due to the temperature-deformation coupling.
                # The transpose must be used here to get the right result.
                alpha = 1.0 # Jacobian coefficient for the state variables
                beta = 0.0 # Jacobian coeff. for the first time derivative of the state variables
                gamma = 0.0 # Coeff. for the second time derivative of the state variables
                self.assembler.assembleJacobian(alpha, beta, gamma, self.res, self.mat, matOr=TACS.TRANSPOSE)
                self.pc.factor()

                # Evaluate the functions in preparation for evaluating the derivative
                # of the functions w.r.t. the state variables. Some TACS functions
                # require their evaluation to store internal data before the sensitivities
                # can be computed.
                feval = self.assembler.evalFunctions(self.funclist)

                # Zero the vectors in the sensitivity list
                for svsens in self.svsenslist:
                    svsens.zeroEntries()

                # Compute the derivative of the function with respect to the
                # state variables
                self.assembler.addSVSens(self.funclist, self.svsenslist, 1.0, 0.0, 0.0)

                # Evaluate state variable sensitivities and scale to get right-hand side
                for func in range(len(self.funclist)):
                    # Check if the function is a TACS function or not
                    if self.functag[func] == -1:
                        break

                    if self.functag[func] == 1:
                        self.svsenslist[func].scale(-1.0)
                    else:
                        self.svsenslist[func].zeroEntries()

        elif bodies[0].analysis_type=='aeroelastic':
            if self.tacs_proc:
                ans_array = self.ans.getArray()
                ans_array[:] = self.struct_disps_all[scenario.id]

                self.tacs.setVariables(self.ans)
                self.tacs.evalFunctions(self.funclist)

                for body in bodies:
                    struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof,dtype=TACS.dtype)
                    for i in range(body.xfer_ndof):
                        struct_disps[i::body.xfer_ndof] = ans_array[i::self.dof]
            else:
                for body in bodies:
                    struct_disps = np.zeros(body.struct_nnodes*body.xfer_ndof)

        return 0

    def iterate_adjoint(self, scenario, bodies, step):
        fail = 0
        if bodies[0].analysis_type=='aerothermal':
            for body in bodies:
                body.psi_T_S[:,:] = 0.0

            if self.tacs_proc:
                feval = self.assembler.evalFunctions(self.funclist)
                for svsens in self.svsenslist:
                    svsens.zeroEntries()

                # Compute the derivative of the function with respect to the
                # state variables. Note that the vector is zeroed above.
                self.assembler.addSVSens(self.funclist, self.svsenslist, 1.0, 0.0, 0.0)

                # Evaluate state variable sensitivities and scale to get right-hand side
                for func in range(len(self.funclist)):
                    # Check if the function is a TACS function or not
                    if self.functag[func] == -1:
                        break

                    if self.functag[func] == 1:
                        self.svsenslist[func].scale(-1.0)
                    else:
                        self.svsenslist[func].scale(0.0)

                    self.struct_rhs_vec.copyValues(self.svsenslist[func])
                    struct_rhs_array = self.struct_rhs_vec.getArray()

                    for body in bodies:
                        # Form new right-hand side of structural adjoint equation using state
                        # variable sensitivites and the transformed temperature transfer
                        # adjoint variables
                        # FIXME index slice for body
                        for i in range(body.therm_xfer_ndof):
                            struct_rhs_array[self.thermal_index::self.dof] += body.struct_rhs_T[i::body.therm_xfer_ndof, func]

                        # Solve structural adjoint equation
                        # FIXME applyBCs doesn't seem to actually enforce thermal boundary conditions,
                        # using setBCs instead
                        self.assembler.applyBCs(self.struct_rhs_vec)
                        self.gmres.solve(self.struct_rhs_vec, self.psi_T_S_vec)
                        psi_T_S_array = self.psi_T_S_vec.getArray()
                        self.psi_T_S[:,func] = psi_T_S_array[:]

                        # resize to the size of the structural force vector
                        for i in range(body.therm_xfer_ndof):
                            body.psi_T_S[i::body.therm_xfer_ndof, func] = self.psi_T_S[self.thermal_index::self.dof, func]

        elif bodies[0].analysis_type=='aerothermoelastic':
            for body in bodies:
                body.psi_S[:,:] = 0.0
                body.psi_T_S[:,:] = 0.0

            if self.tacs_proc:
                # Evaluate state variable sensitivities and scale to get right-hand side
                for func in range(len(self.funclist)):
                    # Check if the function is a TACS function or not
                    if self.functag[func] == -1:
                        break

                    # Copy values into the right-hand-side
                    self.struct_rhs_vec.copyValues(self.svsenslist[func])
                    struct_rhs_array = self.struct_rhs_vec.getArray()

                    for body in bodies:
                        # Form new right-hand side of structural adjoint equation using state
                        # variable sensitivites and the transformed temperature transfer
                        # adjoint variables
                        for i in range(body.xfer_ndof):
                            struct_rhs_array[i::self.dof] += body.struct_rhs[i::body.xfer_ndof,func]
                        for i in range(body.therm_xfer_ndof):
                            struct_rhs_array[self.thermal_index::self.dof] += body.struct_rhs_T[i::body.therm_xfer_ndof, func]

                    # Zero the adjoint right-hand-side conditions at DOF locations
                    # where the boundary conditions are applied. This is consistent with
                    # the forward analysis where the forces/fluxes contributiosn are
                    # zeroed at Dirichlet DOF locations.
                    self.assembler.applyBCs(self.struct_rhs_vec)

                    # Solve structural adjoint equation
                    self.gmres.solve(self.struct_rhs_vec, self.psi_S_vec)

                    # Extract the adjoint variables and store them
                    psi_S_array = self.psi_S_vec.getArray()
                    self.psi_S[:,func] = psi_S_array[:]

                    # Set the adjoint variables for each body
                    for body in bodies:
                        for i in range(body.xfer_ndof):
                            body.psi_S[i::body.xfer_ndof, func] = self.psi_S[i::self.dof, func]
                        for i in range(body.therm_xfer_ndof):
                            body.psi_T_S[i::body.therm_xfer_ndof, func] = self.psi_S[self.thermal_index::self.dof, func]

        elif bodies[0].analysis_type=='aeroelastic':
            for body in bodies:
                body.psi_S[:,:] = 0.0

            if self.tacs_proc:
                self.tacs.evalFunctions(self.funclist)
                for func,_ in enumerate(self.funclist):
                    if self.functag[func] == -1:
                        break
                    # Evaluate state variable sensitivities and scale to get right-hand side
                    self.tacs.evalSVSens(self.funclist[func], self.svsens)
                    if self.functag[func] == 1:

                        self.svsens.scale(-1.0)
                    else:
                        self.svsens.scale(0.0)

                    self.struct_rhs_vec.copyValues(self.svsens)
                    struct_rhs_array = self.struct_rhs_vec.getArray()

                    for body in bodies:
                        # Form new right-hand side of structural adjoint equation using state
                        # variable sensitivites and the transformed displacement transfer
                        # adjoint variables
                        #FIXME index slice for body
                        for i in range(body.xfer_ndof):
                            struct_rhs_array[i::self.dof] += body.struct_rhs[i::body.xfer_ndof,func]

                        # Solve structural adjoint equation
                        self.tacs.applyBCs(self.struct_rhs_vec)
                        self.gmres.solve(self.struct_rhs_vec, self.psi_S_vec)
                        psi_S_6dof = self.psi_S_vec.getArray()
                        self.psi_S[:,func] = psi_S_6dof[:]

                        # resize to the size of the structural force vector
                        for i in range(body.xfer_ndof):
                            body.psi_S[i::body.xfer_ndof,func] = self.psi_S[i::self.dof,func]

        return fail

    def post_adjoint(self,scenario,bodies):
        if self.tacs_proc:
            self.eval_gradients(scenario,bodies)
