import socket

try:
    print("Creating connection...")
    socket.create_connection(("smtp.ionos.co.uk", 587), timeout=10)
    print("Connection successful")
except Exception as e:
    print(f"Connection failed: {e}")