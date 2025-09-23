#!/usr/bin/env python3

import curses
import os
import subprocess

class PowerMonitorSetup:
    def __init__(self):
        self.config_file = "/etc/powermonitor/config.conf"
    
    def load_existing_config(self):
        """Load existing configuration if it exists"""
        config = {
            'DEVICE_ID': '',
            'LOCATION_NAME': '',
            'CT_RATING': '30',
            'VOLTAGE': '120.0',
            'SERVER_URL': 'https://linesights.com/api/data',
            'TIMEZONE': 'America/New_York'
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    lines = f.readlines()
                
                for line in lines:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        if key in config:
                            config[key] = value
                                
                return config, True  # True = existing config loaded
        except Exception as e:
            pass
        
        return config, False  # False = no existing config
    
    def save_config(self, config):
        """Save configuration to file"""
        try:
            temp_config = "/tmp/powermonitor_config.conf"
            with open(temp_config, 'w') as f:
                f.write("# Power Monitor Configuration - Updated\n")
                f.write(f"# Updated: {os.popen('date').read().strip()}\n")
                f.write("#\n")
                for key, value in config.items():
                    f.write(f"{key}={value}\n")
            
            subprocess.run(['sudo', 'cp', temp_config, self.config_file], check=True)
            subprocess.run(['sudo', 'chown', 'pi:pi', self.config_file], check=True)
            os.remove(temp_config)
            
            return True, "Configuration saved successfully!"
        except Exception as e:
            return False, f"Error saving config: {str(e)}"

def draw_header(stdscr, title):
    """Draw the application header"""
    height, width = stdscr.getmaxyx()
    stdscr.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD)
    stdscr.addstr(1, 0, "=" * width)

def edit_config_screen(stdscr, setup, config):
    """Interactive configuration editor"""
    current_field = 0
    fields = ['DEVICE_ID', 'LOCATION_NAME', 'CT_RATING', 'VOLTAGE', 'SERVER_URL']
    
    ct_options = ['30', '50', '100', '200']
    voltage_options = ['110.0', '120.0', '230.0', '240.0']
    
    while True:
        stdscr.clear()
        draw_header(stdscr, "🔌 Power Monitor Configuration Editor")
        
        stdscr.addstr(3, 2, "Use ↑↓ to navigate, ENTER to edit, ←→ for options", curses.A_DIM)
        stdscr.addstr(4, 2, "F1=Save&Restart  F2=Save  ESC=Cancel", curses.A_DIM)
        
        # Show fields
        row = 6
        for i, field in enumerate(fields):
            attr = curses.A_REVERSE if i == current_field else curses.A_NORMAL
            
            if field == 'DEVICE_ID':
                stdscr.addstr(row, 2, "Device Name: ", attr)
                stdscr.addstr(row, 17, config[field], attr)
            elif field == 'LOCATION_NAME':
                stdscr.addstr(row + 1, 2, "Location: ", attr)
                stdscr.addstr(row + 1, 17, config[field], attr)
            elif field == 'CT_RATING':
                stdscr.addstr(row + 2, 2, "CT Rating: ", attr)
                stdscr.addstr(row + 2, 17, f"{config[field]}A (←→ to change)", attr)
            elif field == 'VOLTAGE':
                stdscr.addstr(row + 3, 2, "Voltage: ", attr)
                stdscr.addstr(row + 3, 17, f"{config[field]}V (←→ to change)", attr)
            elif field == 'SERVER_URL':
                stdscr.addstr(row + 4, 2, "Server URL: ", attr)
                stdscr.addstr(row + 4, 17, config[field], attr)
        
        stdscr.addstr(row + 6, 2, f"Timezone: {config['TIMEZONE']}", curses.A_DIM)
        stdscr.refresh()
        
        key = stdscr.getch()
        
        if key == curses.KEY_UP and current_field > 0:
            current_field -= 1
        elif key == curses.KEY_DOWN and current_field < len(fields) - 1:
            current_field += 1
        elif key == curses.KEY_LEFT:
            if fields[current_field] == 'CT_RATING':
                current_idx = ct_options.index(config['CT_RATING'])
                config['CT_RATING'] = ct_options[(current_idx - 1) % len(ct_options)]
            elif fields[current_field] == 'VOLTAGE':
                current_idx = voltage_options.index(config['VOLTAGE'])
                config['VOLTAGE'] = voltage_options[(current_idx - 1) % len(voltage_options)]
        elif key == curses.KEY_RIGHT:
            if fields[current_field] == 'CT_RATING':
                current_idx = ct_options.index(config['CT_RATING'])
                config['CT_RATING'] = ct_options[(current_idx + 1) % len(ct_options)]
            elif fields[current_field] == 'VOLTAGE':
                current_idx = voltage_options.index(config['VOLTAGE'])
                config['VOLTAGE'] = voltage_options[(current_idx + 1) % len(voltage_options)]
        elif key == ord('\n') or key == ord('\r'):
            field = fields[current_field]
            if field in ['DEVICE_ID', 'LOCATION_NAME', 'SERVER_URL']:
                stdscr.addstr(20, 2, f"Enter new {field.lower().replace('_', ' ')}: ")
                stdscr.refresh()
                curses.echo()
                new_value = stdscr.getstr().decode('utf-8').strip()
                curses.noecho()
                if new_value:
                    if field == 'DEVICE_ID':
                        # Clean device ID
                        new_value = ''.join(c for c in new_value if c.isalnum() or c in '_-').lower()
                    config[field] = new_value
        elif key == 265:  # F1 - Save & Restart
            return config, "restart"
        elif key == 266:  # F2 - Save
            return config, "save"
        elif key == 27:  # ESC
            return None, "cancel"

def main_setup_flow(stdscr):
    """Main setup flow"""
    setup = PowerMonitorSetup()
    
    # Load existing configuration
    config, config_exists = setup.load_existing_config()
    
    if not config_exists:
        stdscr.clear()
        stdscr.addstr(0, 2, "No configuration found!", curses.A_BOLD)
        stdscr.addstr(2, 2, "Press any key to exit...")
        stdscr.refresh()
        stdscr.getch()
        return
    
    # Show current config and edit
    result, action = edit_config_screen(stdscr, setup, config)
    
    if action == "cancel" or result is None:
        stdscr.clear()
        stdscr.addstr(0, 2, "Configuration cancelled.", curses.A_BOLD)
        stdscr.addstr(2, 2, "Press any key to exit...")
        stdscr.refresh()
        stdscr.getch()
        return
    
    # Save configuration
    stdscr.clear()
    stdscr.addstr(0, 2, "Saving configuration...", curses.A_BOLD)
    stdscr.refresh()
    
    success, message = setup.save_config(result)
    
    if success:
        stdscr.addstr(2, 2, "✅ Configuration saved!")
        
        if action == "restart":
            stdscr.addstr(3, 2, "🔄 Restarting service...")
            stdscr.refresh()
            try:
                subprocess.run(['sudo', 'systemctl', 'restart', 'powermonitor'])
                stdscr.addstr(4, 2, "✅ Service restarted!")
            except:
                stdscr.addstr(4, 2, "❌ Service restart failed")
        else:
            stdscr.addstr(3, 2, "💡 Restart service to apply: sudo systemctl restart powermonitor")
    else:
        stdscr.addstr(2, 2, f"❌ {message}")
    
    stdscr.addstr(6, 2, "Press any key to exit...")
    stdscr.refresh()
    stdscr.getch()

def main():
    """Main application entry point"""
    try:
        curses.wrapper(main_setup_flow)
    except KeyboardInterrupt:
        print("\nConfiguration cancelled.")
    except Exception as e:
        print(f"Configuration error: {e}")

if __name__ == "__main__":
    main()
