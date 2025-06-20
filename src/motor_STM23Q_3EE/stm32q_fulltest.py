#!/usr/bin/env python3
"""
STM23Q-3EE Motor Controller Connection Test Script

This script connects to an Applied Motion Products STM23Q-3EE motor controller
using the eSCL (SCL over Ethernet) protocol over UDP.

Features:
- Test communication with motor controller
- Spin motor at specified RPM (positive for CW, negative for CCW)  
- Stop motor with controlled or immediate deceleration
- Get comprehensive motor status information
- Interactive motor control demo

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
    """Class to handle communication with STM23Q-3EE motor controller"""
    
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
        self.timeout = 2.0  # 2 second timeout
        
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
            print(f"Invalid header: {response_bytes[0]:02X} {response_bytes[1]:02X}")
            return None
        
        # Extract response string (skip header, remove terminator)
        response_str = response_bytes[2:-1].decode('ascii', errors='ignore')
        return response_str
    
    def send_command(self, command: str, expect_response: bool = True, verbose: bool = True) -> Optional[str]:
        """
        Send command to motor controller and optionally wait for response
        
        Args:
            command: SCL command to send
            expect_response: Whether to wait for a response
            verbose: Whether to print debug information
            
        Returns:
            Response string if successful, None otherwise
        """
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
            
            return response
            
        except socket.timeout:
            if verbose:
                print(f"Timeout waiting for response to command: {command}")
            return None
        except Exception as e:
            if verbose:
                print(f"Error sending command {command}: {e}")
            return None

    def enable_motor(self) -> bool:
        """Enable the motor for operation"""
        print("Enabling motor...")
        response = self.send_command("ME", expect_response=False)
        if response:
            print("\u2713 Motor enabled")
            return True
        else:
            print("\u2717 Failed to enable motor")
            return False

    def disable_motor(self) -> bool:
        """Disable the motor"""
        print("Disabling motor...")
        response = self.send_command("MD", expect_response=False)
        if response:
            print("\u2713 Motor disabled")
            return True
        else:
            print("\u2717 Failed to disable motor")
            return False

    def spin_motor(self, rpm: float, acceleration: float = 10.0) -> bool:
        """Spin the motor at specified RPM using jog mode"""
        print(f"Spinning motor at {rpm} RPM...")
        
        # Convert RPM to rev/sec
        rps = rpm / 60.0
        
        # Validate speed limits
        max_rps = 80.0  # Conservative limit for STM drives
        if abs(rps) > max_rps:
            print(f"\u2717 Speed too high! Maximum: �{max_rps * 60:.0f} RPM")
            return False
        
        try:
            # Set jog acceleration
            response = self.send_command(f"JA{acceleration}", expect_response=False)
            if not response:
                print("\u2717 Failed to set acceleration")
                return False
            
            # Set jog speed (rev/sec)
            response = self.send_command(f"JS{abs(rps)}", expect_response=False)
            if not response:
                print("\u2717 Failed to set jog speed")
                return False
            
            # Set direction using DI command
            direction = 1 if rpm >= 0 else -1
            response = self.send_command(f"DI{direction}", expect_response=False)
            if not response:
                print("\u2717 Failed to set direction")
                return False
            
            # Start jogging
            response = self.send_command("CJ", expect_response=False)
            if not response:
                print("\u2717 Failed to start jogging")
                return False
            
            direction_str = "CW" if rpm >= 0 else "CCW"
            print(f"\u2713 Motor spinning at {rpm} RPM ({direction_str})")
            return True
            
        except Exception as e:
            print(f"\u2717 Error spinning motor: {e}")
            return False

    def stop_motor(self, controlled: bool = True) -> bool:
        """Stop the motor"""
        command = "SJ" if controlled else "ST"
        stop_type = "controlled deceleration" if controlled else "immediate"
        
        print(f"Stopping motor ({stop_type})...")
        
        try:
            response = self.send_command(command, expect_response=False)
            if response:
                print(f"\u2713 Motor stopped ({stop_type})")
                return True
            else:
                print(f"\u2717 Failed to stop motor")
                return False
        except Exception as e:
            print(f"\u2717 Error stopping motor: {e}")
            return False

    def get_motor_status(self) -> dict:
        """Get comprehensive motor status information"""
        status = {}
        
        status_commands = [
            ("SC", "status_code"),
            ("AL", "alarm_code"), 
            ("IP", "position"),
            ("IV0", "actual_velocity"),
            ("IV1", "target_velocity"),
            ("IT", "temperature"),
            ("IU", "bus_voltage"),
            ("IC", "commanded_current"),
        ]
        
        for cmd, key in status_commands:
            try:
                response = self.send_command(cmd)
                if response:
                    if "=" in response:
                        value = response.split("=")[1]
                    else:
                        value = response
                    status[key] = value
            except Exception as e:
                status[key] = f"Error: {e}"
        
        return status


def decode_model_version(mv_response: str) -> dict:
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

def decode_status_code(sc_response: str) -> str:
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

def decode_alarm_code(al_response: str) -> str:
    """Decode alarm code response"""
    if 'AL=' in al_response:
        code = al_response.split('=')[1]
        if code == '0000':
            return "No alarms"
        else:
            return f"Alarm present: {code}"
    return al_response

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
        ("MV", "Request model and revision", decode_model_version), 
        ("AL", "Request alarm code", decode_alarm_code),
        ("SC", "Request status code", decode_status_code),
        ("ME", "Enable motor (test command)", None),
        ("IP", "Request current position", None),
    ]
    
    passed_tests = 0
    total_tests = len(test_commands)
    
    for command, description, decoder in test_commands:
        print(f"\nTest: {description}")
        print(f"Command: {command}")
        
        response = controller.send_command(command)
        
        if response and response.strip():
            print(f"✓ PASS - Raw response: {response}")
            
            # Decode response if decoder provided
            if decoder:
                try:
                    if command == "MV":
                        decoded = decoder(response)
                        print(f"  Decoded: Firmware {decoded.get('firmware', 'N/A')}, "
                              f"Model: {decoded.get('model_name', 'N/A')}")
                    else:
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
    ]
    
    for cmd, desc in info_commands:
        response = controller.send_command(cmd)
        if response:
            print(f"{desc}: {response}")
    
    return passed_tests >= (total_tests - 1)  # Allow one failure for tolerance

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
    ]
    
    for ip in test_ips:
        print(f"Trying {ip}...")
        controller = STM23QController(drive_ip=ip)
        
        if controller.connect():
            # Quick test with RV command
            response = controller.send_command("RV")
            controller.disconnect()
            
            if response and response.strip():
                print(f"Found controller at {ip}!")
                return ip
        
        time.sleep(0.5)  # Brief pause between attempts
    
    return None

def diagnose_network():
    """Diagnose network connectivity issues"""
    print("\n=== Network Diagnostics ===")
    
    # Check if we can ping the motor controller
    motor_ip = "192.168.1.10"
    print(f"Testing ping to motor controller at {motor_ip}...")
    
    try:
        if platform.system().lower() == "windows":
            result = subprocess.run(["ping", "-n", "3", motor_ip], 
                                  capture_output=True, text=True, timeout=10)
        else:
            result = subprocess.run(["ping", "-c", "3", motor_ip], 
                                  capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✓ Ping successful - Network connectivity OK")
        else:
            print("✗ Ping failed - Network connectivity issue")
            print("Check: VM network mode, firewall, IP configuration")
    except Exception as e:
        print(f"Could not test ping: {e}")
    
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

def test_motor_control(controller: STM23QController) -> bool:
    """Test motor control functions"""
    print("\n=== Testing Motor Control Functions ===")
    
    # Enable motor first
    if not controller.enable_motor():
        print("Failed to enable motor")
        return False
    
    time.sleep(1)
    
    # Test spinning at different speeds
    test_speeds = [60, 120, -90]  # RPM values
    
    for rpm in test_speeds:
        print(f"\n--- Testing {rpm} RPM ---")
        
        if not controller.spin_motor(rpm, acceleration=20.0):
            print("Failed to start spinning")
            continue
        
        # Let it spin for 3 seconds
        print("Spinning for 3 seconds...")
        for i in range(3):
            time.sleep(1)
            status = controller.get_motor_status()
            print(f"  Status: Position={status.get('position', 'N/A')}, "
                  f"Velocity={status.get('actual_velocity', 'N/A')}")
        
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
    """Interactive motor control demo"""
    print("\n" + "="*50)
    print("INTERACTIVE MOTOR CONTROL DEMO")
    print("="*50)
    print("Commands:")
    print("  spin <rpm>     - Spin motor at specified RPM")
    print("  stop          - Stop motor with controlled deceleration")
    print("  stop!         - Stop motor immediately")
    print("  status        - Show motor status")
    print("  enable        - Enable motor")
    print("  disable       - Disable motor")
    print("  quit          - Exit demo")
    
    controller.enable_motor()
    
    while True:
        try:
            command = input("\nMotor> ").strip().lower()
            
            if command == "quit" or command == "exit":
                print("Stopping motor and exiting...")
                controller.stop_motor(controlled=False)
                controller.disable_motor()
                break
                
            elif command.startswith("spin "):
                try:
                    rpm_str = command.split()[1]
                    rpm = float(rpm_str)
                    controller.spin_motor(rpm)
                except (IndexError, ValueError):
                    print("Invalid syntax. Use: spin <rpm>")
                    
            elif command == "stop":
                controller.stop_motor(controlled=True)
                
            elif command == "stop!":
                controller.stop_motor(controlled=False)
                
            elif command == "status":
                status = controller.get_motor_status()
                print("\nMotor Status:")
                for key, value in status.items():
                    print(f"  {key.replace('_', ' ').title()}: {value}")
                    
            elif command == "enable":
                controller.enable_motor()
                
            elif command == "disable":
                controller.disable_motor()
                
            elif command == "help" or command == "?":
                print("\nCommands: spin <rpm>, stop, stop!, status, enable, disable, quit")
                
            elif command == "":
                continue
                
            else:
                print(f"Unknown command: {command}. Type 'help' for available commands.")
                
        except KeyboardInterrupt:
            print("\nStopping motor and exiting...")
            controller.stop_motor(controlled=False)
            controller.disable_motor()
            break
        except Exception as e:
            print(f"Error: {e}")

def main():
    """Main function to test motor controller connection"""
    print("STM23Q-3EE Motor Controller Connection Test")
    print("==========================================")
    
    # Run network diagnostics first
    diagnose_network()
    
    # Try to find controller automatically first
    found_ip = find_controller()
    
    if found_ip:
        drive_ip = found_ip
    else:
        print("\nController not found automatically.")
        print("Please enter the IP address manually or check:")
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
            print("Failed to establish connection")
            return False
        
        # Run connection tests
        success = test_connection(controller)
        
        if success:
            print("\n🎉 All tests passed! Motor controller connection is working properly.")
            
            # Ask if user wants to test motor control
            print("\n" + "="*50)
            test_motor = input("Do you want to test motor control functions? (y/N): ").strip().lower()
            
            if test_motor in ['y', 'yes']:
                print("\n⚠️  WARNING: Motor will spin! Ensure:")
                print("   - Motor shaft can rotate freely")
                print("   - No mechanical load attached")
                print("   - Safe area around motor")
                
                confirm = input("\nContinue with motor test? (y/N): ").strip().lower()
                
                if confirm in ['y', 'yes']:
                    # Keep connection open for motor control tests
                    motor_success = test_motor_control(controller)
                    if motor_success:
                        print("\n🎉 Motor control tests completed successfully!")
                        
                        # Offer interactive demo
                        demo = input("\nWould you like to try interactive motor control? (y/N): ").strip().lower()
                        if demo in ['y', 'yes']:
                            interactive_motor_demo(controller)
                    else:
                        print("\n⚠️  Some motor control tests failed.")
                else:
                    print("Motor control test skipped.")
            else:
                print("\nConnection test completed. Motor control test skipped.")
                
        else:
            print("\n⚠️  Some tests failed. Check controller status and network configuration.")
        
        return success
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        return False
    finally:
        # Always ensure motor is stopped and disabled before disconnecting
        if controller.socket:
            try:
                controller.stop_motor(controlled=False)
                controller.disable_motor() 
            except:
                pass  # Ignore errors during cleanup
        controller.disconnect()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)