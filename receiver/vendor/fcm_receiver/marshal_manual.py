from __future__ import annotations

from typing import List

from .messages_manual import (
    AndroidCheckinRequest,
    AndroidCheckinProto,
    ChromeBuildProto,
    LoginRequest,
    Setting,
    HeartbeatStat,
    ClientEvent,
    DataMessageStanza,
    AppData,
)
from .proto_manual import ProtoEncoder


def marshal_android_checkin_request(msg: AndroidCheckinRequest) -> bytes:
    e = ProtoEncoder()
    if msg.imei is not None:
        e.encode_string(1, msg.imei)
    if msg.id is not None:
        e.encode_int64(2, msg.id)
    if msg.digest is not None:
        e.encode_string(3, msg.digest)
    if msg.checkin is not None:
        e.encode_bytes(4, marshal_android_checkin_proto(msg.checkin))
    if msg.desired_build is not None:
        e.encode_string(5, msg.desired_build)
    if msg.locale is not None:
        e.encode_string(6, msg.locale)
    if msg.logging_id is not None:
        e.encode_int64(7, msg.logging_id)
    if msg.market_checkin is not None:
        e.encode_string(8, msg.market_checkin)
    for v in msg.mac_addr:
        e.encode_string(9, v)
    if msg.meid is not None:
        e.encode_string(10, msg.meid)
    for v in msg.account_cookie:
        e.encode_string(11, v)
    if msg.time_zone is not None:
        e.encode_string(12, msg.time_zone)
    if msg.security_token is not None:
        e.encode_fixed64(13, msg.security_token)
    if msg.version is not None:
        e.encode_int32(14, msg.version)
    for v in msg.ota_cert:
        e.encode_string(15, v)
    if msg.serial_number is not None:
        e.encode_string(16, msg.serial_number)
    if msg.esn is not None:
        e.encode_string(17, msg.esn)
    for v in msg.mac_addr_type:
        e.encode_string(19, v)
    if msg.fragment is not None:
        e.encode_int32(20, msg.fragment)
    if msg.user_name is not None:
        e.encode_string(21, msg.user_name)
    if msg.user_serial_number is not None:
        e.encode_int32(22, msg.user_serial_number)
    return e.bytes()


def marshal_android_checkin_proto(msg: AndroidCheckinProto) -> bytes:
    e = ProtoEncoder()
    if msg.last_checkin_msec is not None:
        e.encode_int64(2, msg.last_checkin_msec)
    if msg.cell_operator is not None:
        e.encode_string(6, msg.cell_operator)
    if msg.sim_operator is not None:
        e.encode_string(7, msg.sim_operator)
    if msg.roaming is not None:
        e.encode_string(8, msg.roaming)
    if msg.user_number is not None:
        e.encode_int32(9, msg.user_number)
    if msg.type is not None:
        e.encode_int32(12, msg.type)
    if msg.chrome_build is not None:
        e.encode_bytes(13, marshal_chrome_build_proto(msg.chrome_build))
    return e.bytes()


def marshal_chrome_build_proto(msg: ChromeBuildProto) -> bytes:
    e = ProtoEncoder()
    if msg.platform is not None:
        e.encode_int32(1, msg.platform)
    if msg.chrome_version is not None:
        e.encode_string(2, msg.chrome_version)
    if msg.channel is not None:
        e.encode_int32(3, msg.channel)
    return e.bytes()


def marshal_login_request(msg: LoginRequest) -> bytes:
    e = ProtoEncoder()
    e.encode_string(1, msg.id)
    e.encode_string(2, msg.domain)
    e.encode_string(3, msg.user)
    e.encode_string(4, msg.resource)
    e.encode_string(5, msg.auth_token)
    e.encode_string(6, msg.device_id)
    if msg.last_rmq_id is not None:
        e.encode_int64(7, msg.last_rmq_id)
    for s in msg.setting:
        e.encode_bytes(8, marshal_setting(s))
    for pid in msg.received_persistent_id:
        e.encode_string(10, pid)
    if msg.adaptive_heartbeat is not None:
        e.encode_bool(12, msg.adaptive_heartbeat)
    if msg.heartbeat_stat is not None:
        e.encode_bytes(13, marshal_heartbeat_stat(msg.heartbeat_stat))
    if msg.use_rmq2 is not None:
        e.encode_bool(14, msg.use_rmq2)
    if msg.account_id is not None:
        e.encode_int64(15, msg.account_id)
    if msg.auth_service is not None:
        e.encode_int32(16, msg.auth_service)
    if msg.network_type is not None:
        e.encode_int32(17, msg.network_type)
    if msg.status is not None:
        e.encode_int64(18, msg.status)
    for ev in msg.client_event:
        e.encode_bytes(22, marshal_client_event(ev))
    return e.bytes()


def marshal_setting(msg: Setting) -> bytes:
    e = ProtoEncoder()
    e.encode_string(1, msg.name)
    e.encode_string(2, msg.value)
    return e.bytes()


def marshal_heartbeat_stat(msg: HeartbeatStat) -> bytes:
    e = ProtoEncoder()
    e.encode_string(1, msg.ip)
    e.encode_bool(2, msg.timeout)
    e.encode_int32(3, msg.interval_ms)
    return e.bytes()


def marshal_client_event(msg: ClientEvent) -> bytes:
    e = ProtoEncoder()
    if msg.type is not None:
        e.encode_int32(1, msg.type)
    if msg.number_discarded_events is not None:
        e.encode_uint32(100, msg.number_discarded_events)
    if msg.network_type is not None:
        e.encode_int32(200, msg.network_type)
    if msg.time_connection_started_ms is not None:
        e.encode_uint64(202, msg.time_connection_started_ms)
    if msg.time_connection_ended_ms is not None:
        e.encode_uint64(203, msg.time_connection_ended_ms)
    if msg.error_code is not None:
        e.encode_int32(204, msg.error_code)
    if msg.time_connection_established_ms is not None:
        e.encode_uint64(300, msg.time_connection_established_ms)
    return e.bytes()


def marshal_app_data(msg: AppData) -> bytes:
    e = ProtoEncoder()
    e.encode_string(1, msg.key)
    e.encode_string(2, msg.value)
    return e.bytes()


def marshal_data_message_stanza(msg: DataMessageStanza) -> bytes:
    e = ProtoEncoder()
    if msg.id is not None:
        e.encode_string(2, msg.id)
    if msg.from_ is not None:
        e.encode_string(3, msg.from_)
    if msg.to is not None:
        e.encode_string(4, msg.to)
    if msg.category is not None:
        e.encode_string(5, msg.category)
    if msg.token is not None:
        e.encode_string(6, msg.token)
    for ad in msg.app_data:
        e.encode_bytes(7, marshal_app_data(ad))
    if msg.from_trusted_server is not None:
        e.encode_bool(8, msg.from_trusted_server)
    if msg.persistent_id is not None:
        e.encode_string(9, msg.persistent_id)
    if msg.stream_id is not None:
        e.encode_int32(10, msg.stream_id)
    if msg.last_stream_id_received is not None:
        e.encode_int32(11, msg.last_stream_id_received)
    if msg.reg_id is not None:
        e.encode_string(13, msg.reg_id)
    if msg.device_user_id is not None:
        e.encode_int64(16, msg.device_user_id)
    if msg.ttl is not None:
        e.encode_int32(17, msg.ttl)
    if msg.sent is not None:
        e.encode_int64(18, msg.sent)
    if msg.queued is not None:
        e.encode_int32(19, msg.queued)
    if msg.status is not None:
        e.encode_int64(20, msg.status)
    if msg.raw_data is not None:
        e.encode_bytes(21, msg.raw_data)
    if msg.immediate_ack is not None:
        e.encode_bool(24, msg.immediate_ack)
    return e.bytes()
