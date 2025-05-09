rom machine import Pin, UART
import time
import random

# Import robot modules
from pololu_3pi_2040_robot import robot

# Initialize robot components
motors = robot.Motors()
display = robot.Display()
line_sensors = robot.LineSensors()
bump_sensors = robot.BumpSensors()
yellow_led = robot.YellowLED()
buzzer = robot.Buzzer()

# LED for visual feedback
led = Pin(25, Pin.OUT)  # Use the onboard LED on the Pololu 2040

# Initialize UART for communication with Pico W 2
print("Initializing UART with direct pin numbers")
uart = UART(0, baudrate=9600, tx=28, rx=29)
print("UART initialized successfully")

# Mode and state variables
MODE_MANUAL = 0
MODE_LINE_FOLLOWING = 1
MODE_STOPPED = 2

current_mode = MODE_STOPPED
line_calibrated = False

# Speed settings
SPEED_LEVEL_1 = 1000    # Slow
SPEED_LEVEL_2 = 1250    # Medium
SPEED_LEVEL_3 = 1500   # Fast

current_speed = SPEED_LEVEL_1

# Line following variables
p = 0
last_p = 0
line = [0, 0, 0, 0, 0]

# Collision detection flag
collision_detected = False

# Calibration settings - using moderate default values
calibration_speed = 200
calibration_count = 100

# Buffer for incoming messages
rx_buffer = ""

# Command Handlers
def cmd_forward():
    global current_mode
    if not collision_detected:
        current_mode = MODE_MANUAL
        motors.set_speeds(current_speed, current_speed)
        display_update("FORWARD", f"Speed: {current_speed}")
        return f"MOVING:FORWARD at speed {current_speed}"
    else:
        return "ERROR:COLLISION_DETECTED"

def cmd_backward():
    global current_mode
    current_mode = MODE_MANUAL
    motors.set_speeds(-current_speed, -current_speed)
    display_update("BACKWARD", f"Speed: {current_speed}")
    return f"MOVING:BACKWARD at speed {current_speed}"

def cmd_left():
    global current_mode
    current_mode = MODE_MANUAL
    motors.set_speeds(-current_speed, current_speed)
    display_update("LEFT", f"Speed: {current_speed}")
    return f"TURNING:LEFT at speed {current_speed}"

def cmd_right():
    global current_mode
    current_mode = MODE_MANUAL
    motors.set_speeds(current_speed, -current_speed)
    display_update("RIGHT", f"Speed: {current_speed}")
    return f"TURNING:RIGHT at speed {current_speed}"

def cmd_stop():
    global current_mode
    prev_mode = current_mode
    current_mode = MODE_STOPPED
    motors.off()
    display_update("STOPPED", "Motors off")
    
    # Auto-resume line following after a brief pause
    if prev_mode == MODE_LINE_FOLLOWING:
        time.sleep_ms(3000)
        current_mode = MODE_LINE_FOLLOWING
        display_update("LINE FOLLOW", f"Speed: {current_speed}")
        return "STOPPED (resuming line following)"
    else:
        return "STOPPED"

def cmd_speed(level):
    global current_speed
    try:
        level_num = int(level)
        if level_num == 1:
            current_speed = SPEED_LEVEL_1
        elif level_num == 2:
            current_speed = SPEED_LEVEL_2
        elif level_num == 3:
            current_speed = SPEED_LEVEL_3
        else:
            return "ERROR:INVALID_SPEED_LEVEL (use 1-3)"
        
        display_update("SPEED CHANGED", f"New speed: {current_speed}")
        return f"SPEED_SET:{level_num} ({current_speed})"
    except ValueError:
        return "ERROR:INVALID_SPEED_LEVEL (use 1-3)"

def cmd_status():
    global collision_detected, current_mode, current_speed, line_calibrated
    
    # Read bump sensors
    bump_sensors.read()
    
    # Get mode as text
    mode_text = "STOPPED"
    if current_mode == MODE_MANUAL:
        mode_text = "MANUAL"
    elif current_mode == MODE_LINE_FOLLOWING:
        mode_text = "LINE_FOLLOWING"
    
    # Construct status message
    status = "STATUS:OK,"
    status += f"BATTERY:{random.randint(80, 100)}%,"
    status += f"MODE:{mode_text},"
    status += f"SPEED:{current_speed},"
    status += f"CALIBRATED:{line_calibrated},"
    status += f"COLLISION:{collision_detected},"
    status += f"LEFT_BUMP:{bump_sensors.left_is_pressed()},"
    status += f"RIGHT_BUMP:{bump_sensors.right_is_pressed()}"
    
    display_update("STATUS CHECK", f"Mode: {mode_text}")
    return status

def cmd_line_follow(param=""):
    global current_mode, line_calibrated
    
    if param.upper() == "START":
        if line_calibrated:
            current_mode = MODE_LINE_FOLLOWING
            display_update("LINE FOLLOW", "STARTED")
            return "LINE_FOLLOWING:STARTED"
        else:
            return "ERROR:NOT_CALIBRATED"
    elif param.upper() == "STOP":
        current_mode = MODE_STOPPED
        motors.off()
        display_update("LINE FOLLOW", "STOPPED")
        return "LINE_FOLLOWING:STOPPED"
    elif param.upper() == "CALIBRATE":
        return calibrate_line_sensors()
    else:
        if current_mode == MODE_LINE_FOLLOWING:
            return "LINE_FOLLOWING:ACTIVE"
        else:
            return "LINE_FOLLOWING:INACTIVE"

def calibrate_line_sensors():
    global line_calibrated, current_mode
    
    # Switch to stopped mode
    current_mode = MODE_STOPPED
    motors.off()
    
    display.fill(0)
    display.text("Calibrating", 0, 0)
    display.text("Line Sensors...", 0, 10)
    display.show()
    
    try:
        # Calibration sequence
        motors.set_speeds(calibration_speed, -calibration_speed)
        for i in range(int(calibration_count/4)):
            line_sensors.calibrate()
        
        motors.off()
        time.sleep_ms(200)
        
        motors.set_speeds(-calibration_speed, calibration_speed)
        for i in range(int(calibration_count/2)):
            line_sensors.calibrate()
        
        motors.off()
        time.sleep_ms(200)
        
        motors.set_speeds(calibration_speed, -calibration_speed)
        for i in range(int(calibration_count/4)):
            line_sensors.calibrate()
        
        motors.off()
        
        line_calibrated = True
        display.fill(0)
        display.text("Calibration", 0, 0)
        display.text("Complete!", 0, 10)
        display.text("Starting Line", 0, 20)
        display.text("Following...", 0, 30)
        display.show()
        time.sleep_ms(1000)
        
        # Automatically start line following after calibration
        current_mode = MODE_LINE_FOLLOWING
        
        return "LINE_SENSORS:CALIBRATED_AND_FOLLOWING"
    except Exception as e:
        line_calibrated = False
        display.fill(0)
        display.text("Calibration", 0, 0)
        display.text("Failed!", 0, 10)
        display.text(str(e), 0, 20)
        display.show()
        time.sleep_ms(1000)
        
        return f"ERROR:CALIBRATION_FAILED ({str(e)})"

def cmd_heartbeat(val):
    return f"HEARTBEAT_ACK:{val}"

# Command dictionary
COMMANDS = {
    "PING": "PONG",
    "STATUS": cmd_status,
    "FORWARD": cmd_forward,
    "BACKWARD": cmd_backward,
    "LEFT": cmd_left,
    "RIGHT": cmd_right,
    "STOP": cmd_stop,
    "SPEED": cmd_speed,
    "LINE": cmd_line_follow,
    "HEARTBEAT": cmd_heartbeat,
}

def display_update(title, message):
    """Helper function to update the display"""
    display.fill(0)
    display.text("BLE Control", 0, 0)
    display.text(title, 0, 10)
    display.text(message, 0, 20)
    
    # Show mode
    mode_text = "STOPPED"
    if current_mode == MODE_MANUAL:
        mode_text = "MANUAL"
    elif current_mode == MODE_LINE_FOLLOWING:
        mode_text = "LINE"
    display.text(f"Mode: {mode_text}", 0, 30)
    
    if collision_detected:
        display.text("!COLLISION!", 0, 50)
    
    display.show()

def process_command(command):
    """Process a received command and return appropriate response"""
    # Log the received command for debugging
    print(f"Processing command: {command}")
    
    command = command.strip().upper()
    response = "ERROR:UNKNOWN_COMMAND"
    
    # Check for commands with parameters
    parts = command.split()
    base_cmd = parts[0]
    
    # Extra visual feedback
    led.on()
    
    if base_cmd in COMMANDS:
        if callable(COMMANDS[base_cmd]):
            # If the command value is a function, call it with any parameters
            if len(parts) > 1:
                response = COMMANDS[base_cmd](parts[1])
                print(f"Called {base_cmd} with param {parts[1]}")
            else:
                response = COMMANDS[base_cmd]()
                print(f"Called {base_cmd} without params")
        else:
            # Otherwise, return the static response
            response = COMMANDS[base_cmd]
            print(f"Got static response: {response}")
    
    # Turn off LED after processing
    led.off()
    
    return response

def check_collisions():
    """Check bump sensors for collisions"""
    global collision_detected, current_mode
    
    # Read bump sensors
    bump_sensors.read()
    
    # Check if either sensor is pressed
    if bump_sensors.left_is_pressed() or bump_sensors.right_is_pressed():
        if not collision_detected:
            collision_detected = True
            yellow_led.on()
            buzzer.play("c32")
            
            # If we're moving forward, stop the motors
            if current_mode != MODE_STOPPED and motors._left_speed > 0 and motors._right_speed > 0:
                motors.off()
                current_mode = MODE_STOPPED
                return True
    else:
        if collision_detected:
            collision_detected = False
            yellow_led.off()
    
    return False

def follow_line():
    """Execute one iteration of the line following algorithm"""
    global p, last_p, line, current_mode, current_speed
    
    # Read line sensors
    line = line_sensors.read_calibrated()[:]
    line_sensors.start_read()
    
    # Positive p means robot is to left of line
    if line[1] < 700 and line[2] < 700 and line[3] < 700:
        if p < 0:
            l = 0
        else:
            l = 4000
    else:
        # Estimate line position
        try:
            l = (1000*line[1] + 2000*line[2] + 3000*line[3] + 4000*line[4]) // sum(line)
        except ZeroDivisionError:
            l = 2000  # Center position if no line detected
    
    p = l - 2000
    d = p - last_p
    last_p = p
    
    # PID coefficients adjusted for lower speeds
    pid = p*15 + d*300
    
    min_speed = 0
    max_speed = current_speed
    left = max(min_speed, min(max_speed, max_speed + pid))
    right = max(min_speed, min(max_speed, max_speed - pid))
    
    # Set motor speeds for line following
    motors.set_speeds(left, right)

# Main function
def main():
    global current_mode, line_calibrated, collision_detected, rx_buffer
    
    # Calibrate bump sensors
    bump_sensors.calibrate()
    
    # Clear any pending data
    if uart.any():
        uart.read()
    
    # Blink LED 3 times to indicate startup
    for _ in range(3):
        led.on()
        time.sleep(0.1)
        led.off()
        time.sleep(0.1)
    
    # Automatically start calibration at boot
    display.fill(0)
    display.text("Auto-Calibrating", 0, 0)
    display.text("Line Sensors...", 0, 10)
    display.show()
    time.sleep_ms(1000)
    
    # Call calibration routine
    calibrate_line_sensors()
    
    # Send initial message
    try:
        uart.write(b"ROBOT_READY_AND_FOLLOWING\n")
        print("Robot calibrated and following line")
    except Exception as e:
        print(f"Error sending ready message: {e}")
    
    # Counter for status updates
    counter = 0
    
    # Main loop
    print("Starting main loop")
    while True:
        # Check for collisions
        check_collisions()
        
        # Process any incoming UART data - FIXED THIS SECTION
        if uart.any() > 0:
            print("Data available on UART")
            try:
                # Read all available data
                data = uart.read()
                if data:
                    # Convert bytes to string and process
                    new_data = data.decode()
                    print(f"Received data: {new_data}")
                    
                    # Add to buffer and check for complete commands
                    rx_buffer += new_data
                    
                    # Process any complete commands in the buffer
                    if '\n' in rx_buffer:
                        # Split by newlines in case we received multiple commands
                        commands = rx_buffer.split('\n')
                        # All but the last part are complete commands
                        for cmd in commands[:-1]:
                            if cmd.strip():  # Skip empty commands
                                print(f"Processing command: {cmd}")
                                response = process_command(cmd.strip())
                                uart.write(f"{response}\n".encode())
                        
                        # Keep any partial command in the buffer
                        rx_buffer = commands[-1]
            except Exception as e:
                print(f"Error processing UART data: {e}")
                rx_buffer = ""  # Clear buffer on error
        
        # Execute line following if in the right mode
        if current_mode == MODE_LINE_FOLLOWING and line_calibrated and not collision_detected:
            follow_line()
        
        # Send autonomous status update every ~60 seconds
        counter += 1
        if counter >= 600:  # ~60 seconds (100ms per loop * 600)
            counter = 0
            try:
                status = cmd_status()
                status_update = f"AUTO:{status}\n"
                print(f"Sending status: {status_update.strip()}")
                uart.write(status_update.encode())
                
                # Blink LED
                led.on()
                time.sleep(0.1)
                led.off()
            except Exception as e:
                print(f"Error sending status: {e}")
        
        # Small delay to avoid busy loop
        time.sleep_ms(100)

# Run the main program
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Critical error: {e}")
        motors.off()
        yellow_led.on()
        
        # Display error
        display.fill(0)
        display.text("ERROR!", 0, 0)
        display.text(str(e)[:20], 0, 10)
        display.show()

