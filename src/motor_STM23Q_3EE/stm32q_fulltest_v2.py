#!/usr/bin/env python3
"""
STM23Q-3EE Motor Controller - Improved Version with Proper Command Sequencing

This improved version addresses:
- Proper acknowledgment checking
- Complete motor setup sequence
- Error handling and alarm checking
- Reliable command execution with timeouts
- Status monitoring during operations

Based on the Host Command Reference documentation for Applied Motion Products drives.
"""

import socket
import time
import sys
import subprocess
import platform
from typing import Optional, Tuple, List

class STM23QController:
    """Improved class to handle communication with STM23Q-3EE motor controller"""
    
    # Default IP addresses based on rotary switch settings
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
        """Initialize the controller connection"""
        self.drive_ip = drive_ip
        self.drive_port = drive_port
        self.local_port = local_port
        self.socket = None
        self.timeout = 3.0  # 3 second timeout
        self.is_initialized = False
        
    def connect(self) -> bool:
        """Establish UDP connection to the motor controller"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(self.timeout)
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
        """Create eSCL UDP packet according to protocol specification"""
        packet = bytearray()
        packet.extend([0x00, 0x07])  # eSCL header
        packet.extend(command.encode('ascii'))  # Command
        packet.append(0x0D)  # Carriage return terminator
        return bytes(packet)
    
    def _parse_response(self, response_bytes: bytes) -> Optional[str]:
        """Parse response packet from motor controller"""
        if len(response_bytes) < 3:
            return None
        if response_bytes[0] != 0x00 or response_bytes[1] != 0x07:
            print(f"Invalid header: {response_bytes[0]:02X} {response_bytes[1]:02X}")
            return None
        response_str = response_bytes[2:-1].decode('ascii', errors='ignore')
        return response_str
    
    def send_command(self, command: str, expect_response: bool = True, 
                    expected_ack: str = None, verbose: bool = False) -> Optional[str]:
        """
        Send command with proper acknowledgment checking
        
        Args:
            command: SCL command to send
            expect_response: Whether to wait for a response
            expected_ack: Expected acknowledgment ('*' for buffered, '%' for immediate)
            verbose: Whether to print debug information
        """
        if not self.socket:
            print("Not connected to motor controller")
            return None
        
        try:
            packet = self._create_packet(command)
            if verbose:
                print(f"Sending: {command}")
            
            self.socket.sendto(packet, (self.drive_ip, self.drive_port))
            
            if not expect_response:
                return "OK"
            
            # Wait for response
            response_bytes, addr = self.socket.recvfrom(1024)
            response = self._parse_response(response_bytes)
            
            if verbose and response:
                print(f"Response: {response}")
            
            # Check for errors
            if response and response.startswith('?'):
                print(f"Command error for '{command}': {response}")
                return None
            
            # Check expected acknowledgment
            if expected_ack and response != expected_ack:
                if not (response and ('=' in response)):  # Allow value responses
                    print(f"Unexpected response for '{command}': expected '{expected_ack}', got '{response}'")
                    return None
            
            return response
            
        except socket.timeout:
            print(f"Timeout waiting for response to command: {command}")
            return None
        except Exception as e:
            print(f"Error sending command {command}: {e}")
            return None

    def check_alarms(self) -> bool:
        """Check for drive alarms and clear them if found"""
        response = self.send_command("AL")
        if not response:
            return False
        
        if '=' in response:
            alarm_code = response.split('=')[1]
            if alarm_code != '0000':
                print(f"⚠️  Drive alarm detected: {alarm_code}")
                # Try to reset alarms
                reset_response = self.send_command("AR", expected_ack="%")
                if reset_response:
                    print("✓ Alarms cleared")
                    time.sleep(0.5)  # Allow time for reset
                    return True
                else:
                    print("✗ Failed to clear alarms")
                    return False
        return True

    def get_status(self) -> dict:
        """Get comprehensive drive status"""
        status = {}
        
        # Get alarm code
        response = self.send_command("AL")
        if response and '=' in response:
            status['alarm_code'] = response.split('=')[1]
            status['has_alarms'] = status['alarm_code'] != '0000'
        
        # Get status code
        response = self.send_command("SC")
        if response and '=' in response:
            status['status_code'] = response.split('=')[1]
        
        # Get position
        response = self.send_command("IP")
        if response and '=' in response:
            status['position'] = int(response.split('=')[1])
        
        # Get actual velocity
        response = self.send_command("IV0")
        if response and '=' in response:
            status['actual_velocity_rpm'] = int(response.split('=')[1])
        
        # Get temperature
        response = self.send_command("IT")
        if response and '=' in response:
            status['temperature_c'] = float(response.split('=')[1]) / 10.0
        
        # Get bus voltage
        response = self.send_command("IU")
        if response and '=' in response:
            status['bus_voltage_v'] = float(response.split('=')[1]) / 10.0
            
        return status

    def initialize_motor(self, current_amps: float = 3.0, microsteps_per_rev: int = 25600) -> bool:
        """
        Complete motor initialization sequence
        
        Args:
            current_amps: Motor running current in amps
            microsteps_per_rev: Microstep resolution (default 25600 = 128 microsteps/step)
        """
        print("=== Initializing Motor ===")
        
        # Check for alarms first
        if not self.check_alarms():
            print("✗ Cannot initialize - drive has alarms")
            return False
        
        # Motor setup sequence
        setup_commands = [
            # Basic motor parameters
            ("MD", "%", "Disable motor for setup"),
            (f"CC{current_amps}", "*", f"Set running current to {current_amps}A"),
            (f"CI{current_amps/2}", "*", f"Set idle current to {current_amps/2}A"),
            ("CD1.0", "*", "Set idle current delay to 1.0s"),
            (f"EG{microsteps_per_rev}", "*", f"Set resolution to {microsteps_per_rev} steps/rev"),
            
            # Motion parameters for jogging
            ("AC20", "*", "Set acceleration to 20 rev/s²"),
            ("DE20", "*", "Set deceleration to 20 rev/s²"),
            ("AM50", "*", "Set max acceleration to 50 rev/s²"),
            ("VM10", "*", "Set max velocity to 10 rev/s"),
            
            # Jog parameters
            ("JA10", "*", "Set jog acceleration to 10 rev/s²"),
            ("JL10", "*", "Set jog deceleration to 10 rev/s²"),
            ("JS1.0", "*", "Set default jog speed to 1 rev/s"),
            
            # Set control mode to commanded velocity (jog mode)
            ("CM10", "*", "Set control mode to commanded velocity"),
            
            # Enable motor
            ("ME", "%", "Enable motor"),
        ]
        
        for command, expected_ack, description in setup_commands:
            print(f"  {description}...")
            response = self.send_command(command, expected_ack=expected_ack)
            if not response:
                print(f"✗ Failed: {description}")
                return False
            time.sleep(0.1)  # Small delay between commands
        
        # Verify motor is enabled and ready
        status = self.get_status()
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
        
        response = self.send_command("ME", expected_ack="%")
        if response:
            print("✓ Motor enabled")
            return True
        else:
            print("✗ Failed to enable motor")
            return False

    def disable_motor(self) -> bool:
        """Disable the motor"""
        response = self.send_command("MD", expected_ack="%")
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
        if not self.check_alarms():
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
            self.send_command("SJ", expected_ack="%")
            time.sleep(0.2)
            
            # Set jog parameters in sequence
            commands = [
                (f"JA{acceleration}", "*", "Set jog acceleration"),
                (f"JL{acceleration}", "*", "Set jog deceleration"),
                (f"JS{rps}", "*", "Set jog speed"),
                (f"DI{direction}", "*", "Set direction"),
            ]
            
            for command, expected_ack, description in commands:
                response = self.send_command(command, expected_ack=expected_ack)
                if not response:
                    print(f"✗ Failed to {description.lower()}")
                    return False
                time.sleep(0.05)  # Small delay between commands
            
            # Start jogging
            response = self.send_command("CJ", expected_ack="*")
            if not response:
                print("✗ Failed to start jogging")
                return False
            
            # Wait a moment and verify motion started
            time.sleep(0.5)
            status = self.get_status()
            actual_rpm = abs(status.get('actual_velocity_rpm', 0))
            
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
            response = self.send_command(command, expected_ack="%")
            if response:
                # Wait for motor to actually stop
                time.sleep(0.5)
                status = self.get_status()
                actual_rpm = abs(status.get('actual_velocity_rpm', 0))
                
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
        
        response = self.send_command(f"CS{rps}")
        if response and response.startswith("CS="):
            print(f"✓ Speed changed to {new_rpm} RPM")
            return True
        else:
            print(f"✗ Failed to change speed")
            return False

    def get_detailed_status(self) -> dict:
        """Get detailed motor status for monitoring"""
        status = self.get_status()
        
        # Add interpretation of status codes
        alarm_code = status.get('alarm_code', '0000')
        if alarm_code != '0000':
            status['alarm_description'] = self._decode_alarm_code(alarm_code)
        
        return status
    
    def _decode_alarm_code(self, alarm_hex: str) -> str:
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


def test_improved_controller():
    """Test the improved controller functionality"""
    print("STM23Q-3EE Motor Controller - Improved Test")
    print("=" * 50)
    
    # Find or specify controller IP
    controller_ip = input("Enter controller IP (or press Enter for 10.10.10.10): ").strip()
    if not controller_ip:
        controller_ip = "10.10.10.10"
    
    controller = STM23QController(drive_ip=controller_ip)
    
    try:
        # Connect
        if not controller.connect():
            print("Failed to connect")
            return False
        
        # Test basic communication
        print("\n=== Testing Communication ===")
        response = controller.send_command("RV")
        if response:
            print(f"✓ Communication OK - Firmware: {response}")
        else:
            print("✗ Communication failed")
            return False
        
        # Initialize motor
        print(f"\n=== Motor Initialization ===")
        if not controller.initialize_motor(current_amps=2.0):
            print("Failed to initialize motor")
            return False
        
        # Show initial status
        print(f"\n=== Initial Status ===")
        status = controller.get_detailed_status()
        for key, value in status.items():
            print(f"  {key}: {value}")
        
        # Test motor control
        print(f"\n=== Motor Control Test ===")
        test_speeds = [120, -90, 240, 0]  # RPM values, 0 to stop
        
        for rpm in test_speeds:
            if rpm == 0:
                print(f"\n--- Stopping Motor ---")
                if controller.stop_motor():
                    time.sleep(2)
                    status = controller.get_status()
                    print(f"  Final velocity: {status.get('actual_velocity_rpm', 'N/A')} RPM")
            else:
                print(f"\n--- Testing {rpm} RPM ---")
                if controller.spin_motor(rpm, acceleration=15.0):
                    # Let it run for 3 seconds
                    for i in range(3):
                        time.sleep(1)
                        status = controller.get_status()
                        print(f"  t+{i+1}s: Position={status.get('position', 'N/A')}, "
                              f"Velocity={status.get('actual_velocity_rpm', 'N/A')} RPM")
                else:
                    print(f"Failed to start motor at {rpm} RPM")
                    break
        
        print(f"\n✓ Motor control test completed successfully!")
        return True
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        return False
    except Exception as e:
        print(f"Test failed with error: {e}")
        return False
    finally:
        controller.disconnect()


def interactive_motor_control():
    """Interactive motor control with improved commands"""
    print("\n" + "="*60)
    print("INTERACTIVE MOTOR CONTROL - IMPROVED VERSION")
    print("="*60)
    print("Commands:")
    print("  init              - Initialize motor with default settings")
    print("  spin <rpm>        - Spin motor at specified RPM")
    print("  speed <rpm>       - Change speed while running")
    print("  stop              - Stop motor with controlled deceleration")
    print("  stop!             - Stop motor immediately")
    print("  status            - Show detailed motor status")
    print("  enable            - Enable motor")
    print("  disable           - Disable motor")
    print("  quit              - Exit")
    
    controller_ip = input("\nEnter controller IP (or press Enter for 10.10.10.10): ").strip()
    if not controller_ip:
        controller_ip = "10.10.10.10"
    
    controller = STM23QController(drive_ip=controller_ip)
    
    try:
        if not controller.connect():
            print("Failed to connect to controller")
            return
        
        print(f"Connected to {controller_ip}")
        print("Type 'init' to initialize the motor, then use 'spin <rpm>' to test")
        
        while True:
            try:
                command = input("\nMotor> ").strip().lower()
                
                if command in ["quit", "exit"]:
                    print("Stopping motor and exiting...")
                    controller.stop_motor_immediate()
                    break
                
                elif command == "init":
                    current = float(input("Enter motor current in amps (default 2.0): ") or "2.0")
                    controller.initialize_motor(current_amps=current)
                
                elif command.startswith("spin "):
                    try:
                        rpm_str = command.split()[1]
                        rpm = float(rpm_str)
                        controller.spin_motor(rpm)
                    except (IndexError, ValueError):
                        print("Invalid syntax. Use: spin <rpm>")
                
                elif command.startswith("speed "):
                    try:
                        rpm_str = command.split()[1]
                        rpm = float(rpm_str)
                        controller.change_speed_while_running(rpm)
                    except (IndexError, ValueError):
                        print("Invalid syntax. Use: speed <rpm>")
                
                elif command == "stop":
                    controller.stop_motor(controlled=True)
                
                elif command == "stop!":
                    controller.stop_motor_immediate()
                
                elif command == "status":
                    status = controller.get_detailed_status()
                    print("\nDetailed Motor Status:")
                    for key, value in status.items():
                        print(f"  {key.replace('_', ' ').title()}: {value}")
                
                elif command == "enable":
                    controller.enable_motor()
                
                elif command == "disable":
                    controller.disable_motor()
                
                elif command in ["help", "?"]:
                    print("\nCommands: init, spin <rpm>, speed <rpm>, stop, stop!, status, enable, disable, quit")
                
                elif command == "":
                    continue
                
                else:
                    print(f"Unknown command: {command}. Type 'help' for available commands.")
            
            except KeyboardInterrupt:
                print("\nStopping motor and exiting...")
                controller.stop_motor_immediate()
                break
            except Exception as e:
                print(f"Error: {e}")
    
    finally:
        controller.disconnect()


if __name__ == "__main__":
    print("STM23Q-3EE Motor Controller - Improved Version")
    print("Choose test mode:")
    print("1. Automated test")
    print("2. Interactive control")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        success = test_improved_controller()
        sys.exit(0 if success else 1)
    elif choice == "2":
        interactive_motor_control()
    else:
        print("Invalid choice")
        sys.exit(1)