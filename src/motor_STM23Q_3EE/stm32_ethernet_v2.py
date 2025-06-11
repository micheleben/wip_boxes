#!/usr/bin/env python3
"""
STM23Q-3EE Motor Controller Connection Test Script

This script connects to an Applied Motion Products STM23Q-3EE motor controller
using the eSCL (SCL over Ethernet) protocol over UDP.

Based on the Host Command Reference documentation for Applied Motion Products drives.
"""

import socket
import time
import sys
from typing import Optional, Tuple, List192.

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
    
    def send_command(self, command: str, expect_response: bool = True) -> Optional[str]:
        """
        Send command to motor controller and optionally wait for response
        
        Args:
            command: SCL command to send
            expect_response: Whether to wait for a response
            
        Returns:
            Response string if successful, None otherwise
        """
        if not self.socket:
            print("Not connected to motor controller")
            return None
        
        try:
            # Create and send packet
            packet = self._create_packet(command)
            print(f"Sending command: {command}")
            print(f"Packet bytes: {' '.join(f'{b:02X}' for b in packet)}")
            
            self.socket.sendto(packet, (self.drive_ip, self.drive_port))
            
            if not expect_response:
                return "OK"
            
            # Wait for response
            response_bytes, addr = self.socket.recvfrom(1024)
            print(f"Received {len(response_bytes)} bytes from {addr}")
            print(f"Response bytes: {' '.join(f'{b:02X}' for b in response_bytes)}")
            
            # Parse response
            response = self._parse_response(response_bytes)
            if response:
                print(f"Response: {response}")
            
            return response
            
        except socket.timeout:
            print(f"Timeout waiting for response to command: {command}")
            return None
        except Exception as e:
            print(f"Error sending command {command}: {e}")
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
        ("RV", "Request firmware revision"),
        ("MV", "Request model and revision"), 
        ("AL", "Request alarm code"),
        ("MN", "Request model number"),
        ("SC", "Request status code"),
    ]
    
    passed_tests = 0
    total_tests = len(test_commands)
    
    for command, description in test_commands:
        print(f"\nTest: {description}")
        print(f"Command: {command}")
        
        response = controller.send_command(command)
        
        if response and response.strip():
            print(f"✓ PASS - Response: {response}")
            passed_tests += 1
        else:
            print(f"✗ FAIL - No valid response")
    
    print(f"\n=== Test Results: {passed_tests}/{total_tests} tests passed ===")
    return passed_tests == total_tests

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

def main():
    """Main function to test motor controller connection"""
    print("STM23Q-3EE Motor Controller Connection Test")
    print("==========================================")
    
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
        else:
            print("\n⚠️  Some tests failed. Check controller status and network configuration.")
        
        return success
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        return False
    finally:
        controller.disconnect()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)