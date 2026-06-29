"""
Game Client Module

A robust TCP socket client for communicating with a game server.
Includes connection management, error handling, and graceful disconnection.
"""

import socket
import logging
import sys
from typing import Optional
from contextlib import contextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GameClientError(Exception):
    """Base exception for GameClient errors."""
    pass


class ConnectionError(GameClientError):
    """Raised when connection-related errors occur."""
    pass


class GameClient:
    """
    A TCP socket client for game server communication.
    
    Attributes:
        server_ip (str): The server's IP address
        server_port (int): The server's port number
        socket (socket.socket): The socket instance
        is_connected (bool): Connection status
        timeout (float): Socket timeout in seconds
    """

    def __init__(self, server_ip: str, server_port: int, timeout: float = 5.0):
        """
        Initialize the GameClient.
        
        Args:
            server_ip (str): Server IP address
            server_port (int): Server port number
            timeout (float): Socket timeout in seconds (default: 5.0)
        
        Raises:
            ValueError: If port is invalid
        """
        if not 0 < server_port < 65536:
            raise ValueError(f"Port must be between 1 and 65535, got {server_port}")
        
        self.server_ip = server_ip
        self.server_port = server_port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self.is_connected = False

    def connect(self) -> bool:
        """
        Establish connection to the server.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.server_ip, self.server_port))
            self.is_connected = True
            logger.info(f"Connected to server at {self.server_ip}:{self.server_port}")
            return True
        except socket.timeout:
            logger.error(f"Connection timeout after {self.timeout}s")
            self._cleanup_socket()
            return False
        except socket.gaierror as e:
            logger.error(f"Failed to resolve hostname: {e}")
            self._cleanup_socket()
            return False
        except socket.error as e:
            logger.error(f"Connection failed: {e}")
            self._cleanup_socket()
            return False

    def send_message(self, message: str) -> bool:
        """
        Send a message to the server.
        
        Args:
            message (str): Message to send
        
        Returns:
            bool: True if message sent successfully, False otherwise
        """
        if not message or not message.strip():
            logger.warning("Attempted to send empty message")
            return False

        if self.is_connected and self.socket:
            try:
                self.socket.sendall(message.encode('utf-8'))
                logger.info(f"Message sent: {message}")
                return True
            except socket.error as e:
                logger.error(f"Failed to send message: {e}")
                self.is_connected = False
                self._cleanup_socket()
                return False
        else:
            logger.warning("Not connected to server")
            self.send_offline_notification(message)
            return False

    def receive_message(self, buffer_size: int = 1024) -> Optional[str]:
        """
        Receive a message from the server.
        
        Args:
            buffer_size (int): Maximum bytes to receive (default: 1024)
        
        Returns:
            Optional[str]: Received message or None if no data
        """
        if not self.is_connected or not self.socket:
            logger.error("Cannot receive: not connected to server")
            return None

        try:
            data = self.socket.recv(buffer_size)
            if data:
                message = data.decode('utf-8')
                logger.info(f"Message received: {message}")
                return message
            else:
                logger.info("Server closed connection")
                self.is_connected = False
                return None
        except socket.timeout:
            logger.warning("Receive timeout")
            return None
        except socket.error as e:
            logger.error(f"Failed to receive message: {e}")
            self.is_connected = False
            self._cleanup_socket()
            return None
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode message: {e}")
            return None

    def send_offline_notification(self, message: str) -> None:
        """
        Handle offline message notification.
        
        Args:
            message (str): The message that couldn't be sent
        """
        logger.warning(f"Message queued for offline delivery: {message}")
        # TODO: Implement queue/cache logic for offline messages

    def disconnect(self) -> None:
        """Close the connection to the server gracefully."""
        if self.is_connected:
            try:
                self.send_message("EXIT")  # Send exit signal to server if desired
            except Exception as e:
                logger.warning(f"Error sending exit signal: {e}")
        
        self._cleanup_socket()
        self.is_connected = False
        logger.info("Disconnected from server")

    def _cleanup_socket(self) -> None:
        """Clean up socket resources."""
        if self.socket:
            try:
                self.socket.close()
            except socket.error as e:
                logger.error(f"Error closing socket: {e}")
            finally:
                self.socket = None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.disconnect()
        return False


@contextmanager
def game_client_session(server_ip: str, server_port: int, timeout: float = 5.0):
    """
    Context manager for GameClient session.
    
    Args:
        server_ip (str): Server IP address
        server_port (int): Server port number
        timeout (float): Socket timeout in seconds
    
    Yields:
        GameClient: Connected client instance
    """
    client = GameClient(server_ip, server_port, timeout)
    try:
        if client.connect():
            yield client
        else:
            raise ConnectionError("Failed to establish connection")
    finally:
        client.disconnect()


def main() -> None:
    """Main client loop with interactive messaging."""
    server_ip = '127.0.0.1'
    server_port = 12345
    
    try:
        with game_client_session(server_ip, server_port) as client:
            logger.info("Connected to game server. Type 'exit' to quit.")
            
            while True:
                try:
                    msg = input("Enter message to send (or 'exit' to quit): ").strip()
                    
                    if msg.lower() == 'exit':
                        logger.info("Exiting...")
                        break
                    
                    if msg:
                        client.send_message(msg)
                        # Optional: wait for response
                        # response = client.receive_message()
                        # if response:
                        #     print(f"Server response: {response}")
                    else:
                        logger.warning("Empty message ignored")
                
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in main loop: {e}")
                    break
    
    except ConnectionError as e:
        logger.error(f"Connection error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
