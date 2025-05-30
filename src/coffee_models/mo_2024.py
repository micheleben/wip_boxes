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
        """Build coefficient matrix for swelling equation"""
        N = self.N_p
        A = np.zeros((N, N))
        
        # Interior points
        for i in range(1, N-1):
            D_eff = self.params.D_w * (1 - self.c_w[i])
            
            # Central differences for Laplacian in spherical coordinates
            # ∇²c_w = (1/R²)d/dR(R² dc_w/dR)
            coeff_center = -2 * D_eff * dt / self.dR**2
            coeff_plus = D_eff * dt / self.dR**2 * (1 + self.dR / (2 * self.R[i]))
            coeff_minus = D_eff * dt / self.dR**2 * (1 - self.dR / (2 * self.R[i]))
            
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
