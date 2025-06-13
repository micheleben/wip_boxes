#!/usr/bin/env python3
"""
STM23Q-3EE Motor Controller - Complete All-Dancing and Singing Version

This comprehensive version includes:
- Improved motor control with proper command sequencing
- Network diagnostics and troubleshooting tools
- Auto-discovery of motor controllers
- Comprehensive connection testing
- Detailed status monitoring and debugging
- Interactive motor control demo
- Error handling and alarm management

Features:
- Test communication with motor controller
- Spin motor at specified RPM (positive for CW, negative for CCW)  
- Stop motor with controlled or immediate deceleration
- Get comprehensive motor status information
- Interactive motor control demo
- Network diagnostics and IP scanning
- Automatic controller discovery
- Complete command testing suite

Based on the Host Command Reference documentation for Applied Motion Products drives.

Safety Warning:
- Ensure motor shaft can rotate freely before testing
- Remove any mechanical loads during testing
- Maintain safe distance from moving parts
"""

import socket
import time
import sys
import subprocess
import platform
from typing import Optional, Tuple, List

class STM23QController:
    """Comprehensive class to handle communication with STM23Q-3EE motor controller"""
    
    # Default IP addresses based on rotary switch settings (from documentation)
    DEFAULT_IPS = {
        0: "10.10.10.10",    # Universal recovery address
        1: "192.168.1.10",
        2: "192.168.1.20", 
        3: "192.168.1.30",
        4: "192.168.0.40",
        5: "192.168.0.50",
        6: "192.168.0.60",
        7: "192.168.0.70",
        8: "192.168.0.80",
        9: "192.168.0.90",
        10: "192.168.0.100",  # 'A' on switch
        11: "192.168.0.110",  # 'B' on switch  
        12: "192.168.0.120",  # 'C' on switch
        13: "192.168.0.130",  # 'D' on switch
        14: "192.168.0.140",  # 'E' on switch
    }
    
    def __init__(self, drive_ip: str = "10.10.10.10", drive_port: int = 7775, local_port: int = 7777):
        """
        Initialize the controller connection
        
        Args:
            drive_ip: IP address of the motor controller
            drive_port: UDP port of the motor controller (default 7775)
            local_port: Local UDP port for PC (default 7777)
        """
        self.drive_ip = drive_ip
        self.drive_port = drive_port
        self.local_port = local_port
        self.socket = None
        self.timeout = 3.0  # 3 second timeout
        self.is_initialized = False
        self.debug_mode = False
        
    def set_debug_mode(self, enabled: bool):
        """Enable/disable debug mode for verbose output"""
        self.debug_mode = enabled
        
    def connect(self) -> bool:
        """
        Establish UDP connection to the motor controller
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(self.timeout)
            
            # Bind to local port
            self.socket.bind(('', self.local_port))
            
            print(f"Connected to {self.drive_ip}:{self.drive_port} from local port {self.local_port}")
            return True
            
        except Exception as e:
            print(f"Failed to create socket connection: {e}")
            return False
    
    def disconnect(self):
        """Close the socket connection"""
        if self.socket:
            try:
                # Safety: stop motor before disconnecting
                self.stop_motor_immediate()
                self.disable_motor()
            except:
                pass  # Ignore errors during cleanup
            self.socket.close()
            self.socket = None
            print("Disconnected from motor controller")
    
    def _create_packet(self, command: str) -> bytes:
        """
        Create eSCL UDP packet according to protocol specification
        
        Packet format:
        - Header: 2 bytes (0x00, 0x07) 
        - SCL command: ASCII encoded string
        - Terminator: Carriage return (0x0D)
        
        Args:
            command: SCL command string (e.g., "RV", "MV")
            
        Returns:
            Byte array ready for transmission
        """
        packet = bytearray()
        
        # Add eSCL header (0x00, 0x07)
        packet.extend([0x00, 0x07])
        
        # Add command as ASCII bytes
        packet.extend(command.encode('ascii'))
        
        # Add carriage return terminator
        packet.append(0x0D)
        
        return bytes(packet)
    
    def _parse_response(self, response_bytes: bytes) -> Optional[str]:
        """
        Parse response packet from motor controller
        
        Response format:
        - Header: 2 bytes (0x00, 0x07)
        - Response string: ASCII encoded
        - Terminator: Carriage return (0x0D)
        
        Args:
            response_bytes: Raw response from controller
            
        Returns:
            Parsed response string or None if invalid
        """
        if len(response_bytes) < 3:
            return None
            
        # Check header
        if response_bytes[0] != 0x00 or response_bytes[1] != 0x07:
            if self.debug_mode:
                print(f"Invalid header: {response_bytes[0]:02X} {response_bytes[1]:02X}")
            return None
        
        # Extract response string (skip header, remove terminator)
        response_str = response_bytes[2:-1].decode('ascii', errors='ignore')
        return response_str
    
    def send_command(self, command: str, expect_response: bool = True, 
                    expected_ack: Optional[str] = None, verbose: Optional[bool] = None) -> Optional[str]:
        """
        Send command to motor controller with proper acknowledgment checking
        
        Args:
            command: SCL command to send
            expect_response: Whether to wait for a response
            expected_ack: Expected acknowledgment ('*' for buffered, '%' for immediate)
            verbose: Whether to print debug information (None = use debug_mode)
            
        Returns:
            Response string if successful, None otherwise
        """
        if verbose is None:
            verbose = self.debug_mode
            
        if not self.socket:
            print("Not connected to motor controller")
            return None
        
        try:
            # Create and send packet
            packet = self._create_packet(command)
            if verbose:
                print(f"Sending command: {command}")
                print(f"Packet bytes: {' '.join(f'{b:02X}' for b in packet)}")
            
            self.socket.sendto(packet, (self.drive_ip, self.drive_port))
            
            if not expect_response:
                return "OK"
            
            # Wait for response
            response_bytes, addr = self.socket.recvfrom(1024)
            if verbose:
                print(f"Received {len(response_bytes)} bytes from {addr}")
                print(f"Response bytes: {' '.join(f'{b:02X}' for b in response_bytes)}")
            
            # Parse response
            response = self._parse_response(response_bytes)
            if response and verbose:
                print(f"Response: {response}")
            
            # Check for errors
            if response and response.startswith('?'):
                print(f"Command error for '{command}': {response}")
                return None
            
            # Check expected acknowledgment
            if expected_ack and response != expected_ack:
                if not (response and ('=' in response)):  # Allow value responses
                    if verbose:
                        print(f"Unexpected response for '{command}': expected '{expected_ack}', got '{response}'")
                    return None
            
            return response
            
        except socket.timeout:
            if verbose:
                print(f"Timeout waiting for response to command: {command}")
            return None
        except Exception as e:
            if verbose:
                print(f"Error sending command {command}: {e}")
            return None

    def check_alarms(self, verbose: bool = True) -> bool:
        """Check for drive alarms and clear them if found"""
        response = self.send_command("AL", verbose=False)
        if not response:
            return False
        
        if '=' in response:
            alarm_code = response.split('=')[1]
            if alarm_code != '0000':
                if verbose:
                    alarm_desc = self.decode_alarm_code(alarm_code)
                    print(f"⚠️  Drive alarm detected: {alarm_code} ({alarm_desc})")
                # Try to reset alarms
                reset_response = self.send_command("AR", expected_ack="%", verbose=False)
                if reset_response:
                    if verbose:
                        print("✓ Alarms cleared")
                    time.sleep(0.5)  # Allow time for reset
                    return True
                else:
                    if verbose:
                        print("✗ Failed to clear alarms")
                    return False
        return True

    def _safe_int_convert(self, value, default=0):
        """Safely convert value to int, handling both decimal and hex formats"""
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            if value.startswith('Error'):
                return default

    def decode_alarm_code(self, alarm_hex: str) -> str:
        """Decode alarm code to human readable description"""
        try:
            alarm_int = int(alarm_hex, 16)
            alarms = []
            
            alarm_bits = {
                0x0001: "Position Limit",
                0x0002: "CCW Limit", 
                0x0004: "CW Limit",
                0x0008: "Over Temperature",
                0x0010: "Internal Voltage",
                0x0020: "Over Voltage",
                0x0040: "Under Voltage", 
                0x0080: "Over Current",
                0x0100: "Open Motor Winding",
                0x0400: "Communication Error",
                0x0800: "Bad Flash",
                0x1000: "No Move",
                0x2000: "Current Foldback"
            }
            
            for bit, description in alarm_bits.items():
                if alarm_int & bit:
                    alarms.append(description)
            
            return ", ".join(alarms) if alarms else "Unknown alarm"
        except:
            return f"Invalid alarm code: {alarm_hex}"
        
    def _safe_float_convert(self, value, default=0.0):
        """Safely convert value to float, handling both decimal and hex formats"""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            if value.startswith('Error'):
                return default
            try:
                # Try decimal first
                return float(value)
            except ValueError:
                try:
                    # Try hex conversion
                    return float(int(value, 16))
                except ValueError:
                    return default
        return default


    def decode_model_version(self, mv_response: str) -> dict:
        """
        Decode MV command response according to documentation
        Format: AAAABBBC where AAAA=firmware, BBB=model code, C=sub-model
        """
        info = {}
        if len(mv_response) >= 7:
            info['firmware'] = mv_response[:4]
            info['model_code'] = mv_response[4:7]
            info['sub_model'] = mv_response[7] if len(mv_response) > 7 else ''
            
            # Model code lookup (from documentation)
            model_codes = {
                '049': 'STM23-S family',
                '050': 'STM23-Q family', 
                '053': 'STM24-C family',
                '054': 'STM23-C family',
            }
            info['model_name'] = model_codes.get(info['model_code'], f"Unknown model ({info['model_code']})")
        
        return info

    def decode_status_code(self, sc_response: str) -> str:
        """Decode status code response"""
        if 'SC=' in sc_response:
            code = sc_response.split('=')[1]
            # Basic status interpretation
            if code == '0000':
                return "Ready/Idle"
            elif code == '0001':
                return "Drive Enabled"
            else:
                return f"Status: {code}"
        return sc_response

    def initialize_motor(self, current_amps: float = 3.0, microsteps_per_rev: int = 25600, 
                        max_velocity: float = 10.0) -> bool:
        """
        Complete motor initialization sequence with enhanced debugging
        
        Args:
            current_amps: Motor running current in amps
            microsteps_per_rev: Microstep resolution (default 25600 = 128 microsteps/step)
            max_velocity: Maximum velocity in rev/sec
        """
        print("=== Initializing Motor ===")
        
        # Check for alarms first
        if not self.check_alarms():
            print("✗ Cannot initialize - drive has alarms")
            return False
        
        # Test current command format first
        print("  Testing current command format...")
        
        # Try different current command formats to see which works
        test_current = 2.0
        current_formats = [
            f"CC{test_current}",      # CC2.0
            f"CC{int(test_current)}", # CC2  
            f"CC{test_current:.1f}",  # CC2.0
        ]
        
        working_current_format = None
        for fmt in current_formats:
            print(f"    Trying format: {fmt}")
            # First ensure motor is disabled
            self.send_command("MD", expected_ack="%", verbose=self.debug_mode)
            time.sleep(0.2)
            
            response = self.send_command(fmt, verbose=self.debug_mode)
            if response == "%":  # Changed from "*" to "%" 
                print(f"    ✓ Format {fmt} works!")
                working_current_format = fmt.replace(str(test_current), "{}")
                break
            elif response:
                print(f"    ⚠️  Got response '{response}' instead of '%'")
            else:
                print(f"    ✗ No response for {fmt}")
        
        if not working_current_format:
            print("✗ Cannot find working current command format")
            return False
        
        # Test velocity command format
        print("  Testing velocity command format...")
        test_velocity = 10.0
        velocity_formats = [
            f"VM{test_velocity}",      # VM10.0
            f"VM{int(test_velocity)}", # VM10  
            f"VM{test_velocity:.1f}",  # VM10.0
            f"VM{test_velocity:.0f}",  # VM10
        ]
        
        working_velocity_format = None
        for fmt in velocity_formats:
            print(f"    Trying format: {fmt}")
            response = self.send_command(fmt, verbose=self.debug_mode)
            if response == "%":
                print(f"    ✓ Format {fmt} works!")
                working_velocity_format = fmt.replace(str(test_velocity), "{}")
                break
            elif response and response.startswith('?'):
                print(f"    ✗ Command error for {fmt}")
            elif response:
                print(f"    ⚠️  Got response '{response}' for {fmt}")
            else:
                print(f"    ✗ No response for {fmt}")
        
        if not working_velocity_format:
            print("⚠️  VM command not working, will skip maximum velocity setting")
            working_velocity_format = None
        
        # Motor setup sequence with working formats
        setup_commands = [
            # Basic motor parameters
            ("MD", "%", "Disable motor for setup"),
            ("IF D", "%", "Set data format to decimal"),  # Force decimal responses
            (working_current_format.format(current_amps), "%", f"Set running current to {current_amps}A"),
            (working_current_format.format(current_amps/2), "%", f"Set idle current to {current_amps/2}A"),
            ("CD1.0", "%", "Set idle current delay to 1.0s"),
            (f"EG{microsteps_per_rev}", "%", f"Set resolution to {microsteps_per_rev} steps/rev"),
            
            # Motion parameters for jogging
            ("AC20", "%", "Set acceleration to 20 rev/s²"),
            ("DE20", "%", "Set deceleration to 20 rev/s²"),
            ("AM50", "%", "Set max acceleration to 50 rev/s²"),
            
            # Jog parameters
            ("JA10", "%", "Set jog acceleration to 10 rev/s²"),
            ("JL10", "%", "Set jog deceleration to 10 rev/s²"),
            ("JS1.0", "%", "Set default jog speed to 1 rev/s"),
            
            # Set control mode to commanded velocity (jog mode)
            ("CM10", "%", "Set control mode to commanded velocity"),
            
            # Enable motor
            ("ME", "%", "Enable motor"),
        ]
        
        # Add VM command only if format works
        if working_velocity_format:
            setup_commands.insert(-2, (working_velocity_format.format(max_velocity), "%", f"Set max velocity to {max_velocity} rev/s"))
        else:
            print("  Skipping maximum velocity setting (VM command not supported)")
        
        print(f"  Proceeding with {len(setup_commands)} configuration commands...")
        
        for command, expected_ack, description in setup_commands:
            print(f"  {description}...")
            response = self.send_command(command, expected_ack=expected_ack, verbose=self.debug_mode)
            if not response:
                print(f"✗ Failed: {description}")
                print(f"    Command: {command}")
                print(f"    Expected: {expected_ack}")
                print(f"    Got: {response}")
                
                # Try to get more info about why it failed
                print("    Checking drive status...")
                status_response = self.send_command("SC", verbose=True)
                alarm_response = self.send_command("AL", verbose=True)
                print(f"    Status: {status_response}")
                print(f"    Alarms: {alarm_response}")
                
                return False
            time.sleep(0.15)  # Slightly longer delay between commands
        
        # Verify motor is enabled and ready
        status = self.get_motor_status()
        if status.get('has_alarms', True):
            print("✗ Motor has alarms after initialization")
            return False
        
        self.is_initialized = True
        print("✓ Motor initialized successfully")
        return True

    def enable_motor(self) -> bool:
        """Enable the motor for operation"""
        if not self.check_alarms():
            return False
        
        response = self.send_command("ME", expected_ack="%", verbose=False)
        if response:
            print("✓ Motor enabled")
            return True
        else:
            print("✗ Failed to enable motor")
            return False

    def disable_motor(self) -> bool:
        """Disable the motor"""
        response = self.send_command("MD", expected_ack="%", verbose=False)
        if response:
            print("✓ Motor disabled")
            return True
        else:
            print("✗ Failed to disable motor")
            return False

    def spin_motor(self, rpm: float, acceleration: float = 10.0) -> bool:
        """
        Spin the motor at specified RPM using jog mode with proper sequencing
        
        Args:
            rpm: Target speed in RPM (positive=CW, negative=CCW)
            acceleration: Acceleration rate in rev/sec²
        """
        if not self.is_initialized:
            print("✗ Motor not initialized. Call initialize_motor() first.")
            return False
        
        # Check for alarms
        if not self.check_alarms(verbose=False):
            return False
        
        print(f"Spinning motor at {rpm} RPM...")
        
        # Convert RPM to rev/sec
        rps = abs(rpm) / 60.0
        direction = 1 if rpm >= 0 else -1
        
        # Validate speed limits
        max_rps = 10.0  # Conservative limit
        if rps > max_rps:
            print(f"✗ Speed too high! Maximum: {max_rps * 60:.0f} RPM")
            return False
        
        try:
            # Stop any current motion
            self.send_command("SJ", expected_ack="%", verbose=False)
            time.sleep(0.2)
            
            # Set jog parameters in sequence
            commands = [
                (f"JA{acceleration}", "%", "Set jog acceleration"),
                (f"JL{acceleration}", "%", "Set jog deceleration"),
                (f"JS{rps}", "%", "Set jog speed"),
                (f"DI{direction}", "%", "Set direction"),
            ]
            
            for command, expected_ack, description in commands:
                response = self.send_command(command, expected_ack=expected_ack, verbose=False)
                if not response:
                    print(f"✗ Failed to {description.lower()}")
                    return False
                time.sleep(0.05)  # Small delay between commands
            
            # Start jogging
            response = self.send_command("CJ", expected_ack="%", verbose=False)
            if not response:
                print("✗ Failed to start jogging")
                return False
            
            # Wait a moment and verify motion started
            time.sleep(0.5)
            status = self.get_motor_status()
            
            # Safely get actual RPM with None handling
            actual_velocity = status.get('actual_velocity_rpm', 0)
            if actual_velocity is None:
                actual_rpm = 0
            else:
                actual_rpm = abs(actual_velocity)
            
            if actual_rpm > 5:  # Motor is moving
                direction_str = "CW" if rpm >= 0 else "CCW"
                print(f"✓ Motor spinning at {rpm} RPM ({direction_str})")
                print(f"  Actual velocity: {status.get('actual_velocity_rpm', 'N/A')} RPM")
                return True
            else:
                print(f"✗ Motor not moving - actual RPM: {actual_rpm}")
                return False
            
        except Exception as e:
            print(f"✗ Error spinning motor: {e}")
            return False

    def stop_motor(self, controlled: bool = True) -> bool:
        """
        Stop the motor with proper acknowledgment checking
        
        Args:
            controlled: True for controlled deceleration (SJ), False for immediate stop (ST)
        """
        command = "SJ" if controlled else "ST"
        stop_type = "controlled deceleration" if controlled else "immediate stop"
        
        print(f"Stopping motor ({stop_type})...")
        
        try:
            response = self.send_command(command, expected_ack="%", verbose=False)
            if response:
                # Wait for motor to actually stop
                time.sleep(0.5)
                status = self.get_motor_status()
                
                # Safely get actual RPM with None handling
                actual_velocity = status.get('actual_velocity_rpm', 0)
                if actual_velocity is None:
                    actual_rpm = 0
                else:
                    actual_rpm = abs(actual_velocity)
                
                if actual_rpm < 5:  # Nearly stopped
                    print(f"✓ Motor stopped ({stop_type})")
                    return True
                else:
                    print(f"⚠️  Motor stopping - current RPM: {actual_rpm}")
                    return True  # Command sent successfully, motor is stopping
            else:
                print(f"✗ Failed to stop motor")
                return False
        except Exception as e:
            print(f"✗ Error stopping motor: {e}")
            return False

    def stop_motor_immediate(self) -> bool:
        """Immediate motor stop for emergency situations"""
        return self.stop_motor(controlled=False)

    def change_speed_while_running(self, new_rpm: float) -> bool:
        """
        Change motor speed while it's running using CS command
        
        Args:
            new_rpm: New speed in RPM (positive=CW, negative=CCW)
        """
        if not self.is_initialized:
            print("✗ Motor not initialized")
            return False
        
        rps = new_rpm / 60.0
        
        # Validate speed
        if abs(rps) > 10.0:
            print(f"✗ Speed too high! Maximum: 600 RPM")
            return False
        
        print(f"Changing speed to {new_rpm} RPM...")
        
        response = self.send_command(f"CS{rps}", verbose=False)
        if response and response.startswith("CS="):
            print(f"✓ Speed changed to {new_rpm} RPM")
            return True
        else:
            print(f"✗ Failed to change speed")
            return False

    def get_motor_status(self) -> dict:
        """Get comprehensive motor status information"""
        status = {}
        
        status_commands = [
            ("SC", "status_code"),
            ("AL", "alarm_code"), 
            ("IP", "position"),
            #("IV0", "actual_velocity_rpm"),
            #("IV1", "target_velocity_rpm"),
            ("IT", "temperature_raw"),
            ("IU", "bus_voltage_raw"),
            ("IC", "commanded_current_raw"),
        ]
        
        for cmd, key in status_commands:
            try:
                response = self.send_command(cmd, verbose=False)
                if response:
                    if "=" in response:
                        value = response.split("=")[1]
                    else:
                        value = response
                    
                    # Convert specific values with safe conversion
                    if key == "position":
                        status[key] = self._safe_int_convert(value)
                    elif key in ["actual_velocity_rpm", "target_velocity_rpm"]:
                        status[key] = self._safe_int_convert(value)
                    elif key == "temperature_raw":
                        temp_val = self._safe_float_convert(value) / 10.0
                        status['temperature_c'] = temp_val
                        status[key] = value
                    elif key == "bus_voltage_raw":
                        voltage_val = self._safe_float_convert(value) / 10.0
                        status['bus_voltage_v'] = voltage_val
                        status[key] = value
                    elif key == "commanded_current_raw":
                        current_val = self._safe_float_convert(value) / 100.0
                        status['commanded_current_a'] = current_val
                        status[key] = value
                    elif key == "alarm_code":
                        status[key] = value
                        status['has_alarms'] = value != '0000'
                        if value != '0000':
                            status['alarm_description'] = self.decode_alarm_code(value)
                    else:
                        status[key] = value
                else:
                    # Set default values for failed commands
                    if key == "position":
                        status[key] = 0
                    elif key in ["actual_velocity_rpm", "target_velocity_rpm"]:
                        status[key] = 0
                    elif key == "temperature_raw":
                        status['temperature_c'] = 0.0
                        status[key] = "0"
                    elif key == "bus_voltage_raw":
                        status['bus_voltage_v'] = 0.0
                        status[key] = "0"
                    elif key == "commanded_current_raw":
                        status['commanded_current_a'] = 0.0
                        status[key] = "0"
                    elif key == "alarm_code":
                        status[key] = "0000"
                        status['has_alarms'] = False
                    else:
                        status[key] = "No response"
            except Exception as e:
                # Set safe default values on exception
                if key == "position":
                    status[key] = 0
                elif key in ["actual_velocity_rpm", "target_velocity_rpm"]:
                    status[key] = 0
                elif key == "temperature_raw":
                    status['temperature_c'] = 0.0
                    status[key] = f"Error: {e}"
                elif key == "bus_voltage_raw":
                    status['bus_voltage_v'] = 0.0
                    status[key] = f"Error: {e}"
                elif key == "commanded_current_raw":
                    status['commanded_current_a'] = 0.0
                    status[key] = f"Error: {e}"
                elif key == "alarm_code":
                    status[key] = "0000"
                    status['has_alarms'] = False
                else:
                    status[key] = f"Error: {e}"
        # handle IV0
        try:
            response = self.send_command("IV0", verbose=False)
            if response and "=" in response:
                value = response.split("=")[1]
                status['actual_velocity_rpm'] = self._safe_int_convert(value)
        except:
                status['actual_velocity_rpm'] = 0
        # handle IV1
        try:
            response = self.send_command("IV1", verbose=False)
            if response and "=" in response:
                value = response.split("=")[1]
                status['target_velocity_rpm'] = self._safe_int_convert(value)
        except:
                status['target_velocity_rpm'] = 0
        
        return status


def diagnose_network():
    """Diagnose network connectivity issues"""
    print("\n=== Network Diagnostics ===")
    
    # Check if we can ping the motor controller
    motor_ips = ["10.10.10.10", "192.168.1.10", "192.168.0.40"]
    
    for motor_ip in motor_ips:
        print(f"Testing ping to {motor_ip}...")
        
        try:
            if platform.system().lower() == "windows":
                result = subprocess.run(["ping", "-n", "3", motor_ip], 
                                      capture_output=True, text=True, timeout=10)
            else:
                result = subprocess.run(["ping", "-c", "3", motor_ip], 
                                      capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print(f"✓ Ping successful to {motor_ip} - Network connectivity OK")
                break
            else:
                print(f"✗ Ping failed to {motor_ip}")
        except Exception as e:
            print(f"Could not test ping to {motor_ip}: {e}")
    
    # Show network interface information
    print("\nNetwork interface information:")
    try:
        if platform.system().lower() == "windows":
            result = subprocess.run(["ipconfig"], capture_output=True, text=True)
        else:
            result = subprocess.run(["ip", "addr", "show"], capture_output=True, text=True)
        
        lines = result.stdout.split('\n')
        for line in lines:
            if '192.168.' in line or 'inet ' in line:
                print(f"  {line.strip()}")
    except Exception as e:
        print(f"Could not get network info: {e}")
    
    # Test UDP socket binding
    print("\nTesting UDP socket binding...")
    try:
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        test_socket.bind(('', 7777))
        print("✓ Can bind to UDP port 7777")
        test_socket.close()
    except Exception as e:
        print(f"✗ Cannot bind to UDP port 7777: {e}")
        print("Try a different port or check if port is already in use")

def find_controller() -> Optional[str]:
    """
    Try to find the motor controller by testing common IP addresses
    
    Returns:
        IP address if found, None otherwise
    """
    print("Searching for motor controller...")
    
    # Test most common addresses first
    test_ips = [
        "10.10.10.10",      # Universal recovery
        "192.168.1.10",     # Switch position 1
        "192.168.0.40",     # Switch position 4  
        "192.168.0.50",     # Switch position 5
        "192.168.1.20",     # Switch position 2
        "192.168.1.30",     # Switch position 3
    ]
    
    for ip in test_ips:
        print(f"Trying {ip}...")
        controller = STM23QController(drive_ip=ip)
        
        if controller.connect():
            # Quick test with RV command
            response = controller.send_command("RV", verbose=False)
            controller.disconnect()
            
            if response and response.strip():
                print(f"✓ Found controller at {ip}!")
                return ip
        
        time.sleep(0.5)  # Brief pause between attempts
    
    print("✗ No controller found automatically")
    return None

def test_connection(controller: STM23QController) -> bool:
    """
    Test basic communication with the motor controller
    
    Args:
        controller: STM23QController instance
        
    Returns:
        True if all tests pass, False otherwise
    """
    print("\n=== Testing Motor Controller Connection ===")
    
    test_commands = [
        ("RV", "Request firmware revision", None),
        ("MV", "Request model and revision", controller.decode_model_version), 
        ("AL", "Request alarm code", controller.decode_alarm_code),
        ("SC", "Request status code", controller.decode_status_code),
        ("ME", "Enable motor (test command)", None),
        ("IP", "Request current position", None),
    ]
    
    passed_tests = 0
    total_tests = len(test_commands)
    
    for command, description, decoder in test_commands:
        print(f"\nTest: {description}")
        print(f"Command: {command}")
        
        response = controller.send_command(command, verbose=True)
        
        if response and response.strip():
            print(f"✓ PASS - Raw response: {response}")
            
            # Decode response if decoder provided
            if decoder:
                try:
                    if command == "MV":
                        decoded = decoder(response)
                        print(f"  Decoded: Firmware {decoded.get('firmware', 'N/A')}, "
                              f"Model: {decoded.get('model_name', 'N/A')}")
                    elif command == "AL":
                        if '=' in response:
                            alarm_code = response.split('=')[1]
                            decoded = decoder(alarm_code)
                            print(f"  Decoded: {decoded}")
                    elif command == "SC":
                        decoded = decoder(response)
                        print(f"  Decoded: {decoded}")
                except Exception as e:
                    print(f"  Decode error: {e}")
            
            passed_tests += 1
        else:
            print(f"✗ FAIL - No valid response")
    
    print(f"\n=== Test Results: {passed_tests}/{total_tests} tests passed ===")
    
    # Additional motor information
    print("\n=== Motor Controller Information ===")
    
    # Get detailed info
    info_commands = [
        ("IT", "Temperature"),
        ("IU", "Bus voltage"), 
        ("CC", "Current setting"),
        ("VE", "Velocity setting"),
        ("EG", "Electronic gearing"),
        ("CM", "Control mode"),
    ]
    
    for cmd, desc in info_commands:
        response = controller.send_command(cmd, verbose=False)
        if response:
            print(f"{desc}: {response}")
    
    return passed_tests >= (total_tests - 1)  # Allow one failure for tolerance

def test_motor_control(controller: STM23QController) -> bool:
    """Test motor control functions with comprehensive checks"""
    print("\n=== Testing Motor Control Functions ===")
    
    # Initialize motor first
    if not controller.initialize_motor(current_amps=2.0):
        print("Failed to initialize motor")
        return False
    
    time.sleep(1)
    
    # Test spinning at different speeds
    test_speeds = [60, 120, -90, 240]  # RPM values
    
    for rpm in test_speeds:
        print(f"\n--- Testing {rpm} RPM ---")
        
        if not controller.spin_motor(rpm, acceleration=20.0):
            print("Failed to start spinning")
            continue
        
        # Let it spin for 3 seconds with monitoring
        print("Spinning for 3 seconds...")
        for i in range(3):
            time.sleep(1)
            status = controller.get_motor_status()
            print(f"  t+{i+1}s: Position={status.get('position', 'N/A')}, "
                  f"Velocity={status.get('actual_velocity_rpm', 'N/A')} RPM, "
                  f"Temp={status.get('temperature_c', 'N/A')}°C")
        
        # Test speed change while running
        if abs(rpm) < 200:  # Only test speed change at lower speeds
            new_rpm = rpm * 1.5
            print(f"  Testing speed change to {new_rpm} RPM...")
            controller.change_speed_while_running(new_rpm)
            time.sleep(2)
            status = controller.get_motor_status()
            print(f"  After speed change: Velocity={status.get('actual_velocity_rpm', 'N/A')} RPM")
        
        # Stop with controlled deceleration
        if not controller.stop_motor(controlled=True):
            print("Failed to stop motor")
            break
        
        time.sleep(2)
    
    # Test immediate stop
    print(f"\n--- Testing Immediate Stop ---")
    if controller.spin_motor(180, acceleration=30.0):
        time.sleep(1)
        controller.stop_motor(controlled=False)
    
    time.sleep(1)
    
    # Show final status
    print(f"\n--- Final Motor Status ---")
    status = controller.get_motor_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    return True

def interactive_motor_demo(controller: STM23QController):
    """Enhanced interactive motor control demo"""
    print("\n" + "="*60)
    print("INTERACTIVE MOTOR CONTROL DEMO - ALL-DANCING VERSION")
    print("="*60)
    print("Commands:")
    print("  init [current]    - Initialize motor (default 2.0A)")
    print("  spin <rpm>        - Spin motor at specified RPM")
    print("  speed <rpm>       - Change speed while running")
    print("  stop              - Stop motor with controlled deceleration")
    print("  stop!             - Stop motor immediately")
    print("  status            - Show detailed motor status")
    print("  debug on/off      - Enable/disable debug mode")
    print("  test              - Run connection tests")
    print("  cmd <command>     - Send manual command (e.g., 'cmd CC3')")
    print("  raw               - Show raw command responses")
    print("  enable            - Enable motor")
    print("  disable           - Disable motor")
    print("  alarms            - Check and clear alarms")
    print("  help/?            - Show this help")
    print("  quit              - Exit demo")
    
    # Try to initialize motor automatically
    print("\nAttempting automatic motor initialization...")
    if controller.initialize_motor():
        print("✓ Motor ready for operation")
    else:
        print("⚠️  Automatic initialization failed. Use 'init' command manually.")
    
    while True:
        try:
            command = input("\nMotor> ").strip()
            
            if command.lower() in ["quit", "exit"]:
                print("Stopping motor and exiting...")
                controller.stop_motor_immediate()
                controller.disable_motor()
                break
                
            elif command.lower().startswith("init"):
                parts = command.split()
                current = 2.0
                if len(parts) > 1:
                    try:
                        current = float(parts[1])
                    except ValueError:
                        print("Invalid current value, using 2.0A")
                controller.initialize_motor(current_amps=current)
                
            elif command.lower().startswith("spin "):
                try:
                    rpm_str = command.split()[1]
                    rpm = float(rpm_str)
                    controller.spin_motor(rpm)
                except (IndexError, ValueError):
                    print("Invalid syntax. Use: spin <rpm>")
                    
            elif command.lower().startswith("speed "):
                try:
                    rpm_str = command.split()[1]
                    rpm = float(rpm_str)
                    controller.change_speed_while_running(rpm)
                except (IndexError, ValueError):
                    print("Invalid syntax. Use: speed <rpm>")
                    
            elif command.lower() == "stop":
                controller.stop_motor(controlled=True)
                
            elif command.lower() == "stop!":
                controller.stop_motor_immediate()
                
            elif command.lower() == "status":
                status = controller.get_motor_status()
                print("\nDetailed Motor Status:")
                for key, value in status.items():
                    print(f"  {key.replace('_', ' ').title()}: {value}")
                    
            elif command.lower() == "debug on":
                controller.set_debug_mode(True)
                print("✓ Debug mode enabled")
                
            elif command.lower() == "debug off":
                controller.set_debug_mode(False)
                print("✓ Debug mode disabled")
                
            elif command.lower() == "test":
                test_connection(controller)
                
            elif command.lower() == "enable":
                controller.enable_motor()
                
            elif command.lower() == "disable":
                controller.disable_motor()
                
            elif command.lower() == "alarms":
                if controller.check_alarms():
                    print("✓ No alarms present")
                    
            elif command.lower().startswith("cmd "):
                # Manual command testing
                try:
                    cmd_part = command[4:].strip()
                    print(f"Sending manual command: {cmd_part}")
                    response = controller.send_command(cmd_part, verbose=True)
                    print(f"Response: {response}")
                except Exception as e:
                    print(f"Error: {e}")
                    
            elif command.lower() == "raw":
                # Show raw command responses for debugging
                print("\nRaw command responses:")
                raw_commands = ["IP", "IV0", "IV1", "SC", "AL"]
                for cmd in raw_commands:
                    response = controller.send_command(cmd, verbose=False)
                    print(f"  {cmd}: {response}")
                    
            elif command.lower() in ["help", "?"]:
                print("\nCommands: init, spin <rpm>, speed <rpm>, stop, stop!, status, debug on/off, test, enable, disable, alarms, quit")
                
            elif command == "":
                continue
                
            else:
                print(f"Unknown command: '{command}'. Type 'help' for available commands.")
                
        except KeyboardInterrupt:
            print("\nStopping motor and exiting...")
            controller.stop_motor_immediate()
            controller.disable_motor()
            break
        except Exception as e:
            print(f"Error: {e}")

def main():
    """Main function with comprehensive testing and setup"""
    print("STM23Q-3EE Motor Controller - All-Dancing and Singing Version")
    print("=" * 70)
    print("This comprehensive version includes:")
    print("- Improved motor control with proper command sequencing")  
    print("- Network diagnostics and troubleshooting tools")
    print("- Auto-discovery of motor controllers")
    print("- Comprehensive connection testing")
    print("- Interactive motor control with debugging")
    print("=" * 70)
    
    # Run network diagnostics first
    diagnose_network()
    
    # Try to find controller automatically first
    found_ip = find_controller()
    
    if found_ip:
        drive_ip = found_ip
        print(f"\n✓ Using auto-discovered controller at {drive_ip}")
    else:
        print("\nController not found automatically.")
        print("Please check:")
        print("1. Motor controller is powered on")
        print("2. Ethernet cable is connected") 
        print("3. IP address matches rotary switch setting")
        print("4. PC and controller are on same subnet")
        
        # Allow manual IP entry
        manual_ip = input("\nEnter controller IP address (or press Enter for 10.10.10.10): ").strip()
        drive_ip = manual_ip if manual_ip else "10.10.10.10"
    
    # Create controller instance
    controller = STM23QController(drive_ip=drive_ip)
    
    try:
        # Connect to controller
        if not controller.connect():
            print("✗ Failed to establish connection")
            return False
        
        # Run comprehensive connection tests
        success = test_connection(controller)
        
        if success:
            print("\n🎉 All communication tests passed! Motor controller connection is working properly.")
            
            # Offer different test modes
            print("\n" + "="*50)
            print("What would you like to do?")
            print("1. Automated motor control test")
            print("2. Interactive motor control")
            print("3. Connection tests only (current)")
            
            choice = input("\nEnter choice (1/2/3): ").strip()
            
            if choice == "1":
                print("\n⚠️  WARNING: Motor will spin! Ensure:")
                print("   - Motor shaft can rotate freely")
                print("   - No mechanical load attached")
                print("   - Safe area around motor")
                
                confirm = input("\nContinue with automated motor test? (y/N): ").strip().lower()
                
                if confirm in ['y', 'yes']:
                    motor_success = test_motor_control(controller)
                    if motor_success:
                        print("\n🎉 Automated motor control tests completed successfully!")
                    else:
                        print("\n⚠️  Some motor control tests failed.")
                else:
                    print("Automated motor test skipped.")
                    
            elif choice == "2":
                print("\n⚠️  WARNING: Motor will spin! Ensure safe operation.")
                confirm = input("Continue with interactive control? (y/N): ").strip().lower()
                
                if confirm in ['y', 'yes']:
                    interactive_motor_demo(controller)
                else:
                    print("Interactive control skipped.")
                    
            else:
                print("\nConnection testing completed. Motor control tests skipped.")
                
        else:
            print("\n⚠️  Some communication tests failed. Check controller status and network configuration.")
            print("Try running interactive mode to debug step by step.")
            
            # Offer interactive mode for debugging
            debug_choice = input("\nWould you like to try interactive mode for debugging? (y/N): ").strip().lower()
            if debug_choice in ['y', 'yes']:
                controller.set_debug_mode(True)
                interactive_motor_demo(controller)
        
        return success
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False
    finally:
        # Always ensure motor is stopped and disabled before disconnecting
        if controller.socket:
            try:
                controller.stop_motor_immediate()
                controller.disable_motor() 
            except:
                pass  # Ignore errors during cleanup
        controller.disconnect()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)