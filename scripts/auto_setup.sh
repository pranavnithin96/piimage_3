#!/bin/bash

# Enhanced Auto-setup - Always accessible
echo ""
echo "🔌 Enhanced Power Monitor Configuration Manager"

# Check if configuration exists
if [ -f "/etc/powermonitor/config.conf" ]; then
    echo "📝 Current configuration found"
    
    # Show current device info
    DEVICE_ID=$(grep "DEVICE_ID=" /etc/powermonitor/config.conf 2>/dev/null | cut -d'=' -f2)
    LOCATION=$(grep "LOCATION_NAME=" /etc/powermonitor/config.conf 2>/dev/null | cut -d'=' -f2)
    
    echo "📱 Device: $DEVICE_ID"
    echo "📍 Location: $LOCATION"
    
    # Check service status
    if systemctl is-active --quiet powermonitor 2>/dev/null; then
        echo "✅ Service is running"
    else
        echo "❌ Service is not running"
    fi
    
    echo ""
    echo "Options:"
    echo "  [ENTER] - Open configuration wizard"
    echo "  [s] - Show service logs"
    echo "  [q] - Skip"
    
    read -n 1 -r -p "Choice: " choice
    echo ""
    
    case $choice in
        s|S)
            echo "📊 Showing service logs (Ctrl+C to exit)..."
            journalctl -u powermonitor -f
            ;;
        q|Q)
            echo "Skipping configuration."
            ;;
        *)
            echo "Opening configuration wizard..."
            python3 /opt/powermonitor/turnkey_setup_interactive.py
            ;;
    esac
else
    echo "🆕 No configuration found - starting setup..."
    python3 /opt/powermonitor/turnkey_setup_interactive.py
fi

echo ""
