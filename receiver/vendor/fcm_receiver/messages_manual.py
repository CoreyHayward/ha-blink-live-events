from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# Enums (minimal needed)
class DeviceType:
    DEVICE_ANDROID_OS = 1
    DEVICE_IOS_OS = 2
    DEVICE_CHROME_BROWSER = 3
    DEVICE_CHROME_OS = 4


class ChromePlatform:
    PLATFORM_WIN = 1
    PLATFORM_MAC = 2
    PLATFORM_LINUX = 3
    PLATFORM_CROS = 4
    PLATFORM_IOS = 5
    PLATFORM_ANDROID = 6


class ChromeChannel:
    CHANNEL_STABLE = 1
    CHANNEL_BETA = 2
    CHANNEL_DEV = 3
    CHANNEL_CANARY = 4
    CHANNEL_UNKNOWN = 5


class LoginAuthService:
    ANDROID_ID = 2


class IqType:
    GET = 0
    SET = 1
    RESULT = 2
    IQ_ERROR = 3


@dataclass
class ChromeBuildProto:
    platform: Optional[int] = None
    chrome_version: Optional[str] = None
    channel: Optional[int] = None


@dataclass
class AndroidCheckinProto:
    last_checkin_msec: Optional[int] = None
    cell_operator: Optional[str] = None
    sim_operator: Optional[str] = None
    roaming: Optional[str] = None
    user_number: Optional[int] = None
    type: Optional[int] = None
    chrome_build: Optional[ChromeBuildProto] = None


@dataclass
class GservicesSetting:
    name: bytes = b""
    value: bytes = b""


@dataclass
class AndroidCheckinRequest:
    # subset used
    imei: Optional[str] = None
    meid: Optional[str] = None
    mac_addr: List[str] = field(default_factory=list)
    mac_addr_type: List[str] = field(default_factory=list)
    serial_number: Optional[str] = None
    esn: Optional[str] = None
    id: Optional[int] = None
    logging_id: Optional[int] = None
    digest: Optional[str] = None
    locale: Optional[str] = None
    checkin: Optional[AndroidCheckinProto] = None
    desired_build: Optional[str] = None
    market_checkin: Optional[str] = None
    account_cookie: List[str] = field(default_factory=list)
    time_zone: Optional[str] = None
    security_token: Optional[int] = None
    version: Optional[int] = None
    ota_cert: List[str] = field(default_factory=list)
    fragment: Optional[int] = None
    user_name: Optional[str] = None
    user_serial_number: Optional[int] = None


@dataclass
class AndroidCheckinResponse:
    stats_ok: Optional[bool] = None
    time_msec: Optional[int] = None
    digest: Optional[str] = None
    settings_diff: Optional[bool] = None
    delete_setting: List[str] = field(default_factory=list)
    setting: List[GservicesSetting] = field(default_factory=list)
    market_ok: Optional[bool] = None
    android_id: Optional[int] = None
    security_token: Optional[int] = None
    version_info: Optional[str] = None


@dataclass
class HeartbeatPing:
    pass


@dataclass
class HeartbeatAck:
    pass


@dataclass
class ErrorInfo:
    code: Optional[int] = None
    message: Optional[str] = None
    type: Optional[str] = None


@dataclass
class Setting:
    name: str = ""
    value: str = ""


@dataclass
class HeartbeatStat:
    ip: str = ""
    timeout: bool = False
    interval_ms: int = 0


@dataclass
class HeartbeatConfig:
    upload_stat: Optional[bool] = None
    ip: Optional[str] = None
    interval_ms: Optional[int] = None


@dataclass
class ClientEvent:
    type: Optional[int] = None
    number_discarded_events: Optional[int] = None
    network_type: Optional[int] = None
    time_connection_started_ms: Optional[int] = None
    time_connection_ended_ms: Optional[int] = None
    error_code: Optional[int] = None
    time_connection_established_ms: Optional[int] = None


@dataclass
class LoginRequest:
    id: str = ""
    domain: str = ""
    user: str = ""
    resource: str = ""
    auth_token: str = ""
    device_id: str = ""
    last_rmq_id: Optional[int] = None
    setting: List[Setting] = field(default_factory=list)
    received_persistent_id: List[str] = field(default_factory=list)
    adaptive_heartbeat: Optional[bool] = None
    heartbeat_stat: Optional[HeartbeatStat] = None
    use_rmq2: Optional[bool] = None
    account_id: Optional[int] = None
    auth_service: Optional[int] = None
    network_type: Optional[int] = None
    status: Optional[int] = None
    client_event: List[ClientEvent] = field(default_factory=list)


@dataclass
class LoginResponse:
    id: Optional[str] = None
    jid: Optional[str] = None
    error: Optional[ErrorInfo] = None
    setting: List[Setting] = field(default_factory=list)
    stream_id: Optional[int] = None
    last_stream_id_received: Optional[int] = None
    heartbeat_config: Optional[HeartbeatConfig] = None
    server_timestamp: Optional[int] = None


@dataclass
class Close:
    pass


@dataclass
class StreamErrorStanza:
    type: Optional[str] = None
    text: Optional[str] = None


@dataclass
class Extension:
    id: Optional[int] = None
    data: bytes = b""


@dataclass
class IqStanza:
    rmq_id: Optional[int] = None
    type: Optional[int] = None
    id: Optional[str] = None
    from_: Optional[str] = None
    to: Optional[str] = None
    error: Optional[ErrorInfo] = None
    extension: Optional[Extension] = None
    persistent_id: Optional[str] = None
    stream_id: Optional[int] = None
    last_stream_id_received: Optional[int] = None
    account_id: Optional[int] = None
    status: Optional[int] = None


@dataclass
class AppData:
    key: str
    value: str


@dataclass
class DataMessageStanza:
    id: Optional[str] = None
    from_: Optional[str] = None
    to: Optional[str] = None
    category: Optional[str] = None
    token: Optional[str] = None
    app_data: List[AppData] = field(default_factory=list)
    from_trusted_server: Optional[bool] = None
    persistent_id: Optional[str] = None
    stream_id: Optional[int] = None
    last_stream_id_received: Optional[int] = None
    reg_id: Optional[str] = None
    device_user_id: Optional[int] = None
    ttl: Optional[int] = None
    sent: Optional[int] = None
    queued: Optional[int] = None
    status: Optional[int] = None
    raw_data: Optional[bytes] = None
    immediate_ack: Optional[bool] = None

