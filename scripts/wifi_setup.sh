#!/bin/bash

# WiFi Setup Script for Raspberry Pi
# Scans for networks, lets user select one, and connects

echo ""
echo "📶 WiFi Setup"
echo "============="

# Check if already connected to WiFi
current_ssid=$(iwgetid -r 2>/dev/null)
if [ -n "$current_ssid" ]; then
    echo "✅ Already connected to: $current_ssid"

    # Test internet connectivity
    if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
        echo "✅ Internet connection working"
        echo ""
        read -p "Do you want to connect to a different network? (y/N): " change_wifi
        if [[ ! "$change_wifi" =~ ^[Yy]$ ]]; then
            echo "Keeping current WiFi connection."
            exit 0
        fi
    else
        echo "⚠️  Connected to WiFi but no internet access"
    fi
fi

echo ""
echo "🔍 Scanning for WiFi networks..."
echo ""

# Scan for networks
# Try nmcli first (newer systems), fall back to iwlist
if command -v nmcli &>/dev/null; then
    # Using NetworkManager
    scan_result=$(nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list 2>/dev/null | grep -v "^--" | grep -v "^$" | head -15)

    if [ -z "$scan_result" ]; then
        # Force rescan
        nmcli dev wifi rescan 2>/dev/null
        sleep 2
        scan_result=$(nmcli -t -f SSID,SIGNAL,SECURITY dev wifi list 2>/dev/null | grep -v "^--" | grep -v "^$" | head -15)
    fi

    if [ -z "$scan_result" ]; then
        echo "❌ No WiFi networks found. Make sure WiFi is enabled."
        echo "   Try: sudo rfkill unblock wifi"
        exit 1
    fi

    # Display networks
    echo "Available networks:"
    echo "-------------------"
    i=1
    declare -a networks
    while IFS=: read -r ssid signal security; do
        if [ -n "$ssid" ]; then
            networks[$i]="$ssid"
            # Show signal strength as bars
            if [ "$signal" -gt 70 ]; then
                bars="▂▄▆█"
            elif [ "$signal" -gt 50 ]; then
                bars="▂▄▆_"
            elif [ "$signal" -gt 30 ]; then
                bars="▂▄__"
            else
                bars="▂___"
            fi

            # Show lock if secured
            if [ -n "$security" ] && [ "$security" != "--" ]; then
                lock="🔒"
            else
                lock="  "
            fi

            printf "  %2d) %s %s %s\n" "$i" "$bars" "$lock" "$ssid"
            ((i++))
        fi
    done <<< "$scan_result"

    echo ""
    echo "  0) Enter network name manually"
    echo "  q) Quit"
    echo ""

    # Get user selection
    read -p "Select network (1-$((i-1))): " selection

    if [[ "$selection" == "q" ]] || [[ "$selection" == "Q" ]]; then
        echo "WiFi setup cancelled."
        exit 0
    fi

    if [[ "$selection" == "0" ]]; then
        read -p "Enter network name (SSID): " ssid
    elif [[ "$selection" =~ ^[0-9]+$ ]] && [ "$selection" -ge 1 ] && [ "$selection" -lt "$i" ]; then
        ssid="${networks[$selection]}"
    else
        echo "❌ Invalid selection"
        exit 1
    fi

    echo ""
    echo "Connecting to: $ssid"

    # Get password
    read -s -p "Enter WiFi password (leave blank if open): " password
    echo ""

    # Connect using nmcli
    echo "🔄 Connecting..."
    if [ -n "$password" ]; then
        nmcli dev wifi connect "$ssid" password "$password" 2>&1
    else
        nmcli dev wifi connect "$ssid" 2>&1
    fi

else
    # Fallback to iwlist + wpa_supplicant
    echo "Using wpa_supplicant method..."

    scan_result=$(sudo iwlist wlan0 scan 2>/dev/null | grep -E "ESSID:" | cut -d'"' -f2 | grep -v "^$" | sort -u | head -15)

    if [ -z "$scan_result" ]; then
        echo "❌ No WiFi networks found."
        exit 1
    fi

    echo "Available networks:"
    echo "-------------------"
    i=1
    declare -a networks
    while read -r ssid; do
        if [ -n "$ssid" ]; then
            networks[$i]="$ssid"
            printf "  %2d) %s\n" "$i" "$ssid"
            ((i++))
        fi
    done <<< "$scan_result"

    echo ""
    echo "  0) Enter network name manually"
    echo "  q) Quit"
    echo ""

    read -p "Select network (1-$((i-1))): " selection

    if [[ "$selection" == "q" ]] || [[ "$selection" == "Q" ]]; then
        echo "WiFi setup cancelled."
        exit 0
    fi

    if [[ "$selection" == "0" ]]; then
        read -p "Enter network name (SSID): " ssid
    elif [[ "$selection" =~ ^[0-9]+$ ]] && [ "$selection" -ge 1 ] && [ "$selection" -lt "$i" ]; then
        ssid="${networks[$selection]}"
    else
        echo "❌ Invalid selection"
        exit 1
    fi

    echo ""
    echo "Connecting to: $ssid"

    read -s -p "Enter WiFi password: " password
    echo ""

    # Add to wpa_supplicant
    echo "🔄 Connecting..."
    wpa_passphrase "$ssid" "$password" | sudo tee -a /etc/wpa_supplicant/wpa_supplicant.conf > /dev/null
    sudo wpa_cli -i wlan0 reconfigure > /dev/null 2>&1
fi

# Wait for connection
echo "⏳ Waiting for connection..."
for i in {1..15}; do
    sleep 1
    if ping -c 1 -W 1 8.8.8.8 &>/dev/null; then
        echo ""
        echo "✅ Connected to $ssid!"
        echo "✅ Internet connection verified!"

        # Show IP address
        ip_addr=$(hostname -I | awk '{print $1}')
        echo "📍 IP Address: $ip_addr"
        echo ""
        exit 0
    fi
    printf "."
done

echo ""
echo "⚠️  Connection may have failed. Please check:"
echo "   - Password is correct"
echo "   - Network is in range"
echo "   - Try running this script again"
echo ""

# Check if connected to WiFi but no internet
if iwgetid -r &>/dev/null; then
    echo "📶 Connected to WiFi but no internet access"
    echo "   The network may not have internet connectivity"
fi

exit 1
