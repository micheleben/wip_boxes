#!/usr/bin/env python3
"""
STM23Q-3EE Ethernet eSCL Connection Test Script

This script connects to an Applied Motion STM23Q-3EE stepper drive
via Ethernet using eSCL (SCL over Ethernet) protocol and verifies the connection.

The eSCL protocol uses the same SCL commands but over UDP/TCP instead of serial.

Requirements:
- STM23Q-3EE drive connected to network
- Drive configured with known IP address
- Network connectivity to the drive
"""

import socket
import time
import sys
import ipaddress
from contextlib import contextmanager

class STM23QEthernetController:
    def __init__(self, ip_address, port=7775, protocol='UDP', timeout=2):
        """
        Initialize STM23Q Ethernet controller using eSCL protocol
        
        Args:
            ip_address (str): Drive IP address (e.g., '192.168.1.100')
            port (int): Network port (default 7775 for eSCL)
            protocol (str): 'UDP' or 'TCP' 
            timeout (float): Network timeout in seconds
        """
        self.ip_address = ip_address
        self.port = port
        self.protocol = protocol.upper()
        self.timeout = timeout
        self.socket = None
        
        # Validate IP address
        try:
            ipaddress.ip_address(ip_address)
        except ValueError:
            raise ValueError(f"Invalid IP address: {ip_address}")
    
    def connect(self):
        """Establish connection to the drive via Ethernet"""
        try:
            if self.protocol == 'UDP':
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.socket.settimeout(self.timeout)
                print(f"Created UDP socket for {self.ip_address}:{self.port}")
                return True
                
            elif self.protocol == 'TCP':
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(self.timeout)
                self.socket.connect((self.ip_address, self.port))
                print(f"Connected via TCP to {self.ip_address}:{self.port}")
                return True
                
            else:
                raise ValueError(f"Unsupported protocol: {self.protocol}")
                
        except Exception as e:
            print(f"Connection failed: {e}")
            if self.socket:
                self.socket.close()
                self.socket = None
            return False
    
    def send_command(self, command):
        """
        Send an eSCL command to the drive and return the response
        
        Args:
            command (str): SCL command (without carriage return)
            
        Returns:
            str: Response from drive, or None if error
        """
        if not self.socket:
            print("No active connection to drive")
            return None
        
        try:
            # Add carriage return to command (eSCL protocol requirement)
            cmd_with_cr = command + '\r'
            cmd_bytes = cmd_with_cr.encode('ascii')
            
            if self.protocol == 'UDP':
                # Send UDP packet
                self.socket.sendto(cmd_bytes, (self.ip_address, self.port))
                
                # Receive response
                response_bytes, addr = self.socket.recvfrom(1024)
                response = response_bytes.decode('ascii', errors='ignore').strip('\r\n')
                
            elif self.protocol == 'TCP':
                # Send TCP data
                self.socket.sendall(cmd_bytes)
                
                # Receive response
                response_bytes = self.socket.recv(1024)
                response = response_bytes.decode('ascii', errors='ignore').strip('\r\n')
            
            return response if response else None
            
        except socket.timeout:
            print(f"Timeout waiting for response to command '{command}'")
            return None
        except Exception as e:
            print(f"Error sending command '{command}': {e}")
            return None
    
    def ping_drive(self):
        """Test basic network connectivity to the drive IP"""
        import subprocess
        import platform
        
        # Determine ping command based on OS
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        
        try:
            result = subprocess.run(
                ['ping', param, '1', self.ip_address], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def test_connection(self):
        """Run a series of tests to verify drive connection and functionality"""
        print("\n" + "="*60)
        print("STM23Q-3EE Ethernet eSCL Connection Test")
        print("="*60)
        
        # First test network connectivity
        print(f"\nTesting network connectivity to {self.ip_address}...")
        if self.ping_drive():
            print("✅ Network ping successful")
        else:
            print("⚠️  Network ping failed - drive may still respond to eSCL")
        
        # eSCL command tests
        tests = [
            ("Model & Revision", "MV", "Get drive model and firmware version"),
            ("Revision Level", "RV", "Get firmware revision"),
            ("Request Status", "RS", "Get current drive status"),
            ("Alarm Code", "AL", "Check for any alarms"),
            ("Buffer Status", "BS", "Check command buffer status"),
            ("Power-up Mode", "PM", "Get power-up mode setting"),
            ("Protocol Settings", "PR", "Get communication protocol"),
            ("Network Watchdog Status", "ZE", "Get network watchdog enable status"),
            ("Network Timeout Delay", "ZS", "Get network timeout delay"),
        ]
        
        successful_tests = 0
        total_tests = len(tests)
        
        for test_name, command, description in tests:
            print(f"\nTest: {test_name}")
            print(f"Description: {description}")
            print(f"eSCL Command: {command}")
            
            response = self.send_command(command)
            
            if response:
                print(f"Response: {response}")
                
                # Check for error responses
                if response.startswith('?'):
                    print("❌ Command not understood by drive")
                elif '=' in response or response in ['%', '*']:
                    print("✅ Test passed")
                    successful_tests += 1
                else:
                    print("⚠️  Unexpected response format")
                    successful_tests += 0.5  # Partial credit
            else:
                print("❌ No response received")
            
            time.sleep(0.1)  # Small delay between commands
        
        print(f"\n" + "="*60)
        print(f"Test Results: {successful_tests}/{total_tests} tests passed")
        
        if successful_tests >= total_tests * 0.7:  # 70% success rate
            print("✅ eSCL drive connection is working properly!")
            return True
        else:
            print("❌ eSCL drive connection issues detected")
            return False
    
    def get_drive_info(self):
        """Get detailed drive information via eSCL"""
        print("\n" + "-"*50)
        print("Drive Information (via eSCL)")
        print("-"*50)
        
        # Model and version info
        mv_response = self.send_command("MV")
        if mv_response and '=' in mv_response:
            model_info = mv_response.split('=')[1]
            print(f"Model & Version: {model_info}")
            
            # Parse STM response format
            if len(model_info) >= 7:
                firmware = model_info[:4]
                model_code = model_info[4:7]
                sub_model = model_info[7:] if len(model_info) > 7 else ""
                
                print(f"  Firmware: {firmware}")
                print(f"  Model Code: {model_code} (should be 050 for STM23Q)")
                if sub_model:
                    print(f"  Sub-model: {sub_model}")
        
        # Drive status
        status_response = self.send_command("RS")
        if status_response and '=' in status_response:
            status = status_response.split('=')[1]
            print(f"Drive Status: {status}")
            
            # Decode status characters
            status_meanings = {
                'A': 'Alarm present',
                'D': 'Disabled',
                'E': 'Drive Fault', 
                'F': 'Motor moving',
                'H': 'Homing in progress',
                'J': 'Jogging',
                'M': 'Motion in progress',
                'P': 'In position',
                'R': 'Ready (enabled)',
                'S': 'Stopping motion',
                'T': 'Wait Time executing',
                'W': 'Wait Input executing'
            }
            
            print("  Status details:")
            for char in status:
                meaning = status_meanings.get(char, f"Unknown ({char})")
                print(f"    {char}: {meaning}")
        
        # Network-specific information
        print(f"\nNetwork Configuration:")
        print(f"  IP Address: {self.ip_address}")
        print(f"  Port: {self.port}")
        print(f"  Protocol: {self.protocol}")
        
        # Network watchdog settings
        ze_response = self.send_command("ZE")
        if ze_response and '=' in ze_response:
            watchdog_enabled = ze_response.split('=')[1]
            print(f"  Network Watchdog Enabled: {watchdog_enabled}")
        
        zs_response = self.send_command("ZS")
        if zs_response and '=' in zs_response:
            timeout_delay = zs_response.split('=')[1]
            print(f"  Network Timeout Delay: {timeout_delay} ms")
    
    def disconnect(self):
        """Close the connection to the drive"""
        if self.socket:
            self.socket.close()
            self.socket = None
            print(f"\nDisconnected from {self.ip_address}")

def discover_drives_on_network(network_base="192.168.1", start_ip=10, end_ip=50):
    """
    Attempt to discover STM23Q drives on the network
    
    Args:
        network_base (str): Network base (e.g., "192.168.1")
        start_ip (int): Starting IP to scan
        end_ip (int): Ending IP to scan
    """
    print(f"\nScanning for drives on {network_base}.{start_ip}-{end_ip}...")
    found_drives = []
    
    for i in range(start_ip, end_ip + 1):
        ip = f"{network_base}.{i}"
        print(f"Checking {ip}...", end=" ")
        
        try:
            controller = STM23QEthernetController(ip, timeout=1)
            if controller.connect():
                response = controller.send_command("MV")
                if response and "050" in response:  # STM23Q model code
                    print("✅ STM23Q found!")
                    found_drives.append(ip)
                else:
                    print("❌")
                controller.disconnect()
            else:
                print("❌")
        except:
            print("❌")
        
        time.sleep(0.1)
    
    return found_drives

def main():
    """Main function to run the eSCL connection test"""
    print("STM23Q-3EE Ethernet eSCL Connection Test Script")
    print("=" * 55)
    
    # Get IP address from user
    default_ip = "192.168.1.10"
    ip_input = input(f"Enter drive IP address (default: {default_ip}): ").strip()
    ip_address = ip_input if ip_input else default_ip
    
    # Ask about drive discovery
    discover = input("Would you like to scan for drives on the network first? (y/n): ").strip().lower()
    
    if discover == 'y':
        found_drives = discover_drives_on_network()
        if found_drives:
            print(f"\nFound STM23Q drives at: {found_drives}")
            if len(found_drives) == 1:
                ip_address = found_drives[0]
                print(f"Using discovered drive at {ip_address}")
            else:
                print("Multiple drives found. Please specify which one to use.")
        else:
            print("No STM23Q drives found during scan.")
    
    # Choose protocol
    protocol = input("Select protocol (UDP/TCP, default: UDP): ").strip().upper()
    protocol = protocol if protocol in ['UDP', 'TCP'] else 'UDP'
    
    try:
        # Create controller instance
        controller = STM23QEthernetController(ip_address, protocol=protocol)
        
        # Connect to drive
        if not controller.connect():
            print("\nFailed to establish eSCL connection. Please check:")
            print("1. Drive is powered on and connected to network")
            print("2. IP address is correct")
            print("3. Network connectivity (firewall, etc.)")
            print("4. Drive is configured for eSCL communication")
            return
        
        # Test the connection
        connection_ok = controller.test_connection()
        
        if connection_ok:
            # Get detailed drive information
            controller.get_drive_info()
            
            print("\n" + "="*60)
            print("eSCL connection test completed successfully!")
            print("You can now send eSCL commands to control the drive over Ethernet.")
            print("="*60)
        else:
            print("\neSCL connection test failed. Please check drive network settings.")
    
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    
    except Exception as e:
        print(f"Unexpected error: {e}")
    
    finally:
        # Always disconnect
        if 'controller' in locals():
            controller.disconnect()

if __name__ == "__main__":
    main()