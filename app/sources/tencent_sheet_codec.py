import base64
import struct
import zlib
from dataclasses import dataclass


@dataclass(frozen=True)
class WireField:
    number: int
    wire_type: int
    value: int | bytes


def _read_varint(payload: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(payload) and shift <= 63:
        current = payload[offset]
        offset += 1
        value |= (current & 0x7F) << shift
        if current & 0x80 == 0:
            return value, offset
        shift += 7
    raise ValueError("invalid protobuf varint")


def _parse_message(payload: bytes) -> list[WireField]:
    fields: list[WireField] = []
    offset = 0
    while offset < len(payload):
        key, offset = _read_varint(payload, offset)
        number = key >> 3
        wire_type = key & 0x07
        if number <= 0:
            raise ValueError("invalid protobuf field number")
        if wire_type == 0:
            value, offset = _read_varint(payload, offset)
        elif wire_type == 1:
            end = offset + 8
            if end > len(payload):
                raise ValueError("truncated fixed64 field")
            value = payload[offset:end]
            offset = end
        elif wire_type == 2:
            length, offset = _read_varint(payload, offset)
            end = offset + length
            if end > len(payload):
                raise ValueError("truncated length-delimited field")
            value = payload[offset:end]
            offset = end
        elif wire_type == 5:
            end = offset + 4
            if end > len(payload):
                raise ValueError("truncated fixed32 field")
            value = payload[offset:end]
            offset = end
        else:
            raise ValueError(f"unsupported protobuf wire type: {wire_type}")
        fields.append(WireField(number=number, wire_type=wire_type, value=value))
    return fields


def _values(
    fields: list[WireField],
    number: int,
    wire_type: int | None = None,
) -> list[int | bytes]:
    return [
        field.value
        for field in fields
        if field.number == number
        and (wire_type is None or field.wire_type == wire_type)
    ]


def _message_value(fields: list[WireField], number: int) -> list[WireField]:
    values = _values(fields, number, 2)
    if not values or not isinstance(values[0], bytes):
        raise ValueError(f"missing protobuf message field: {number}")
    return _parse_message(values[0])


def _varint_value(
    fields: list[WireField],
    number: int,
    default: int | None = None,
) -> int:
    values = _values(fields, number, 0)
    if values and isinstance(values[0], int):
        return values[0]
    if default is not None:
        return default
    raise ValueError(f"missing protobuf varint field: {number}")


def _find_sheet_message(workbook: list[WireField]) -> list[WireField]:
    for candidate in _values(workbook, 5, 2):
        if not isinstance(candidate, bytes):
            continue
        fields = _parse_message(candidate)
        if _values(fields, 19, 2):
            return _message_value(fields, 19)
    raise ValueError("Tencent sheet grid payload was not found")


def decode_tencent_sheet(encoded_payload: str) -> list[list[str | int | float]]:
    try:
        compressed = base64.b64decode(encoded_payload, validate=True)
        payload = zlib.decompress(compressed)
    except (ValueError, zlib.error) as exc:
        raise ValueError("invalid Tencent sheet payload") from exc

    root = _parse_message(payload)
    workbook = _message_value(root, 1)
    sheet = _find_sheet_message(workbook)
    value_pool = _message_value(sheet, 5)

    strings: list[str] = []
    for entry in _values(value_pool, 1, 2):
        if not isinstance(entry, bytes):
            continue
        string_fields = _parse_message(entry)
        raw_values = _values(string_fields, 1, 2)
        if not raw_values or not isinstance(raw_values[0], bytes):
            raise ValueError("invalid Tencent shared string")
        strings.append(raw_values[0].decode("utf-8"))

    numbers: list[float] = []
    for entry in _values(value_pool, 3, 2):
        if not isinstance(entry, bytes):
            continue
        number_fields = _parse_message(entry)
        raw_values = _values(number_fields, 1, 1)
        if not raw_values or not isinstance(raw_values[0], bytes):
            raise ValueError("invalid Tencent shared number")
        numbers.append(struct.unpack("<d", raw_values[0])[0])

    cells: dict[tuple[int, int], str | int | float] = {}
    for entry in _values(sheet, 6, 2):
        if not isinstance(entry, bytes):
            continue
        cell = _parse_message(entry)
        row_index = _varint_value(cell, 1, 0)
        column_index = _varint_value(cell, 2, 0)
        descriptor = _message_value(cell, 3)
        value_type = _varint_value(descriptor, 1)
        reference_fields = _message_value(descriptor, 2)
        reference = _varint_value(reference_fields, 1, 0)

        if value_type == 4:
            try:
                value: str | int | float = strings[reference]
            except IndexError as exc:
                raise ValueError("invalid Tencent shared string reference") from exc
        elif value_type == 2:
            number_index = reference - 129
            if number_index >= 0 and number_index < len(numbers):
                value = numbers[number_index]
            else:
                value = reference
        else:
            raise ValueError(f"unsupported Tencent cell value type: {value_type}")
        coordinate = (row_index, column_index)
        if coordinate in cells:
            raise ValueError("duplicate Tencent cell coordinate")
        cells[coordinate] = value

    if not cells:
        return []
    max_row = max(row for row, _ in cells)
    max_column = max(column for _, column in cells)
    return [
        [cells.get((row, column), "") for column in range(max_column + 1)]
        for row in range(max_row + 1)
    ]
