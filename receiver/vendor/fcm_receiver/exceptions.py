"""
FCM Receiver exceptions
"""


class FCMReceiverError(Exception):
    """Base exception for FCM Receiver"""
    pass


class CredentialsError(FCMReceiverError):
    """Exception raised for credentials-related errors"""
    pass


class SubscriptionError(FCMReceiverError):
    """Exception raised for subscription-related errors"""
    pass


class ConnectionError(FCMReceiverError):
    """Exception raised for connection-related errors"""
    pass
