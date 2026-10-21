from __future__ import annotations

from .proto_manual import ProtoDecoder, WireType
from .messages_manual import (
    AndroidCheckinResponse,
    GservicesSetting,
    AndroidCheckinProto,
    ChromeBuildProto,
    LoginRequest,
    LoginResponse,
    ErrorInfo,
    HeartbeatConfig,
    DataMessageStanza,
    AppData,
)


def unmarshal_android_checkin_response(data: bytes) -> AndroidCheckinResponse:
    d = ProtoDecoder(data)
    msg = AndroidCheckinResponse()
    while d.pos < len(d.buf):
        fn, wt = d.decode_field_number()
        if fn == 1 and wt == WireType.VARINT:
            msg.stats_ok = d.decode_bool()
        elif fn == 3 and wt == WireType.VARINT:
            msg.time_msec = d.decode_int64()
        elif fn == 4 and wt == WireType.BYTES:
            msg.digest = d.decode_string()
        elif fn == 5 and wt == WireType.BYTES:
            setting_data = d.decode_bytes()
            msg.setting.append(unmarshal_gservices_setting(setting_data))
        elif fn == 6 and wt == WireType.VARINT:
            msg.market_ok = d.decode_bool()
        elif fn == 7 and wt in (WireType.FIXED64, WireType.VARINT):
            msg.android_id = d.decode_fixed64() if wt == WireType.FIXED64 else d.decode_uint64()
        elif fn == 8 and wt in (WireType.FIXED64, WireType.VARINT):
            msg.security_token = d.decode_fixed64() if wt == WireType.FIXED64 else d.decode_uint64()
        elif fn == 9 and wt == WireType.VARINT:
            msg.settings_diff = d.decode_bool()
        elif fn == 10 and wt == WireType.BYTES:
            msg.delete_setting.append(d.decode_string())
        elif fn == 11 and wt == WireType.BYTES:
            msg.version_info = d.decode_string()
        else:
            d.skip_field(wt)
    return msg


def unmarshal_gservices_setting(data: bytes) -> GservicesSetting:
    d = ProtoDecoder(data)
    msg = GservicesSetting()
    while d.pos < len(d.buf):
        fn, wt = d.decode_field_number()
        if fn == 1 and wt == WireType.BYTES:
            msg.name = d.decode_bytes()
        elif fn == 2 and wt == WireType.BYTES:
            msg.value = d.decode_bytes()
        else:
            d.skip_field(wt)
    return msg


def unmarshal_android_checkin_proto(data: bytes) -> AndroidCheckinProto:
    d = ProtoDecoder(data)
    msg = AndroidCheckinProto()
    while d.pos < len(d.buf):
        fn, wt = d.decode_field_number()
        if fn == 2 and wt == WireType.VARINT:
            msg.last_checkin_msec = d.decode_int64()
        elif fn == 6 and wt == WireType.BYTES:
            msg.cell_operator = d.decode_string()
        elif fn == 7 and wt == WireType.BYTES:
            msg.sim_operator = d.decode_string()
        elif fn == 8 and wt == WireType.BYTES:
            msg.roaming = d.decode_string()
        elif fn == 9 and wt == WireType.VARINT:
            msg.user_number = d.decode_int64()
        elif fn == 12 and wt == WireType.VARINT:
            msg.type = d.decode_int64()
        elif fn == 13 and wt == WireType.BYTES:
            msg.chrome_build = unmarshal_chrome_build_proto(d.decode_bytes())
        else:
            d.skip_field(wt)
    return msg


def unmarshal_chrome_build_proto(data: bytes) -> ChromeBuildProto:
    d = ProtoDecoder(data)
    msg = ChromeBuildProto()
    while d.pos < len(d.buf):
        fn, wt = d.decode_field_number()
        if fn == 1 and wt == WireType.VARINT:
            msg.platform = d.decode_int64()
        elif fn == 2 and wt == WireType.BYTES:
            msg.chrome_version = d.decode_string()
        elif fn == 3 and wt == WireType.VARINT:
            msg.channel = d.decode_int64()
        else:
            d.skip_field(wt)
    return msg


def unmarshal_login_response(data: bytes) -> LoginResponse:
    d = ProtoDecoder(data)
    msg = LoginResponse()
    while d.pos < len(d.buf):
        fn, wt = d.decode_field_number()
        if fn == 1 and wt == WireType.BYTES:
            msg.id = d.decode_string()
        elif fn == 2 and wt == WireType.BYTES:
            msg.jid = d.decode_string()
        elif fn == 3 and wt == WireType.BYTES:
            msg.error = unmarshal_error_info(d.decode_bytes())
        elif fn == 4 and wt == WireType.BYTES:
            d.decode_bytes()  # Settings are not needed by the receiver.
        elif fn == 5 and wt == WireType.VARINT:
            msg.stream_id = d.decode_int32()
        elif fn == 6 and wt == WireType.VARINT:
            msg.last_stream_id_received = d.decode_int32()
        elif fn == 7 and wt == WireType.BYTES:
            msg.heartbeat_config = unmarshal_heartbeat_config(d.decode_bytes())
        elif fn == 8 and wt == WireType.VARINT:
            msg.server_timestamp = d.decode_int64()
        else:
            d.skip_field(wt)
    return msg


def unmarshal_heartbeat_config(data: bytes) -> HeartbeatConfig:
    d = ProtoDecoder(data)
    msg = HeartbeatConfig()
    while d.pos < len(d.buf):
        fn, wt = d.decode_field_number()
        if fn == 1 and wt == WireType.VARINT:
            msg.upload_stat = d.decode_bool()
        elif fn == 2 and wt == WireType.BYTES:
            msg.ip = d.decode_string()
        elif fn == 3 and wt == WireType.VARINT:
            msg.interval_ms = d.decode_int32()
        else:
            d.skip_field(wt)
    return msg


def unmarshal_error_info(data: bytes) -> ErrorInfo:
    d = ProtoDecoder(data)
    msg = ErrorInfo()
    while d.pos < len(d.buf):
        fn, wt = d.decode_field_number()
        if fn == 1 and wt == WireType.VARINT:
            msg.code = d.decode_int32()
        elif fn == 2 and wt == WireType.BYTES:
            msg.message = d.decode_string()
        elif fn == 3 and wt == WireType.BYTES:
            msg.type = d.decode_string()
        else:
            d.skip_field(wt)
    return msg


def unmarshal_data_message_stanza(data: bytes) -> DataMessageStanza:
    d = ProtoDecoder(data)
    msg = DataMessageStanza()
    while d.pos < len(d.buf):
        fn, wt = d.decode_field_number()
        if fn == 2 and wt == WireType.BYTES:
            msg.id = d.decode_string()
        elif fn == 3 and wt == WireType.BYTES:
            msg.from_ = d.decode_string()
        elif fn == 4 and wt == WireType.BYTES:
            msg.to = d.decode_string()
        elif fn == 5 and wt == WireType.BYTES:
            msg.category = d.decode_string()
        elif fn == 6 and wt == WireType.BYTES:
            msg.token = d.decode_string()
        elif fn == 7 and wt == WireType.BYTES:
            ad = unmarshal_app_data(d.decode_bytes())
            msg.app_data.append(ad)
        elif fn == 8 and wt == WireType.VARINT:
            msg.from_trusted_server = d.decode_bool()
        elif fn == 9 and wt == WireType.BYTES:
            msg.persistent_id = d.decode_string()
        elif fn == 10 and wt == WireType.VARINT:
            msg.stream_id = d.decode_int32()
        elif fn == 11 and wt == WireType.VARINT:
            msg.last_stream_id_received = d.decode_int32()
        elif fn == 13 and wt == WireType.BYTES:
            msg.reg_id = d.decode_string()
        elif fn == 16 and wt == WireType.VARINT:
            msg.device_user_id = d.decode_int64()
        elif fn == 17 and wt == WireType.VARINT:
            msg.ttl = d.decode_int32()
        elif fn == 18 and wt == WireType.VARINT:
            msg.sent = d.decode_int64()
        elif fn == 19 and wt == WireType.VARINT:
            msg.queued = d.decode_int32()
        elif fn == 20 and wt == WireType.VARINT:
            msg.status = d.decode_int64()
        elif fn == 21 and wt == WireType.BYTES:
            msg.raw_data = d.decode_bytes()
        elif fn == 24 and wt == WireType.VARINT:
            msg.immediate_ack = d.decode_bool()
        else:
            d.skip_field(wt)
    return msg


def unmarshal_app_data(data: bytes) -> AppData:
    d = ProtoDecoder(data)
    key = ""
    value = ""
    while d.pos < len(d.buf):
        fn, wt = d.decode_field_number()
        if fn == 1 and wt == WireType.BYTES:
            key = d.decode_string()
        elif fn == 2 and wt == WireType.BYTES:
            value = d.decode_string()
        else:
            d.skip_field(wt)
    return AppData(key=key, value=value)
