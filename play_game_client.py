import socket
import time

class GameClient:
    def __init__(self, server_ip, server_port):
        self.server_ip = server_ip
        self.server_port = server_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_connected = False

    def connect(self):
        try:
            self.socket.connect((self.server_ip, self.server_port))
            self.is_connected = True
            print("Connected to the server.")
        except socket.error as e:
            print(f"Connection failed: {e}")

    def send_message(self, message):
        if self.is_connected:
            self.socket.sendall(message.encode())
            print("Message sent to the server.")
        else:
            print("Not connected to the server.")
            self.send_offline_notification(message)

    def send_offline_notification(self, message):
        print("Sending offline meeting notification...")
        # logic to send the notification could go here

    def disconnect(self):
        self.socket.close()
        self.is_connected = False
        print("Disconnected from the server.")

# Example usage:
if __name__ == '__main__':
    client = GameClient('127.0.0.1', 12345)  # Replace with the actual server IP and port
    client.connect()
    while True:
        msg = input("Enter message to send: ")
        client.send_message(msg)
        time.sleep(1)  # Simulating operation time
        if msg.lower() == 'exit':
            break
    client.disconnect()