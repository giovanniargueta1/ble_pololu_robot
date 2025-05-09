import bluetooth
import struct
import time
from machine import Pin, UART
from micropython import const

# Bluetooth Core Specification
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_GATTS_READ_REQUEST = const(4)

# LED for visual feedback
led = Pin("LED", Pin.OUT)

# Create a visible and standard name
DEVICE_NAME = "PICO_ROBOT_BRIDGE_2"

# Standard Service UUID for Nordic UART Service
SERVICE_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
# Nordic UART RX Characteristic (for writes from central)
RX_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
# Nordic UART TX Characteristic (for reads and notifications to central)
TX_UUID = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")

# Global variables
is_connected = False
last_command = "No commands received yet"
last_response = "No response from robot yet"
ble_service = None  # Will be set in main()

# Configure UART - matching the Pololu's settings
uart = UART(1, baudrate=9600, tx=Pin(4), rx=Pin(5))

class BLEUARTBridge:
    def __init__(self):
        # Initialize BLE
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        
        # Register services and characteristics
        ((self._handle_tx, self._handle_rx),) = self._ble.gatts_register_services((
            (SERVICE_UUID, (
                (TX_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY),
                (RX_UUID, bluetooth.FLAG_WRITE),
            )),
        ))
        
        # Set initial values
        self._connections = set()
        self._ble.gatts_write(self._handle_tx, "Robot Bridge Ready".encode())
        
        # Start advertising
        self._advertise()
        print(f"BLE device '{DEVICE_NAME}' initialized as UART bridge to Pololu 2040")
        
    def _irq(self, event, data):
        global is_connected, last_command
        
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            print(f"Connected to central: {conn_handle}")
            self._connections.add(conn_handle)
            is_connected = True
            led.on()
            
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            print(f"Disconnected from central: {conn_handle}")
            if conn_handle in self._connections:
                self._connections.remove(conn_handle)
            is_connected = False
            led.off()
            self._advertise()
            
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._handle_rx:
                # Get the message written to RX characteristic
                message = self._ble.gatts_read(self._handle_rx).decode()
                last_command = message
                print(f"Received command: {message}")
                
                # Forward the command to the robot via UART
                self._send_to_robot(message)
                
        elif event == _IRQ_GATTS_READ_REQUEST:
            conn_handle, value_handle = data
            if value_handle == self._handle_tx:
                print("Central device is reading TX characteristic")
    
    def _advertise(self):
        # Advertising payload
        adv_data = bytearray()
        
        # Add device name
        device_name = DEVICE_NAME.encode()
        adv_data += struct.pack("BB", len(device_name) + 1, 0x09) + device_name
        
        # Add service UUID - we'll use the 16-bit representation
        adv_data += struct.pack("BBH", 3, 0x03, 0xFE9F)
        
        # Standard flags
        adv_data += struct.pack("BBB", 2, 0x01, 0x06)
        
        # Start advertising
        print(f"Starting advertising as '{DEVICE_NAME}'")
        self._ble.gap_advertise(100000, adv_data=adv_data)
    
    def _send_to_robot(self, command):
        """Send command to robot over UART"""
        try:
            # Add newline to command for proper parsing
            if not command.endswith('\n'):
                command += '\n'
            
            # Send the command to the robot
            uart.write(command.encode())
            print(f"Sent to robot: {command.strip()}")
            
            # Add a short delay to ensure command is sent completely
            time.sleep(0.1)
            
            # Provide acknowledgment to BLE central
            ack = f"Command '{command.strip()}' sent to robot"
            self.update_tx(ack)
        except Exception as e:
            error_msg = f"Error sending to robot: {str(e)}"
            print(error_msg)
            self.update_tx(error_msg)
    
    def _notify(self, data):
        """Send notification to connected BLE central devices"""
        for conn_handle in self._connections:
            self._ble.gatts_notify(conn_handle, self._handle_tx, data.encode())
    
    def update_tx(self, new_value):
        """Update TX characteristic and send notification"""
        try:
            self._ble.gatts_write(self._handle_tx, new_value.encode())
            self._notify(new_value)
            print(f"Updated TX value: {new_value}")
        except Exception as e:
            print(f"Error updating TX: {e}")


def check_for_robot_response():
    """Check for any response from the robot and forward it to the BLE central"""
    global last_response
    
    try:
        # Check if data is available
        if uart.any():
            # Read data WITHOUT keyword arguments
            response = uart.read()
            if response:
                # Decode WITHOUT keyword arguments
                response_str = response.decode().strip()
                last_response = response_str
                print(f"Received from robot: {response_str}")
                
                # Forward response to BLE central if connected
                if is_connected and ble_service:
                    # Include source in the response
                    ble_message = f"Robot: {response_str}"
                    ble_service.update_tx(ble_message)
                
                return True
    except Exception as e:
        print(f"Simple read error: {e}")
    
    return False


def main():
    global ble_service
    
    # Initialize and create BLE service
    ble_service = BLEUARTBridge()
    
    # Blink LED 3 times to indicate startup
    for _ in range(3):
        led.on()
        time.sleep(0.1)
        led.off()
        time.sleep(0.1)
    
    # Send an initial ping to the robot to test the connection
    print("Sending initial ping to robot...")
    try:
        uart.write(b"PING\n")
    except Exception as e:
        print(f"Error sending initial ping: {e}")
    
    # Counter for heartbeat messages
    counter = 0
    
    # Main loop
    print("Main loop started - waiting for commands or robot responses")
    try:
        while True:
            counter += 1
            
            # Check for responses from the robot
            check_for_robot_response()
            
            # Every 30 seconds, send a heartbeat to the robot if connected
            if counter % 30 == 0:
                try:
                    heartbeat = f"HEARTBEAT {counter//30}\n"
                    uart.write(heartbeat.encode())
                    print(f"Sent heartbeat to robot: {heartbeat.strip()}")
                    
                    # Also update BLE status if connected
                    if is_connected:
                        ble_service.update_tx(f"Bridge active - Last robot response: {last_response}")
                except Exception as e:
                    print(f"Error sending heartbeat: {e}")
            
            # Every 10 seconds, print status to console
            if counter % 10 == 0:
                status = "Connected" if is_connected else "Disconnected"
                print(f"Status: {status}, Last command: {last_command}, Last response: {last_response}")
            
            # Blink LED when disconnected
            if not is_connected:
                if counter % 2 == 0:
                    led.toggle()
            
            # Sleep to avoid busy waiting
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("Keyboard interrupt, exiting...")
    except Exception as e:
        print(f"Unexpected error in main loop: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Critical error: {e}")
        # Rapid blink to indicate critical error
        while True:
            led.toggle()
            time.sleep(0.1)
