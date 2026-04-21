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

"hahaha ...endpoint closed..access everything on my website"

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
