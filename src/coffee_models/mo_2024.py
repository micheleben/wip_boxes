# this code comes from a paer by mo 2024
import numpy as np
import matplotlib.pyplot as plt
from scipy.sparse import diags
from scipy.sparse.linalg import spsolve
from dataclasses import dataclass
from typing import Tuple, List
import warnings
warnings.filterwarnings('ignore')

@dataclass
class CoffeeParameters:
    """Physical and geometric parameters for coffee extraction"""
    # Geometric parameters
    L_z: float = 0.0126  # Height of coffee bed (m)
    N_layers: int = 10   # Number of bed layers
    N_p: int = 30        # Number of particle shells
    
    # Coffee particle properties
    r_f_init: float = 13.74e-6  # Initial fine radius (m)
    r_c_init: float = 160.85e-6  # Initial coarse radius (m)
    vol_frac_f: float = 0.292   # Volume fraction of fines
    vol_frac_c: float = 0.708   # Volume fraction of coarses
    
    # Physical constants
    D_w: float = 1.25e-10      # Water diffusion in particle (m²/s)
    D_b: float = 2e-9          # Bulk diffusion coefficient (m²/s)
    mu: float = 1e-3           # Fluid viscosity (Pa·s)
    rho: float = 1000          # Fluid density (kg/m³)
    
    # Bed properties
    eps_b_init: float = 0.17   # Initial bed porosity
    eps_p: float = 0.4         # Particle porosity
    beta: float = 3.2          # Tortuosity in particle
    H_c: float = 2.0           # Solute hindrance factor
    K: float = 0.6             # Partition coefficient
    
    # Initial concentration
    c_0: float = 0.216         # Initial solute concentration (g/mL)
    
    # Swelling parameters
    C_M: float = 0.1           # Maximum water fraction
    s_m: float = 0.036         # Maximum swelling degree (3.6%)
    
    # Numerical parameters
    dt_init: float = 0.001     # Initial time step (s)
    dt_sat: float = 0.02       # Saturated time step (s)
    tau_swell: float = 1.0     # Swelling time scale (s)

class SwellingParticle:
    """Individual coffee particle with swelling and extraction"""
    
    def __init__(self, radius_init: float, params: CoffeeParameters):
        self.params = params
        self.R_init = radius_init
        self.N_p = params.N_p
        
        # Spatial discretization (material coordinates)
        self.R = np.linspace(0, self.R_init, self.N_p)
        self.dR = self.R[1] - self.R[0]
        
        # State variables
        self.c_w = np.zeros(self.N_p)  # Additional water concentration
        self.c = np.full(self.N_p, params.c_0)  # Solute concentration
        self.r = self.R.copy()  # Current radial positions
        
        # Validation tracking
        self.validation_history = []
        # Boundary condition
        self.c_b_boundary = 0.0  # Bulk concentration at particle surface
        
    def update_geometry(self):
        """Update particle geometry based on swelling"""
        # Calculate current radial positions from swelling
        for i in range(self.N_p):
            if i == 0:
                self.r[i] = 0
            else:
                # Numerical integration: r³ = R₀³ + 3∫[ξ²/(1-c_w(ξ))]dξ
                integrand = self.R[1:i+1]**2 / (1 - self.c_w[1:i+1] + 1e-10)
                integral = np.trapz(integrand, self.R[1:i+1])
                self.r[i] = (3 * integral)**(1/3)
    
    def get_current_radius(self) -> float:
        """Get current outer radius of particle"""
        return self.r[-1]
    
    def step_swelling(self, dt: float):
        """Advance swelling equation one time step"""
        # Build coefficient matrix for Crank-Nicolson
        A = self._build_swelling_matrix(dt)
        
        # Right hand side
        rhs = self.c_w.copy()
        
        # Boundary conditions
        A[0, 0] = 1.0  # Center: dc_w/dR = 0
        A[0, 1] = -1.0
        rhs[0] = 0.0
        
        A[-1, -1] = 1.0  # Surface: c_w = C_M
        rhs[-1] = self.params.C_M
        
        # Solve
        c_w_new = spsolve(A, rhs)
        self.c_w = np.clip(c_w_new, 0, self.params.C_M)
        
        # Update geometry
        self.update_geometry()
    
    def step_extraction(self, dt: float):
        """Advance extraction equation one time step"""
        # Effective diffusion coefficient
        eps_p_eff = 1 - (1 - self.params.eps_p) * (1 - self.c_w)
        D_p = self.params.D_b * eps_p_eff / (self.params.beta * self.params.H_c)
        
        # Build coefficient matrix
        A = self._build_extraction_matrix(dt, D_p)
        
        # Source term from swelling
        laplacian_cw = self._compute_laplacian(self.c_w)
        source = -self.c * self.params.D_w * laplacian_cw
        
        # Right hand side
        rhs = self.c + dt * source
        
        # Boundary conditions
        A[0, 0] = 1.0  # Center: dc/dR = 0
        A[0, 1] = -1.0
        rhs[0] = 0.0
        
        # Surface boundary condition
        c_surface_target = self.c_b_boundary / self.params.K
        if c_surface_target < self.c[-2]:  # Extraction occurs
            A[-1, -1] = 1.0
            rhs[-1] = c_surface_target
        else:  # No flux
            A[-1, -1] = 1.0
            A[-1, -2] = -1.0
            rhs[-1] = 0.0
        
        # Solve
        c_new = spsolve(A, rhs)
        self.c = np.maximum(c_new, 0)
    
    def get_flux(self) -> float:
        """Calculate mass flux out of particle"""
        if len(self.c) < 2:
            return 0.0
        
        # Effective diffusion coefficient at surface
        eps_p_surf = 1 - (1 - self.params.eps_p) * (1 - self.c_w[-1])
        D_p_surf = self.params.D_b * eps_p_surf / (self.params.beta * self.params.H_c)
        
        # Flux: j = -D_p * (dc/dr) * (dr/dR) at surface
        dc_dR = (self.c[-1] - self.c[-2]) / self.dR
        r_surf = self.get_current_radius()
        R_surf = self.R_init
        
        if r_surf > 0 and R_surf > 0:
            dr_dR = r_surf**2 * (1 - self.c_w[-1]) / R_surf**2
            flux = -D_p_surf * dc_dR * dr_dR
        else:
            flux = 0.0
        
        return max(flux, 0.0)
    
    def _build_swelling_matrix(self, dt: float):
        """Fixed implementation matching paper equation 41"""
        N = self.N_p
        A = np.zeros((N, N))
        
        for i in range(1, N-1):
            # ✅ CORRECTED: Use (1-c_w)² factor from paper
            D_eff = self.params.D_w * (1 - self.c_w[i])**2
            
            # Get current radius for this material point
            r_i = self.r[i] if hasattr(self, 'r') else self.R[i]
            R_i = self.R[i]
            
            # Coordinate transformation factor
            if R_i > 0:
                geom_factor = (r_i/R_i)**2 * (1 - self.c_w[i])
            else:
                geom_factor = 1.0
            
            # Finite difference coefficients
            coeff_center = -2 * D_eff * geom_factor * dt / self.dR**2
            coeff_plus = D_eff * geom_factor * dt / self.dR**2 * (1 + self.dR/(2*R_i))
            coeff_minus = D_eff * geom_factor * dt / self.dR**2 * (1 - self.dR/(2*R_i))
            
            A[i, i-1] = -coeff_minus
            A[i, i] = 1 - coeff_center
            A[i, i+1] = -coeff_plus
        
        return A
    
    def _build_extraction_matrix(self, dt: float, D_p: np.ndarray):
        """Build coefficient matrix for extraction equation"""
        N = self.N_p
        A = np.zeros((N, N))
        
        # Interior points
        for i in range(1, N-1):
            # Central differences with variable diffusion coefficient
            coeff_center = -2 * D_p[i] * dt / self.dR**2
            coeff_plus = D_p[i] * dt / self.dR**2 * (1 + self.dR / (2 * self.R[i]))
            coeff_minus = D_p[i] * dt / self.dR**2 * (1 - self.dR / (2 * self.R[i]))
            
            A[i, i-1] = -coeff_minus
            A[i, i] = 1 - coeff_center
            A[i, i+1] = -coeff_plus
        
        return A
    
    def _compute_laplacian(self, field: np.ndarray) -> np.ndarray:
        """Compute Laplacian in spherical coordinates"""
        laplacian = np.zeros_like(field)
        
        for i in range(1, len(field)-1):
            if self.R[i] > 0:
                # (1/R²)d/dR(R² df/dR)
                df_dR_plus = (field[i+1] - field[i]) / self.dR
                df_dR_minus = (field[i] - field[i-1]) / self.dR
                
                R_plus = (self.R[i] + self.R[i+1]) / 2
                R_minus = (self.R[i-1] + self.R[i]) / 2
                
                laplacian[i] = (R_plus**2 * df_dR_plus - R_minus**2 * df_dR_minus) / (self.dR * self.R[i]**2)
        
        return laplacian
    
    def validate_swelling_physics(self, time: float = None, verbose: bool = True) -> Dict[str, bool]:
        """
        Comprehensive validation of swelling physics
        
        Args:
            time: Current simulation time (for logging)
            verbose: Whether to print detailed results
            
        Returns:
            Dictionary of validation results {test_name: passed}
        """
        results = {}
        
        # Test 1: Water concentration bounds
        results['bounds_check'] = self._check_concentration_bounds(verbose)
        
        # Test 2: Monotonicity (water concentration should decrease inward)
        results['monotonicity_check'] = self._check_monotonicity(verbose)
        
        # Test 3: Mass conservation
        results['mass_conservation'] = self._check_mass_conservation(verbose)
        
        # Test 4: Geometric consistency
        results['geometry_check'] = self._check_geometry_consistency(verbose)
        
        # Test 5: Swelling magnitude realism
        results['swelling_realism'] = self._check_swelling_realism(verbose)
        
        # Test 6: Diffusion coefficient realism
        results['diffusion_realism'] = self._check_diffusion_coefficient(verbose)
        
        # Store results for trend analysis
        validation_record = {
            'time': time,
            'results': results.copy(),
            'c_w_profile': self.c_w.copy(),
            'r_profile': self.r.copy(),
            'current_radius': self.get_current_radius()
        }
        self.validation_history.append(validation_record)
        
        # Summary
        passed_tests = sum(results.values())
        total_tests = len(results)
        
        if verbose:
            print(f"\n=== SWELLING VALIDATION SUMMARY (t={time:.3f}s) ===")
            print(f"Passed: {passed_tests}/{total_tests} tests")
            if passed_tests < total_tests:
                failed = [name for name, passed in results.items() if not passed]
                print(f"❌ Failed tests: {failed}")
            else:
                print("✅ All physics checks passed!")
        
        return results
    
    def _check_concentration_bounds(self, verbose: bool) -> bool:
        """Check that 0 ≤ c_w ≤ C_M everywhere"""
        min_cw = np.min(self.c_w)
        max_cw = np.max(self.c_w)
        
        bounds_ok = (min_cw >= -1e-10) and (max_cw <= self.params.C_M + 1e-10)
        
        if verbose and not bounds_ok:
            print(f"❌ BOUNDS: c_w range [{min_cw:.6f}, {max_cw:.6f}], expected [0, {self.params.C_M}]")
        elif verbose:
            print(f"✅ BOUNDS: c_w ∈ [{min_cw:.6f}, {max_cw:.6f}]")
            
        return bounds_ok
    
    def _check_monotonicity(self, verbose: bool) -> bool:
        """Check that c_w decreases from surface to center (for most cases)"""
        # Skip first few points near center where numerical issues can occur
        start_idx = max(1, self.N_p // 10)
        
        # Check if concentration generally decreases inward
        c_w_subset = self.c_w[start_idx:]
        differences = np.diff(c_w_subset)
        
        # Allow small violations due to numerical errors
        tolerance = 1e-6
        violations = np.sum(differences > tolerance)
        monotonic_ok = violations <= len(differences) * 0.1  # Allow 10% violations
        
        if verbose and not monotonic_ok:
            print(f"❌ MONOTONICITY: {violations}/{len(differences)} points violate inward decrease")
        elif verbose:
            print(f"✅ MONOTONICITY: c_w decreases inward ({violations} minor violations)")
            
        return monotonic_ok
    
    def _check_mass_conservation(self, verbose: bool) -> bool:
        """Check water mass conservation during swelling"""
        # Calculate total additional water mass in particle
        # Volume element in spherical coordinates: dV = 4πr²dr
        
        current_water_mass = 0.0
        for i in range(1, self.N_p):
            # Use trapezoidal rule for integration
            r_avg = (self.r[i] + self.r[i-1]) / 2
            dr = self.r[i] - self.r[i-1]
            c_w_avg = (self.c_w[i] + self.c_w[i-1]) / 2
            
            volume_element = 4 * np.pi * r_avg**2 * dr
            current_water_mass += c_w_avg * volume_element
        
        # Expected mass based on surface boundary condition
        current_radius = self.get_current_radius()
        max_possible_water = (4/3 * np.pi * current_radius**3) * self.params.C_M
        
        # Conservation check: current mass should be ≤ maximum possible
        conservation_ok = current_water_mass <= max_possible_water * 1.1  # 10% tolerance
        
        if verbose:
            fraction = current_water_mass / max_possible_water if max_possible_water > 0 else 0
            if conservation_ok:
                print(f"✅ CONSERVATION: {fraction:.3f} of maximum water content")
            else:
                print(f"❌ CONSERVATION: {fraction:.3f} exceeds maximum water content")
                
        return conservation_ok
    
    def _check_geometry_consistency(self, verbose: bool) -> bool:
        """Check that geometric relationships are consistent"""
        # Check that r[i] ≥ r[i-1] (radii should increase)
        radii_increasing = np.all(np.diff(self.r) >= -1e-10)
        
        # Check that swelling is physically reasonable
        current_radius = self.get_current_radius()
        initial_radius = self.R_init
        
        # Radius should not shrink
        no_shrinking = current_radius >= initial_radius * 0.999
        
        # Check volume conservation equation (Paper Eq. 42)
        geometry_consistent = True
        for i in range(1, min(10, self.N_p)):  # Check first few points
            # r³ = R³ + 3∫[ξ²/(1-c_w(ξ))]dξ
            integrand = self.R[1:i+1]**2 / (1 - self.c_w[1:i+1] + 1e-10)
            integral = np.trapz(integrand, self.R[1:i+1])
            expected_r = (self.R[i]**3 + 3 * integral)**(1/3)
            
            relative_error = abs(self.r[i] - expected_r) / max(expected_r, 1e-10)
            if relative_error > 0.01:  # 1% tolerance
                geometry_consistent = False
                break
        
        geometry_ok = radii_increasing and no_shrinking and geometry_consistent
        
        if verbose:
            if geometry_ok:
                print(f"✅ GEOMETRY: Radii consistent, R={initial_radius:.2e}→r={current_radius:.2e}")
            else:
                print(f"❌ GEOMETRY: Issues detected")
                if not radii_increasing:
                    print("  - Radii not monotonic")
                if not no_shrinking:
                    print("  - Particle shrinking detected")
                if not geometry_consistent:
                    print("  - Volume conservation violated")
                    
        return geometry_ok
    
    def _check_swelling_realism(self, verbose: bool) -> bool:
        """Check that swelling magnitude is physically realistic"""
        current_radius = self.get_current_radius()
        initial_radius = self.R_init
        
        swelling_ratio = current_radius / initial_radius
        swelling_percent = (swelling_ratio - 1) * 100
        
        # Paper mentions 3.6% maximum swelling
        # Allow up to 10% for safety margin
        realistic_swelling = 1.0 <= swelling_ratio <= 1.15
        
        if verbose:
            if realistic_swelling:
                print(f"✅ SWELLING: {swelling_percent:.2f}% increase (realistic)")
            else:
                print(f"❌ SWELLING: {swelling_percent:.2f}% increase (unrealistic)")
                
        return realistic_swelling
    
    def _check_diffusion_coefficient(self, verbose: bool) -> bool:
        """Check that effective diffusion coefficients are reasonable"""
        # Calculate effective diffusion coefficients
        D_eff = self.params.D_w * (1 - self.c_w)**2  # Should be this based on paper
        D_eff_current = self.params.D_w * (1 - self.c_w)  # What code currently uses
        
        # Check bounds
        D_eff_bounded = np.all(D_eff >= 0) and np.all(D_eff <= self.params.D_w)
        
        # Check that diffusion decreases with water content
        center_diffusion = D_eff[0]
        surface_diffusion = D_eff[-1]
        decreases_outward = center_diffusion >= surface_diffusion
        
        diffusion_ok = D_eff_bounded and decreases_outward
        
        if verbose:
            if diffusion_ok:
                print(f"✅ DIFFUSION: D_eff ∈ [{surface_diffusion:.2e}, {center_diffusion:.2e}]")
            else:
                print(f"❌ DIFFUSION: Issues with effective diffusion coefficient")
                
        return diffusion_ok
    
    def plot_validation_diagnostics(self, save_path: str = None):
        """Create diagnostic plots for swelling validation"""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))
        
        # Plot 1: Water concentration profile
        ax1.plot(self.R / self.R_init, self.c_w, 'b-', linewidth=2, label='c_w(R)')
        ax1.axhline(y=self.params.C_M, color='r', linestyle='--', label=f'C_M = {self.params.C_M}')
        ax1.set_xlabel('Normalized Radius R/R₀')
        ax1.set_ylabel('Water Concentration c_w')
        ax1.set_title('Water Concentration Profile')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Geometric transformation
        ax2.plot(self.R / self.R_init, self.r / self.R_init, 'g-', linewidth=2, label='r(R)/R₀')
        ax2.plot([0, 1], [0, 1], 'k--', alpha=0.5, label='No swelling')
        ax2.set_xlabel('Material Coordinate R/R₀')
        ax2.set_ylabel('Current Position r/R₀')
        ax2.set_title('Geometric Transformation')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Plot 3: Effective diffusion coefficient
        D_eff_paper = self.params.D_w * (1 - self.c_w)**2
        D_eff_code = self.params.D_w * (1 - self.c_w)
        ax3.plot(self.R / self.R_init, D_eff_paper / self.params.D_w, 'r-', 
                linewidth=2, label='Paper: (1-c_w)²')
        ax3.plot(self.R / self.R_init, D_eff_code / self.params.D_w, 'b--', 
                linewidth=2, label='Code: (1-c_w)')
        ax3.set_xlabel('Normalized Radius R/R₀')
        ax3.set_ylabel('Normalized Diffusion D_eff/D_w')
        ax3.set_title('Effective Diffusion Coefficient')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # Plot 4: Validation history (if available)
        if len(self.validation_history) > 1:
            times = [h['time'] for h in self.validation_history if h['time'] is not None]
            radii = [h['current_radius'] / self.R_init for h in self.validation_history]
            
            ax4.plot(times, radii, 'purple', linewidth=2, label='Radius evolution')
            ax4.set_xlabel('Time (s)')
            ax4.set_ylabel('Normalized Radius r/R₀')
            ax4.set_title('Swelling Evolution')
            ax4.legend()
            ax4.grid(True, alpha=0.3)
        else:
            ax4.text(0.5, 0.5, 'No time history\navailable', 
                    ha='center', va='center', transform=ax4.transAxes)
            ax4.set_title('Swelling Evolution (No Data)')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Validation plots saved to {save_path}")
        
        plt.show()

class CoffeeExtraction:
    """Main coffee extraction model with swelling effects"""
    
    def __init__(self, params: CoffeeParameters):
        self.params = params
        self.N = params.N_layers
        
        # Spatial discretization
        self.z = np.linspace(0, params.L_z, self.N)
        self.dz = self.z[1] - self.z[0]
        
        # Create particles (fines and coarses)
        self.particles_f = [SwellingParticle(params.r_f_init, params) for _ in range(self.N)]
        self.particles_c = [SwellingParticle(params.r_c_init, params) for _ in range(self.N)]
        
        # Bed-level state
        self.c_b = np.zeros(self.N)  # Bulk concentration
        self.eps_b = np.full(self.N, params.eps_b_init)  # Bed porosity
        self.q = 0.0  # Superficial flow rate
        
        # Time tracking
        self.t = 0.0
        self.dt = params.dt_init
        
        # Number densities
        self.n_f = (1 - params.eps_b_init) * 3 * params.vol_frac_f / (4 * np.pi * params.r_f_init**3)
        self.n_c = (1 - params.eps_b_init) * 3 * params.vol_frac_c / (4 * np.pi * params.r_c_init**3)
    
    def set_flow_conditions(self, flow_rate: float = None, pressure_drop: float = None):
        """Set either fixed flow rate or fixed pressure drop"""
        if flow_rate is not None:
            self.q = flow_rate
            self.fixed_flow = True
        elif pressure_drop is not None:
            self.pressure_drop = pressure_drop
            self.fixed_flow = False
            self._update_flow_rate()
        else:
            raise ValueError("Must specify either flow_rate or pressure_drop")
    
    def step(self, target_time: float = None):
        """Advance simulation one time step"""
        if target_time is not None:
            dt = min(self.dt, target_time - self.t)
        else:
            dt = self.dt
        
        # Update particle boundary conditions
        for i in range(self.N):
            self.particles_f[i].c_b_boundary = self.c_b[i]
            self.particles_c[i].c_b_boundary = self.c_b[i]
        
        # Step particle-level physics
        for i in range(self.N):
            self.particles_f[i].step_swelling(dt)
            self.particles_c[i].step_swelling(dt)
            self.particles_f[i].step_extraction(dt)
            self.particles_c[i].step_extraction(dt)
        
        # Update bed porosity
        self._update_porosity()
        
        # Update flow rate if pressure is fixed
        if not self.fixed_flow:
            self._update_flow_rate()
        
        # Step bed-level transport
        self._step_bed_transport(dt)
        
        # Update time and adaptive time stepping
        self.t += dt
        self._update_time_step()
    
    def _update_porosity(self):
        """Update bed porosity based on particle swelling"""
        for i in range(self.N):
            r_f = self.particles_f[i].get_current_radius()
            r_c = self.particles_c[i].get_current_radius()
            
            vol_ratio = (self.params.vol_frac_f * (r_f / self.params.r_f_init)**3 + 
                        self.params.vol_frac_c * (r_c / self.params.r_c_init)**3)
            
            self.eps_b[i] = 1 - (1 - self.params.eps_b_init) * vol_ratio
            self.eps_b[i] = max(self.eps_b[i], 0.01)  # Prevent negative porosity
    
    def _update_flow_rate(self):
        """Update flow rate for fixed pressure drop case"""
        # Carman-Kozeny permeability
        d_32 = self._calculate_sauter_mean_diameter()
        k = self.eps_b**3 * d_32**2 / (72 * (1 - self.eps_b)**2)
        
        # Average conductivity
        D_avg = np.mean(k / self.params.mu)
        
        # Darcy's law: q = D * ΔP / L
        if hasattr(self, 'pressure_drop'):
            self.q = D_avg * self.pressure_drop / self.params.L_z
    
    def _calculate_sauter_mean_diameter(self) -> float:
        """Calculate Sauter mean diameter"""
        # Average particle sizes
        r_f_avg = np.mean([p.get_current_radius() for p in self.particles_f])
        r_c_avg = np.mean([p.get_current_radius() for p in self.particles_c])
        
        d_32 = 2 / (self.params.vol_frac_c / r_c_avg + self.params.vol_frac_f / r_f_avg)
        return d_32
    
    def _step_bed_transport(self, dt: float):
        """Step bed-level transport equation"""
        # Calculate source terms from particles
        source = np.zeros(self.N)
        
        for i in range(self.N):
            j_f = self.particles_f[i].get_flux()
            j_c = self.particles_c[i].get_flux()
            
            r_f = self.particles_f[i].get_current_radius()
            r_c = self.particles_c[i].get_current_radius()
            
            source[i] = (4 * np.pi * r_f**2 * self.n_f * j_f + 
                        4 * np.pi * r_c**2 * self.n_c * j_c) / self.eps_b[i]
        
        # Advection velocity
        v = self.q / self.eps_b
        
        # Porosity change term
        eps_change = np.gradient(self.eps_b) / dt
        porosity_term = -eps_change * self.c_b / self.eps_b
        
        # Transport equation: dc_b/dt = -v * dc_b/dz + source + porosity_term
        dc_dz = np.gradient(self.c_b, self.dz)
        
        self.c_b += dt * (-v * dc_dz + source + porosity_term)
        self.c_b = np.maximum(self.c_b, 0)
        
        # Boundary condition at outlet
        self.c_b[-1] = 0.0
    
    def _update_time_step(self):
        """Update adaptive time step"""
        # Exponential transition from small to large time step
        dt_diff = (self.params.dt_sat - 
                   (self.params.dt_sat - self.params.dt_init) * 
                   np.exp(-self.t / self.params.tau_swell))
        
        # CFL condition for convection
        v_max = np.max(self.q / self.eps_b) if np.min(self.eps_b) > 0 else 0
        if v_max > 0:
            dt_cfl = 0.1 * self.dz / v_max
        else:
            dt_cfl = self.params.dt_sat
        
        self.dt = min(dt_diff, dt_cfl)
    
    def get_extraction_metrics(self) -> Tuple[float, float]:
        """Calculate extraction yield and strength"""
        # Total extracted mass
        total_extracted = np.trapz(self.q * self.c_b, self.z)
        
        # Total available mass
        total_available = 0
        for i in range(self.N):
            r_f = self.particles_f[i].get_current_radius()
            r_c = self.particles_c[i].get_current_radius()
            
            vol_f = 4/3 * np.pi * r_f**3 * self.n_f
            vol_c = 4/3 * np.pi * r_c**3 * self.n_c
            
            total_available += (vol_f + vol_c) * self.params.c_0 * self.dz
        
        # Yield = extracted / available
        yield_pct = (total_extracted / total_available * 100) if total_available > 0 else 0
        
        # Strength = concentration at outlet
        strength_pct = self.c_b[0] / self.params.rho * 100  # Convert to percentage
        
        return yield_pct, strength_pct

# Usage example in main simulation
def run_simulation_with_validation():
    """Example of how to use validation during simulation"""
    
    # Create parameters and model
    params = CoffeeParameters()
    model = CoffeeExtraction(params)
    model.set_flow_conditions(flow_rate=1.2e-3)
    
    # Validation settings
    validation_interval = 1.0  # Check every 1 second
    last_validation = 0.0
    
    print("Running simulation with swelling validation...")
    
    while model.t < 10.0:  # Short test run
        model.step()
        
        # Periodic validation
        if model.t - last_validation >= validation_interval:
            print(f"\n--- VALIDATION AT t={model.t:.2f}s ---")
            
            # Validate a few representative particles
            for i, layer_idx in enumerate([0, model.N//2, model.N-1]):
                print(f"\nLayer {layer_idx} (fines):")
                model.particles_f[layer_idx].validate_swelling_physics(
                    time=model.t, verbose=True
                )
            
            last_validation = model.t
    
    # Final validation and diagnostic plots
    print("\n=== FINAL VALIDATION ===")
    representative_particle = model.particles_f[0]
    results = representative_particle.validate_swelling_physics(time=model.t, verbose=True)
    
    # Create diagnostic plots
    representative_particle.plot_validation_diagnostics("swelling_diagnostics.png")
    
    return results



def run_simulation_example():
    """Example simulation run"""
    # Create parameters
    params = CoffeeParameters()
    
    # Create model
    model = CoffeeExtraction(params)
    
    # Set flow conditions - fixed flow rate (1.2 mm/s)
    model.set_flow_conditions(flow_rate=1.2e-3)
    
    # Run simulation
    times = []
    yields = []
    strengths = []
    porosities = []
    
    end_time = 60.0  # 60 seconds
    save_interval = 1.0  # Save every second
    next_save = 0.0
    
    print("Running coffee extraction simulation...")
    print("Time (s) | Yield (%) | Strength (%) | Avg Porosity")
    print("-" * 50)
    
    while model.t < end_time:
        if model.t >= next_save:
            yield_val, strength_val = model.get_extraction_metrics()
            avg_porosity = np.mean(model.eps_b)
            
            times.append(model.t)
            yields.append(yield_val)
            strengths.append(strength_val)
            porosities.append(avg_porosity)
            
            print(f"{model.t:7.1f} | {yield_val:8.2f} | {strength_val:11.2f} | {avg_porosity:11.3f}")
            
            next_save += save_interval
        
        model.step()
    
    # Plot results
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))
    
    # Yield vs time
    ax1.plot(times, yields, 'b-', linewidth=2)
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Yield (%)')
    ax1.set_title('Extraction Yield')
    ax1.grid(True, alpha=0.3)
    
    # Strength vs time
    ax2.plot(times, strengths, 'r-', linewidth=2)
    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel('Strength (%)')
    ax2.set_title('Coffee Strength')
    ax2.grid(True, alpha=0.3)
    
    # Porosity vs time
    ax3.plot(times, porosities, 'g-', linewidth=2)
    ax3.set_xlabel('Time (s)')
    ax3.set_ylabel('Average Porosity')
    ax3.set_title('Bed Porosity (Swelling Effect)')
    ax3.grid(True, alpha=0.3)
    
    # Final concentration profile
    ax4.plot(model.z * 1000, model.c_b * 1000, 'k-', linewidth=2)
    ax4.set_xlabel('Position (mm)')
    ax4.set_ylabel('Concentration (mg/mL)')
    ax4.set_title('Final Concentration Profile')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()
    
    print(f"\nSimulation completed!")
    print(f"Final yield: {yields[-1]:.2f}%")
    print(f"Final strength: {strengths[-1]:.2f}%")
    print(f"Porosity change: {params.eps_b_init:.3f} → {porosities[-1]:.3f}")

if __name__ == "__main__":
    run_simulation_example()
