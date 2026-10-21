"""
FCM Receiver Library
A Python library for receiving Firebase Cloud Messages.
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .fcm_client import FCMClient
from .exceptions import FCMReceiverError

__all__ = ["FCMClient", "FCMReceiverError"]
