"""Tests for the Modbus TCP transaction ID handling in umodbus/tcp.py."""

import struct

from umodbus.tcp import CommonTCPFunctions


def _response(trans_id: int, slave_addr: int, function_code: int) -> bytes:
    return struct.pack('>HHHBBB', trans_id, 0, 3, slave_addr, function_code, 0)


def test_transaction_id_wraps_around_at_16_bit():
    client = CommonTCPFunctions(slave_ip="127.0.0.1")
    client.trans_id_ctr = 0xFFFF

    hdr, trans_id = client._create_mbap_hdr(slave_addr=1, modbus_pdu=b"\x04")
    assert trans_id == 0xFFFF
    assert struct.unpack('>H', hdr[:2])[0] == 0xFFFF

    hdr, trans_id = client._create_mbap_hdr(slave_addr=1, modbus_pdu=b"\x04")
    assert trans_id == 0
    assert struct.unpack('>H', hdr[:2])[0] == 0


def test_response_after_wraparound_is_accepted():
    client = CommonTCPFunctions(slave_ip="127.0.0.1")
    client.trans_id_ctr = 0xFFFF
    client._create_mbap_hdr(slave_addr=1, modbus_pdu=b"\x04")

    # the device echoes the (16 bit) transaction ID from the request header
    hdr, trans_id = client._create_mbap_hdr(slave_addr=1, modbus_pdu=b"\x04")
    echoed_tid = struct.unpack('>H', hdr[:2])[0]
    client._validate_resp_hdr(response=_response(echoed_tid, 1, 4),
                              trans_id=trans_id,
                              slave_addr=1,
                              function_code=4)


# ---------------------------------------------------------------------------
# AsyncTCP client: response timeout and request serialization
# ---------------------------------------------------------------------------

import asyncio

import pytest

from umodbus.asynchronous.tcp import AsyncTCP


async def _start_server(handle_frame):
    """Start a local Modbus TCP server calling handle_frame(tid, uid, pdu).

    handle_frame returns the response PDU, or None to never respond.
    """
    async def on_client(reader, writer):
        try:
            while True:
                hdr = await reader.readexactly(7)
                tid, _, length, uid = struct.unpack('>HHHB', hdr)
                pdu = await reader.readexactly(length - 1)
                resp_pdu = await handle_frame(tid, uid, pdu)
                if resp_pdu is None:
                    continue
                writer.write(struct.pack('>HHHB', tid, 0, len(resp_pdu) + 1, uid) + resp_pdu)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(on_client, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def _read_input_register_response(value: int) -> bytes:
    return struct.pack('>BBH', 0x04, 2, value)


def test_response_timeout_raises_oserror_and_drops_connection():
    async def never_respond(tid, uid, pdu):
        return None

    async def scenario():
        server, port = await _start_server(never_respond)
        async with server:
            client = AsyncTCP(slave_ip="127.0.0.1", slave_port=port, timeout=0.2)
            await client.connect()
            with pytest.raises(OSError):
                await client.read_input_registers(slave_addr=1, starting_addr=0, register_qty=1)
            assert not client.is_connected
            assert client._sock_writer is None

            # a later request without reconnect must fail fast, not hang
            with pytest.raises(ValueError):
                await asyncio.wait_for(
                    client.read_input_registers(slave_addr=1, starting_addr=0, register_qty=1), 1)

    asyncio.run(scenario())


def test_reconnect_after_timeout_recovers():
    respond = False

    async def respond_when_enabled(tid, uid, pdu):
        return _read_input_register_response(215) if respond else None

    async def scenario():
        nonlocal respond
        server, port = await _start_server(respond_when_enabled)
        async with server:
            client = AsyncTCP(slave_ip="127.0.0.1", slave_port=port, timeout=0.2)
            try:
                await client.connect()
                with pytest.raises(OSError):
                    await client.read_input_registers(slave_addr=1, starting_addr=0, register_qty=1)

                respond = True
                await client.connect()
                result = await client.read_input_registers(slave_addr=1, starting_addr=0, register_qty=1)
                assert list(result) == [215]
            finally:
                await client._close()

    asyncio.run(scenario())


def test_concurrent_requests_are_serialized():
    in_flight = 0
    max_in_flight = 0

    async def slow_echo_address(tid, uid, pdu):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        # answer with the requested register address as value
        return _read_input_register_response(struct.unpack('>H', pdu[1:3])[0])

    async def scenario():
        server, port = await _start_server(slow_echo_address)
        async with server:
            client = AsyncTCP(slave_ip="127.0.0.1", slave_port=port, timeout=2)
            try:
                await client.connect()
                results = await asyncio.gather(*(
                    client.read_input_registers(slave_addr=1, starting_addr=addr, register_qty=1)
                    for addr in range(5)
                ))
                assert [list(r) for r in results] == [[0], [1], [2], [3], [4]]
            finally:
                await client._close()

    asyncio.run(scenario())
    assert max_in_flight == 1
