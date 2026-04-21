# FileName: tracker_server.py
from flask import Flask, request, jsonify, session, redirect, url_for
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit
from functools import wraps
import threading
import json
import os
import time
import sqlite3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import binascii
import logging
import subprocess # To check if ngrok is installed
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- ngrok integration ---
from pyngrok import ngrok, conf

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tracker_server.log'),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
app.secret_key = os.urandom(32) # Generate a random secret key for session management.
auth = HTTPBasicAuth()
socketio = SocketIO(app, cors_allowed_origins="*") # Allow all origins for CORS.

# Configuration
DATABASE = 'tracker.db'
SECRET_KEY = os.urandom(16) # Random 16-byte key for AES-128.

# Updated API_KEYS for both dashboard login and API basic auth
# Username is 'admin', password is 'Jeremiah@888856171110'
API_KEYS = {'1': generate_password_hash('12345678'), 'admin': generate_password_hash('Jeremiah@888856171110')}

# SMTP Configuration for Email Notifications
SMTP_USERNAME = "seabatasechaba0@gmail.com"  # <-- CHANGE THIS TO YOUR GMAIL
SMTP_PASSWORD = "lqihksbxduusdjot"            # <-- CHANGE THIS TO YOUR APP PASSWORD
EMAIL_TO = "seabatasechaba57@gmail.com"        # Email address to send notifications to

# --- Embedded HTML Templates ---
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background-color: #f3f4f6;
        }
        .login-container {
            background-color: white;
            padding: 2.5rem;
            border-radius: 0.5rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            width: 100%;
            max-width: 400px;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 0.75rem;
            margin-bottom: 1rem;
            border: 1px solid #d1d5db;
            border-radius: 0.375rem;
        }
        button {
            width: 100%;
            padding: 0.75rem;
            background-color: #3b82f6;
            color: white;
            border-radius: 0.375rem;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        button:hover {
            background-color: #2563eb;
        }
        .error-message {
            color: #ef4444;
            margin-bottom: 1rem;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <form method="POST">
            <label for="username" class="block text-gray-700 text-sm font-bold mb-2">Username:</label>
            <input type="text" id="username" name="username" required>

            <label for="password" class="block text-gray-700 text-sm font-bold mb-2">Password:</label>
            <input type="password" id="password" name="password" required>

            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
"""

LOCATION_ACCESS_PROMPT_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Location Access Required</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background-color: #f3f4f6;
            text-align: center;
        }
        .prompt-container {
            background-color: white;
            padding: 2.5rem;
            border-radius: 0.5rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            width: 100%;
            max-width: 500px;
        }
        button {
            padding: 0.75rem 1.5rem;
            background-color: #3b82f6;
            color: white;
            border-radius: 0.375rem;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 0.2s;
            margin-top: 1.5rem;
        }
        button:hover {
            background-color: #2563eb;
        }
    </style>
</head>
<body>
    <div class="prompt-container">
        <h1 class="text-2xl font-bold mb-4">Location Access Required</h1>
        <p class="text-gray-700 mb-6">
            To view the Device Tracker Dashboard, Sechaba's Tracker needs access to your current location.
            This allows the system to display your own location on the map relative to your devices,
            and helps in providing a comprehensive tracking experience.
        </p>
        <p class="text-gray-700 font-semibold">
            Please grant location access in your browser settings.
        </p>
        <button onclick="requestLocationAndRedirect()">Grant Location Access</button>

        <script>
            function requestLocationAndRedirect() {
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(
                        (position) => {
                            window.location.href = '/?location_access=true';
                        },
                        (error) => {
                            alert("Location access denied. You cannot access the dashboard without it.");
                        }
                    );
                } else {
                    alert("Geolocation is not supported by your browser.");
                }
            }
        </script>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Sechaba's Tracker Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/socket.io-client@4/dist/socket.io.min.js"></script>
    <script src="https://unpkg.com/leaflet@1.9.3/dist/leaflet.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.3/dist/leaflet.css" />
    <style>
        #map { height: 500px; }
        .device-card:hover { transform: scale(1.02); }
        /* Custom marker for Sechaba's Endpoint */
        .sechaba-marker {
            background-color: red;
            width: 20px;
            height: 20px;
            display: block;
            left: -10px;
            top: -10px;
            position: relative;
            border-radius: 50%;
            border: 2px solid white;
            box-shadow: 0 0 0 2px red; /* "Full red color" effect */
        }
        /* Custom marker for online devices (green) */
        .online-marker {
            background-color: green;
            width: 20px;
            height: 20px;
            display: block;
            left: -10px;
            top: -10px;
            position: relative;
            border-radius: 50%;
            border: 2px solid white;
            box-shadow: 0 0 0 2px green;
        }
        /* Custom marker for stolen devices (red) */
        .stolen-marker {
            background-color: red;
            width: 20px;
            height: 20px;
            display: block;
            left: -10px;se
            top: -10px;
            position: relative;
            border-radius: 50%;
            border: 2px solid white;
            box-shadow: 0 0 0 2px red;
        }
        /* Animation for solid lines when stolen */
        @keyframes pulse {
            0% { stroke-width: 2px; }
            50% { stroke-width: 4px; }
            100% { stroke-width: 2px; }
        }
        .stolen-line {
            animation: pulse 1.5s infinite alternate;
        }
    </style>
</head>
<body class="bg-gray-100">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold mb-8">Sechaba's Tracker Dashboard</h1>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Status Overview -->
            <div class="bg-white rounded-lg shadow p-6">
                <h2 class="text-xl font-semibold mb-4">Status Overview</h2>
                <div class="grid grid-cols-2 gap-4">
                    <div class="bg-blue-50 p-3 rounded">
                        <p class="text-gray-500">Total Devices</p>
                        <p id="totalDevices" class="text-2xl font-bold">0</p>
                    </div>
                    <div class="bg-green-50 p-3 rounded">
                        <p class="text-500">Online</p>
                        <p id="onlineDevices" class="text-2xl font-bold">0</p>
                    </div>
                    <div class="bg-red-50 p-3 rounded">
                        <p class="text-gray-500">Stolen</p>
                        <p id="stolenDevices" class="text-2xl font-bold">0</p>
                    </div>
                    <div class="bg-yellow-50 p-3 rounded">
                        <p class="text-gray-500">Reports</p>
                        <p id="totalReports" class="text-2xl font-bold">0</p>
                    </div>
                </div>
            </div>

            <!-- Device Map -->
            <div class="lg:col-span-2 bg-white rounded-lg shadow p-6">
                <h2 class="text-xl font-semibold mb-4">Device Locations</h2>
                <div id="map"></div>
            </div>
        </div>

        <!-- Device List -->
        <div class="mt-8 bg-white rounded-lg shadow overflow-hidden">
            <h2 class="text-xl font-semibold p-6 border-b">All Devices</h2>
            <div id="deviceList" class="divide-y">
                <!-- Devices will be loaded here -->
            </div>
        </div>
    </div>

    <!-- Device Details Modal -->
    <div id="deviceModal" class="fixed inset-0 bg-black bg-opacity-50 hidden items-center justify-center z-50 p-4">
        <div class="bg-white rounded-lg w-full max-w-3xl max-h-[90vh] overflow-y-auto">
            <div class="p-4 border-b flex justify-between items-center">
                <h3 id="modalTitle" class="text-xl font-semibold">Device Details</h3>
                <button onclick="closeModal()" class="text-gray-500 hover:text-gray-700">✕</button>
            </div>
            <div class="p-4">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                    <div>
                        <p class="font-medium">Device ID:</p>
                        <p id="detailDeviceId" class="break-all"></p>
                    </div>
                    <div>
                        <p class="font-medium">Last Seen:</p>
                        <p id="detailLastSeen"></p>
                    </div>
                    <div>
                        <p class="font-medium">Status:</p>
                        <p id="detailStatus"></p>
                    </div>
                    <div>
                        <p class="font-medium">Stolen:</p>
                        <p id="detailStolen"></p>
                    </div>
                    <div class="md:col-span-2">
                        <p class="font-medium">Location:</p>
                        <p id="detailLocation"></p>
                    </div>
                </div>

                <div class="flex space-x-4 mb-6">
                    <button onclick="sendCommand('lock')" class="bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600">
                        Lock Device
                    </button>
                    <button onclick="sendCommand('wipe')" class="bg-orange-500 text-white px-4 py-2 rounded hover:bg-orange-600">
                        Wipe Data
                    </button>
                    <button onclick="sendCommand('locate')" class="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">
                        Locate Device
                    </button>
                </div>

                <h4 class="font-medium mb-2">Recent Reports</h4>
                <div id="reportsContainer" class="space-y-2">
                    <!-- Reports will be loaded here -->
                </div>
            </div>
        </div>
    </div>

    <script>
        // Initialize
        const socket = io();
        let currentDeviceId = null;
        let map, deviceMarkers = {};
        let sechabaMarker = null;
        let connectionLines = [];
        let devicePaths = {}; // To store polylines for device movement

        // Custom icon for Sechaba's Endpoint
        const sechabaIcon = L.divIcon({
            className: 'sechaba-marker',
            iconSize: [20, 20],
            html: '<div style="background-color: red; width: 100%; height: 100%; border-radius: 50%;"></div>'
        });

        // Custom icon for online devices (green)
        const onlineIcon = L.divIcon({
            className: 'online-marker',
            iconSize: [20, 20],
            html: '<div style="background-color: green; width: 100%; height: 100%; border-radius: 50%;"></div>'
        });

        // Custom icon for stolen devices (red)
        const stolenIcon = L.divIcon({
            className: 'stolen-marker',
            iconSize: [20, 20],
            html: '<div style="background-color: red; width: 100%; height: 100%; border-radius: 50%;"></div>'
        });

        // Haversine formula in JS to get distance in km
        function haversine(lat1, lon1, lat2, lon2) {
            const R = 6371; // Earth radius in km
            const dLat = (lat2 - lat1) * Math.PI / 180;
            const dLon = (lon2 - lon1) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                      Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            return R * c; // distance in km
        }

        // Connect to WebSocket for real-time updates
        socket.on('connect', () => {
            console.log('Connected to server');
            fetchDevices();
            // Request browser's location for Sechaba's Endpoint
            if (navigator.geolocation) {
                navigator.geolocation.watchPosition(updateSechabaLocation, (err) => {
                    console.warn("Geolocation error for Sechaba's Endpoint:", err);
                    alert("Could not get your current location. Sechaba's Endpoint will not be shown.");
                }, {enableHighAccuracy:true, maximumAge:5000, timeout:10000});
            } else {
                alert("Geolocation not supported by your browser. Sechaba's Endpoint will not be shown.");
            }
        });

        // Handle incoming reports
        socket.on('new_report', (data) => {
            console.log('New report:', data);
            fetchDevices(); // Refresh device list and map
            if (currentDeviceId === data.device_id) {
                loadDeviceDetails(currentDeviceId); // Refresh details if modal is open
            }
        });

        // Handle device status updates (e.g., from commands)
        socket.on('device_status', (data) => {
            console.log('Device status update:', data);
            fetchDevices(); // Refresh device list and map
            if (currentDeviceId === data.device_id) {
                loadDeviceDetails(currentDeviceId);
            }
        });

        // Update Sechaba's Endpoint location
        function updateSechabaLocation(position) {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;

            if (sechabaMarker) {
                sechabaMarker.setLatLng([lat, lon]);
            } else {
                sechabaMarker = L.marker([lat, lon], { icon: sechabaIcon }).addTo(map)
                    .bindPopup("<b>Sechaba's Endpoint</b><br>Your current location.");
            }
            // Update lines to devices
            updateConnectionLines();
        }

        // Initialize Leaflet map
        function initMap() {
            map = L.map('map').setView([0, 0], 2);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            }).addTo(map);

            map.on('click', function(e) {
                console.log('Map clicked at:', e.latlng);
            });
        }

        // Fetch all devices
        function fetchDevices() {
            fetch('/api/devices')
                .then(res => res.json())
                .then(data => {
                    updateDevicesUI(data);
                    updateMapMarkers(data);
                    updateStats(data);
                    updateConnectionLines(); // Update lines after devices are fetched
                })
                .catch(error => console.error('Error fetching devices:', error));
        }

        // Update devices list
        function updateDevicesUI(devices) {
            const deviceList = document.getElementById('deviceList');
            deviceList.innerHTML = '';

            if (devices.length === 0) {
                deviceList.innerHTML = '<p class="p-4 text-gray-500">No devices registered yet.</p>';
                return;
            }

            devices.forEach(device => {
                const card = document.createElement('div');
                card.className = `p-4 device-card transition cursor-pointer ${device.stolen ? 'bg-red-50' : ''}`;
                card.innerHTML = `
                    <div class="flex justify-between items-center">
                        <div>
                            <p class="font-medium">${device.name || 'Unnamed Device'}</p>
                            <p class="text-sm text-gray-500">${device.id.slice(0, 8)}... | ${device.owner || 'No owner'}</p>
                        </div>
                        <div class="text-right">
                            <p class="${getStatusColor(device.status)} text-sm">${device.status}</p>
                            <p class="text-xs text-gray-500">${formatTime(device.last_seen)}</p>
                        </div>
                    </div>
                `;

                card.addEventListener('click', () => {
                    currentDeviceId = device.id;
                    openModal(device);
                });

                deviceList.appendChild(card);
            });
        }

        // Update map markers for devices and draw paths
        function updateMapMarkers(devices) {
            // Clear existing markers
            Object.values(deviceMarkers).forEach(marker => marker.remove());
            deviceMarkers = {};

            // Clear existing paths
            Object.values(devicePaths).forEach(path => map.removeLayer(path));
            devicePaths = {};

            let hasMarkers = false;
            devices.forEach(device => {
                if (device.lat && device.lng) {
                    const icon = device.stolen ? stolenIcon : onlineIcon;
                    const marker = L.marker([device.lat, device.lng], { icon: icon }).addTo(map);
                    marker.bindPopup(`<b>${device.name || 'Device'}</b><br>Status: ${device.status}<br>Last Seen: ${formatTime(device.last_seen)}`);
                    deviceMarkers[device.id] = marker;
                    hasMarkers = true;

                    // Fetch and draw device path
                    fetch(`/api/reports/${device.id}`)
                        .then(res => res.json())
                        .then(reports => {
                            const latlngs = reports
                                .filter(r => r.type === 'location' && r.data && r.data.lat && r.data.lng)
                                .map(r => [r.data.lat, r.data.lng]);

                            if (latlngs.length > 1) {
                                const pathColor = device.stolen ? 'red' : 'blue';
                                const path = L.polyline(latlngs, { color: pathColor, weight: 3, opacity: 0.7 }).addTo(map);
                                devicePaths[device.id] = path;
                            }
                        })
                        .catch(error => console.error(`Error fetching reports for device ${device.id}:`, error));
                }
            });

            // Fit map to show all markers if any exist, including Sechaba's marker
            const allMarkers = Object.values(deviceMarkers);
            if (sechabaMarker) {
                allMarkers.push(sechabaMarker);
            }

            if (allMarkers.length > 0) {
                const group = new L.featureGroup(allMarkers);
                map.fitBounds(group.getBounds(), { padding: [50, 50] });
            } else {
                map.setView([0, 0], 2);
            }
        }

        // Update lines connecting Sechaba's Endpoint to devices
        function updateConnectionLines() {
            // Clear existing lines
            connectionLines.forEach(line => map.removeLayer(line));
            connectionLines = [];

            if (!sechabaMarker) return; // No Sechaba's endpoint to draw from

            const sechabaLat = sechabaMarker.getLatLng().lat;
            const sechabaLon = sechabaMarker.getLatLng().lng;

            Object.values(deviceMarkers).forEach(marker => {
                const deviceLat = marker.getLatLng().lat;
                const deviceLon = marker.getLatLng().lng;
                const deviceId = Object.keys(deviceMarkers).find(key => deviceMarkers[key] === marker); // Get device ID from marker

                // We need the full device object to check 'stolen' status.
                // This is a simplified approach; in a real app, you'd have a cached list of devices.
                fetch(`/api/devices/${deviceId}`) // Fetch single device details
                    .then(res => res.json())
                    .then(device => {
                        if (device) {
                            const distance = haversine(sechabaLat, sechabaLon, deviceLat, deviceLon);
                            let lineColor = 'blue';
                            let lineWeight = 2;
                            let lineDashArray = '5, 5'; // Broken line
                            let lineClass = '';

                            if (device.stolen) {
                                lineColor = 'red';
                                lineWeight = 3; // Thicker for stolen
                                lineDashArray = null; // Solid line
                                lineClass = 'stolen-line'; // Apply animation class
                            }

                            const line = L.polyline([[sechabaLat, sechabaLon], [deviceLat, deviceLon]], {
                                color: lineColor,
                                weight: lineWeight,
                                dashArray: lineDashArray,
                                className: lineClass // Apply class for animation
                            }).addTo(map);
                            connectionLines.push(line);

                            // Update popup for device marker to include distance
                            marker.setPopupContent(`<b>${device.name || 'Device'}</b><br>Status: ${device.status}<br>Last Seen: ${formatTime(device.last_seen)}<br>Distance from Sechaba: ${distance.toFixed(2)} km`);
                        }
                    })
                    .catch(error => console.error(`Error fetching device ${deviceId} for line drawing:`, error));
            });
        }

        // Helper to get device object by ID (client-side cache for performance)
        let cachedDevices = [];
        function getDeviceById(id) {
            return cachedDevices.find(d => d.id === id);
        }

        // Update stats
        function updateStats(devices) {
            cachedDevices = devices; // Cache devices for getDeviceById
            document.getElementById('totalDevices').textContent = devices.length;
            document.getElementById('onlineDevices').textContent = devices.filter(d => d.status === 'online').length;
            document.getElementById('stolenDevices').textContent = devices.filter(d => d.stolen).length;

            // Note: totalReports is not directly available from /api/devices.
            // It would require a separate API call or a count passed from the server.
            // For now, it will remain 0 unless you implement that.
        }

        // Modal functions
        function openModal(device) {
            document.getElementById('modalTitle').textContent = device.name || 'Device Details';
            document.getElementById('detailDeviceId').textContent = device.id;
            document.getElementById('detailLastSeen').textContent = formatTime(device.last_seen);
            document.getElementById('detailStatus').textContent = device.status;
            document.getElementById('detailStolen').textContent = device.stolen ? 'Yes ⚠️' : 'No';
            document.getElementById('detailLocation').textContent = device.lat && device.lng ?
                `${device.lat.toFixed(4)}, ${device.lng.toFixed(4)}` : 'Unknown';

            loadDeviceDetails(device.id);
            document.getElementById('deviceModal').classList.remove('hidden');
        }

        function closeModal() {
            document.getElementById('deviceModal').classList.add('hidden');
            currentDeviceId = null; // Clear current device when modal closes
        }

        function loadDeviceDetails(deviceId) {
            fetch(`/api/reports/${deviceId}`)
                .then(res => res.json())
                .then(reports => {
                    const container = document.getElementById('reportsContainer');
                    container.innerHTML = '';

                    if (reports.length === 0) {
                        container.innerHTML = '<p class="text-gray-500">No reports available</p>';
                        return;
                    }

                    reports.forEach(report => {
                        const reportDiv = document.createElement('div');
                        reportDiv.className = 'p-3 border rounded';

                        let content = '';
                        if (report.type === 'location') {
                            content = `📍 Location update: ${report.data.lat}, ${report.data.lng}`;
                        } else if (report.type === 'photo') {
                            content = `📸 Photo captured: ${report.data.filename || 'N/A'}`;
                        } else if (report.type === 'status') {
                            content = `ℹ️ Status change: ${report.data.status || 'N/A'}`;
                        } else {
                            // Fallback for unknown report types or generic data
                            content = `🔍 Data: ${JSON.stringify(report.data)}`;
                        }

                        reportDiv.innerHTML = `
                            <div class="flex justify-between items-start">
                                <div class="font-medium">${report.type}</div>
                                <div class="text-sm text-gray-500">${formatTime(report.timestamp)}</div>
                            </div>
                            <div class="mt-1 text-sm">${content}</div>
                        `;
                        container.appendChild(reportDiv);
                    });
                })
                .catch(error => {
                    console.error('Error loading device details:', error);
                    document.getElementById('reportsContainer').innerHTML = '<p class="text-red-500">Failed to load reports.</p>';
                });
        }

        // Send commands to device
        function sendCommand(command) {
            if (!currentDeviceId) {
                alert('No device selected.');
                return;
            }

            // Prompt for PIN for sensitive commands
            let pin = '';
            if (command === 'lock' || command === 'wipe') {
                pin = prompt(`Enter PIN to ${command} device:`);
                if (!pin) {
                    alert('PIN is required for this command.');
                    return;
                }
            }

            fetch(`/api/command/${currentDeviceId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: command, pin: pin })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    alert(`Error sending command: ${data.error}`);
                } else {
                    alert(`Command "${command}" sent successfully! Message: ${data.message || 'No specific message.'}`);
                    closeModal();
                    fetchDevices(); // Refresh dashboard after command
                }
            })
            .catch(err => {
                console.error('Error sending command:', err);
                alert('Failed to send command. Check console for details.');
            });
        }

        // Helper functions
        function getStatusColor(status) {
            return status === 'online' ? 'text-green-600' : 'text-red-600';
        }

        function formatTime(timestamp) {
            if (!timestamp) return 'Never';
            const date = new Date(timestamp * 1000); // Convert Unix timestamp to milliseconds
            return date.toLocaleString();
        }

        // Initialize everything when page loads
        document.addEventListener('DOMContentLoaded', () => {
            initMap();
            fetchDevices();

            // Refresh periodically
            setInterval(fetchDevices, 30000);
        });
    </script>
</body>
</html>
"""

# --- End Embedded HTML Templates ---


# Database Setup
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS devices
                 (id TEXT PRIMARY KEY, name TEXT, owner TEXT, last_seen REAL,
                  lat REAL, lng REAL, status TEXT, stolen INTEGER,
                  user_email TEXT, user_phone TEXT, show_map INTEGER, show_lines INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT, timestamp REAL,
                  report_type TEXT, data TEXT)''')
    conn.commit()
    conn.close()
    logging.info("Database initialized or already exists.")

# Email Sending Function
def send_email(subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = EMAIL_TO
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            logging.info(f"Email sent: {subject}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

# Security Functions
def encrypt_data(data):
    try:
        cipher = AES.new(SECRET_KEY, AES.MODE_CBC)
        ct_bytes = cipher.encrypt(pad(data.encode('utf-8'), AES.block_size))
        return binascii.hexlify(cipher.iv + ct_bytes).decode('ascii')
    except Exception as e:
        logging.error(f"Error encrypting data: {e}")
        return None

def decrypt_data(encrypted_data):
    try:
        data = binascii.unhexlify(encrypted_data)
        iv = data[:AES.block_size]
        ct = data[AES.block_size:]
        cipher = AES.new(SECRET_KEY, AES.MODE_CBC, iv=iv)
        return unpad(cipher.decrypt(ct), AES.block_size).decode('utf-8')
    except (binascii.Error, ValueError, KeyError) as e:
        logging.error(f"Error decrypting data: {e}")
        return None

# Authentication
@auth.verify_password
def verify_password(username, password):
    # For dashboard login and API basic auth, check against the single 'admin' user
    if username == 'admin' and check_password_hash(API_KEYS.get('admin'), password):
        logging.info(f"Authentication successful for user: {username}")
        return username
    logging.warning(f"Authentication failed for user: {username}")
    return False

# Session management for web interface
@app.before_request
def check_valid_session():
    # Allow login, status_check, and static files without session check
    if request.endpoint in ['login', 'status_check', 'static']:
        return
    # For API endpoints, check basic auth
    if request.path.startswith('/api/'):
        # If it's an API call, HTTPBasicAuth decorator will handle it
        # We don't need to redirect to login page for API calls
        return
    # For web dashboard, check session
    if not session.get('authenticated'):
        logging.debug(f"Redirecting unauthenticated web request to login: {request.path}")
        return redirect(url_for('login'))

# Location Access Check Decorator
def location_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.args.get('location_access') == 'true':
            return f(*args, **kwargs)
        else:
            logging.info("Location access not granted, serving prompt HTML.")
            return LOCATION_ACCESS_PROMPT_HTML
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Only allow 'admin' as username for dashboard login
        if username == 'admin' and verify_password(username, password):
            session['authenticated'] = True
            logging.info(f"User '{username}' logged in successfully.")
            return redirect(url_for('dashboard'))
        else:
            logging.warning(f"Failed login attempt for user: {username}")
            # You might want to add an error message to the HTML here
            return LOGIN_HTML # Re-render login page on failure
    return LOGIN_HTML

# --- Health Check Endpoint ---
@app.route('/status', methods=['GET'])
def status_check():
    logging.info("Status check requested.")
    return jsonify({"status": "online"}), 200

# Device Communication Endpoints
@app.route('/api/register', methods=['POST'])
@auth.login_required # <--- This endpoint now requires basic auth
def register_device():
    data = request.json
    device_id = data.get('device_id')
    if not device_id:
        logging.warning("Registration attempt with missing device_id.")
        return jsonify({"error": "Missing device_id"}), 400

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM devices WHERE id=?", (device_id,))
        existing_device = c.fetchone()

        current_time = time.time()
        device_name = data.get('name', 'Unnamed Device')
        device_owner = data.get('owner', 'Unknown')
        device_lat = data.get('lat', 0)
        device_lng = data.get('lng', 0)
        device_status = 'online'
        device_stolen = 0 # Default to not stolen on registration/update
        device_email = data.get('user_email')
        device_phone = data.get('user_phone')
        device_show_map = data.get('show_map', 0)
        device_show_lines = data.get('show_lines', 0)

        if existing_device:
            # Update existing device
            c.execute("""UPDATE devices SET
                         name=?, owner=?, last_seen=?, lat=?, lng=?, status=?, stolen=?,
                         user_email=?, user_phone=?, show_map=?, show_lines=?
                         WHERE id=?""",
                      (device_name, device_owner, current_time, device_lat, device_lng, device_status, device_stolen,
                       device_email, device_phone, device_show_map, device_show_lines,
                       device_id))
            conn.commit()
            logging.info(f"Device {device_id} updated successfully.")
            return jsonify({"status": "success", "message": "Device updated successfully"}), 200
        else:
            # Insert new device
            c.execute("""INSERT INTO devices
                         (id, name, owner, last_seen, lat, lng, status, stolen,
                          user_email, user_phone, show_map, show_lines)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (device_id, device_name, device_owner, current_time, device_lat, device_lng, device_status, device_stolen,
                       device_email, device_phone, device_show_map, device_show_lines))
            conn.commit()
            logging.info(f"Device {device_id} registered successfully.")
            return jsonify({"status": "success", "message": "Device registered successfully"}), 201
    except Exception as e:
        logging.critical(f"Unhandled error during device registration for {device_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        conn.close()

@app.route('/api/report', methods=['POST'])
@auth.login_required
def receive_report():
    device_id = None
    report_type = None
    report_data = {}

    if request.is_json:
        data = request.json
        device_id = data.get('device_id')
        report_type = data.get('type')
        report_data = data.get('data', {})
    elif 'json_data' in request.form:
        try:
            data = json.loads(request.form['json_data'])
            device_id = data.get('device_id')
            report_type = data.get('type')
            report_data = data.get('data', {})
        except json.JSONDecodeError:
            logging.warning("Invalid JSON data in 'json_data' field of multipart report.")
            return jsonify({"error": "Invalid JSON data in multipart report"}), 400
    else:
        logging.warning("Report received with unsupported content type.")
        return jsonify({"error": "Unsupported content type"}), 400

    if not device_id or not report_type:
        logging.warning(f"Missing device_id or report_type in report from {device_id}.")
        return jsonify({"error": "Missing device_id or report_type"}), 400

    logging.info(f"Received report from device {device_id}, type: {report_type}")

    if 'files' in request.files:
        uploaded_files = []
        for key, f in request.files.items():
            if key.startswith('files'):
                filename = f.filename
                upload_dir = os.path.join(app.root_path, 'uploads', device_id)
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, filename)
                f.save(file_path)
                uploaded_files.append(filename)
                logging.info(f"Saved uploaded file: {file_path}")
        report_data['uploaded_files'] = uploaded_files

    encrypted_data = encrypt_data(json.dumps(report_data))
    if encrypted_data is None:
        return jsonify({"error": "Failed to encrypt report data"}), 500

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    current_time = time.time()
    if 'lat' in report_data and 'lng' in report_data:
        c.execute("UPDATE devices SET lat=?, lng=?, last_seen=?, status=? WHERE id=?",
                (report_data['lat'], report_data['lng'], current_time, 'online', device_id))
    else:
        c.execute("UPDATE devices SET last_seen=?, status=? WHERE id=?",
                (current_time, 'online', device_id))

    c.execute("INSERT INTO reports (device_id, timestamp, report_type, data) VALUES (?, ?, ?, ?)",
             (device_id, current_time, report_type, encrypted_data))

    conn.commit()
    conn.close()

    socketio.emit('new_report', {'device_id': device_id, 'type': report_type, 'data': report_data})
    # Send email notification for new reports
    send_email(f"New Report from Device: {device_id}", f"Report Type: {report_type}\nData: {report_data}")
    logging.info(f"Report from {device_id} processed and WebSocket event emitted.")
    return jsonify({"status": "received", "message": "Report processed successfully"})

# Remote Commands with PIN Verification
@app.route('/api/command/<device_id>', methods=['POST'])
@auth.login_required
def send_command(device_id):
    command = request.json.get('command')
    pin = request.json.get('pin')

    # IMPORTANT: For production, the PIN should be more secure (e.g., hashed, environment variable)
    if pin != '3241': # Example PIN - CHANGE THIS FOR PRODUCTION
        logging.warning(f"Invalid PIN attempt for command '{command}' on device {device_id}.")
        return jsonify({"error": "Invalid PIN"}), 403

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    if command == 'lock':
        c.execute("UPDATE devices SET stolen=1 WHERE id=?", (device_id,))
        conn.commit()
        socketio.emit('device_status', {'device_id': device_id, 'status': 'locked', 'stolen': True})
        logging.info(f"Lock command sent to device {device_id}. Device marked as stolen.")
        send_email(f"Device {device_id} Locked!", f"The device {device_id} has been marked as stolen and locked.")
        return jsonify({"command": "lock", "status": "sent", "message": "Lock command sent. Device marked as stolen."})

    elif command == 'wipe':
        socketio.emit('device_command', {'device_id': device_id, 'command': 'wipe'})
        logging.info(f"Wipe command sent to device {device_id}.")
        send_email(f"Wipe Command Sent to Device: {device_id}", f"A wipe command has been sent to device {device_id}.")
        return jsonify({"command": "wipe", "status": "sent", "message": "Wipe command sent."})

    elif command == 'locate':
        socketio.emit('device_command', {'device_id': device_id, 'command': 'locate'})
        logging.info(f"Locate command sent to device {device_id}.")
        send_email(f"Locate Command Sent to Device: {device_id}", f"A locate command has been sent to device {device_id}.")
        return jsonify({"command": "locate", "status": "sent", "message": "Locate command sent."})

    conn.close()
    logging.warning(f"Invalid command '{command}' received for device {device_id}.")
    return jsonify({"error": "Invalid command"}), 400

# Web Interface
@app.route('/')
@auth.login_required # <--- Dashboard now requires basic auth
@location_access_required
def dashboard():
    logging.info("Dashboard requested.")
    return DASHBOARD_HTML

@app.route('/api/devices')
@auth.login_required
def get_devices():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT id, name, owner, last_seen, lat, lng, status, stolen, user_email, user_phone, show_map, show_lines FROM devices")
    devices = [dict(zip(['id', 'name', 'owner', 'last_seen', 'lat', 'lng', 'status', 'stolen', 'user_email', 'user_phone', 'show_map', 'show_lines'], row))
              for row in c.fetchall()]
    conn.close()
    logging.info(f"Fetched {len(devices)} devices for dashboard.")
    return jsonify(devices)

@app.route('/api/devices/<device_id>')
@auth.login_required
def get_single_device(device_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT id, name, owner, last_seen, lat, lng, status, stolen, user_email, user_phone, show_map, show_lines FROM devices WHERE id=?", (device_id,))
    device = c.fetchone()
    conn.close()
    if device:
        device_dict = dict(zip(['id', 'name', 'owner', 'last_seen', 'lat', 'lng', 'status', 'stolen', 'user_email', 'user_phone', 'show_map', 'show_lines'], device))
        logging.info(f"Fetched single device {device_id}.")
        return jsonify(device_dict)
    else:
        logging.warning(f"Device {device_id} not found.")
        return jsonify({"error": "Device not found"}), 404


@app.route('/api/reports/<device_id>')
@auth.login_required
def get_reports(device_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT id, timestamp, report_type, data FROM reports WHERE device_id=? ORDER BY timestamp DESC LIMIT 50", (device_id,))
    reports = []

    for row in c.fetchall():
        report_data = {"error": "Could not decrypt/parse report data"}
        if row[3]:
            decrypted_data_str = decrypt_data(row[3])
            if decrypted_data_str:
                try:
                    report_data = json.loads(decrypted_data_str)
                except json.JSONDecodeError as e:
                    logging.error(f"JSON decode error for report ID {row[0]}: {e}")
            else:
                logging.error(f"Decryption failed for report ID {row[0]}.")

        reports.append({
            'id': row[0],
            'timestamp': row[1],
            'type': row[2],
            'data': report_data
        })
    conn.close()
    logging.info(f"Fetched {len(reports)} reports for device {device_id}.")
    return jsonify(reports)

# --- Socket.IO Event Handlers ---
@socketio.on('connect')
def handle_connect():
    logging.info(f"Socket.IO client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    logging.info(f"Socket.IO client disconnected: {request.sid}")

@socketio.on('register_tracker')
def handle_register_tracker(data):
    device_id = data.get('device_id')
    os_type = data.get('os_type')
    logging.info(f"Tracker registered via Socket.IO: Device ID={device_id}, OS={os_type}, SID={request.sid}")

@socketio.on('command_status')
def handle_command_status(data):
    device_id = data.get('device_id')
    command = data.get('command')
    status = data.get('status')
    message = data.get('message')
    logging.info(f"Command status from {device_id}: Command='{command}', Status='{status}', Message='{message}'")


if __name__ == '__main__':
    init_db()
    logging.info("Starting Flask Socket.IO server...")

    FLASK_PORT = 5000
    # IMPORTANT: Replace with your actual ngrok authtoken and reserved domain
    # Get your authtoken from https://dashboard.ngrok.com/get-started/your-authtoken
    # Reserve a domain from https://dashboard.ngrok.com/cloud-edge/domains
    NGROK_AUTH_TOKEN = "30PPW8XZTo9DvacbMhg40j7xQsf_uPL3JznTMwNJtozuEd5S"
    NGROK_DOMAIN = "meet-primate-gladly.ngrok-free.app"

    try:
        # Check if ngrok is installed and available in PATH
        # Adjust the path to ngrok.exe if it's not in your system's PATH
        ngrok_executable_path = r"C:\ngrok\ngrok.exe" # Example path for Windows
        if not os.path.exists(ngrok_executable_path):
            logging.warning(f"ngrok executable not found at {ngrok_executable_path}. Trying system PATH.")
            ngrok_executable_path = "ngrok" # Fallback to system PATH

        subprocess.run([ngrok_executable_path, "version"], check=True, capture_output=True)
        logging.info("ngrok executable found.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.error("ngrok executable not found. Please install ngrok and ensure it's in your system's PATH or update ngrok_executable_path.")
        logging.error("Download from: https://ngrok.com/download")
        logging.error("Exiting. Cannot start ngrok tunnel without ngrok executable.")
        exit(1) # Exit if ngrok is not found

    public_url = None
    try:
        conf.get_default().auth_token = NGROK_AUTH_TOKEN
        logging.info("ngrok authtoken configured.")

        # Start ngrok tunnel with the reserved domain
        # If you don't have a reserved domain, remove the 'domain' argument
        # and ngrok will assign a random one.
        public_url = ngrok.connect(FLASK_PORT, domain=NGROK_DOMAIN).public_url
        logging.info(f"ngrok tunnel established: {public_url}")

        print(f"\n--- Sechaba's Tracker Dashboard Accessible At ---")
        print(f"Dashboard URL: {public_url}")
        print(f"API Endpoint for Trackers: {public_url}/api/register")
        print(f"--------------------------------------------------\n")

    except Exception as e:
        logging.critical(f"Failed to start ngrok tunnel: {e}", exc_info=True)
        print("\n--- NGROK ERROR ---")
        print("Failed to start ngrok tunnel. Please ensure:")
        print(f"1. ngrok is installed and its executable is in your system's PATH or 'ngrok_executable_path' is correct.")
        print(f"2. Your authtoken '{NGROK_AUTH_TOKEN}' is correct and added to ngrok config (run 'ngrok config add-authtoken {NGROK_AUTH_TOKEN}' in CMD/PowerShell).")
        print(f"3. The reserved domain '{NGROK_DOMAIN}' is correctly configured in your ngrok dashboard and available.")
        print("The Flask server will still run locally, but won't be accessible externally.")
        print("-------------------\n")
        # Continue to run Flask app locally even if ngrok fails

    # Run the Flask-SocketIO app
    socketio.run(
        app,
        host='0.0.0.0',
        port=FLASK_PORT,
        debug=True # Set to False in production
    )
