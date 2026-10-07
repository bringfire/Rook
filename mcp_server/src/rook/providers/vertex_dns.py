"""Cancellable Windows DNS, without a blocking Python resolver thread."""
import ctypes
from ctypes import wintypes
import ipaddress
import os
import socket
import threading

from .vertex_workforce_contract import auth_error


class _Address(ctypes.Structure):
    pass


_AddressPointer = ctypes.POINTER(_Address)
_Address._fields_ = [('flags', ctypes.c_int), ('family', ctypes.c_int),
    ('socktype', ctypes.c_int), ('protocol', ctypes.c_int), ('length', ctypes.c_size_t),
    ('canonical', ctypes.c_void_p), ('address', ctypes.c_void_p), ('blob', ctypes.c_void_p),
    ('blob_length', ctypes.c_size_t), ('provider', ctypes.c_void_p), ('next', _AddressPointer)]


class _Offset(ctypes.Union):
    _fields_ = [('pointer', ctypes.c_void_p), ('offsets', wintypes.DWORD * 2)]


class _Overlapped(ctypes.Structure):
    _fields_ = [('internal', ctypes.c_size_t), ('internal_high', ctypes.c_size_t),
        ('offset', _Offset), ('event', wintypes.HANDLE)]


class _Timeval(ctypes.Structure):
    _fields_ = [('seconds', ctypes.c_long), ('microseconds', ctypes.c_long)]


class _WindowsResolution:
    def __init__(self, host, port, remaining):
        if os.name != 'nt': raise auth_error('vertex_request_failed')
        self.ws = ctypes.WinDLL('ws2_32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateEventW.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.ws.GetAddrInfoExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p,
            _AddressPointer, ctypes.POINTER(_AddressPointer), ctypes.POINTER(_Timeval),
            ctypes.POINTER(_Overlapped), ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
        self.ws.GetAddrInfoExW.restype = ctypes.c_int
        self.ws.GetAddrInfoExOverlappedResult.argtypes = [ctypes.POINTER(_Overlapped)]
        self.ws.GetAddrInfoExOverlappedResult.restype = ctypes.c_int
        self.ws.GetAddrInfoExCancel.argtypes = [ctypes.POINTER(wintypes.HANDLE)]
        self.ws.GetAddrInfoExCancel.restype = ctypes.c_int
        self.ws.FreeAddrInfoExW.argtypes = [_AddressPointer]
        self.ws.FreeAddrInfoExW.restype = None
        self.result = _AddressPointer()
        self.handle = wintypes.HANDLE()
        self.event = self.kernel.CreateEventW(None, True, False, None)
        if not self.event: raise auth_error('vertex_request_failed')
        self.overlapped = _Overlapped(event=self.event)
        self.hints = _Address(socktype=socket.SOCK_STREAM, protocol=socket.IPPROTO_TCP)
        # Keep all input/output buffers alive through asynchronous completion.
        self.host = ctypes.create_unicode_buffer(host)
        self.port = ctypes.create_unicode_buffer(str(port))
        self.timeout = _Timeval(int(remaining), int((remaining % 1) * 1_000_000))
        self.status = self.ws.GetAddrInfoExW(self.host, self.port, 12, None, ctypes.byref(self.hints),
            ctypes.byref(self.result), ctypes.byref(self.timeout), ctypes.byref(self.overlapped), None, ctypes.byref(self.handle))
        if self.status not in (0, 997):
            self.close()
            raise auth_error('vertex_request_failed')

    def poll(self, seconds):
        if self.status == 0: return True
        status = self.kernel.WaitForSingleObject(self.event, max(0, int(seconds * 1000)))
        if status not in (0, 258): raise auth_error('vertex_request_failed')
        return status == 0

    def addresses(self):
        if self.status == 997 and self.ws.GetAddrInfoExOverlappedResult(ctypes.byref(self.overlapped)) != 0:
            raise auth_error('vertex_request_failed')
        output, node = [], self.result
        for _ in range(64):
            if not node: break
            item = node.contents
            if item.family in (socket.AF_INET, socket.AF_INET6):
                size = 16 if item.family == socket.AF_INET else 28
                if item.length != size or not item.address: raise auth_error('vertex_request_failed')
                raw = ctypes.string_at(item.address, size)
                port = int.from_bytes(raw[2:4], 'big')
                if item.family == socket.AF_INET:
                    address = (socket.inet_ntop(socket.AF_INET, raw[4:8]), port)
                else:
                    address = (socket.inet_ntop(socket.AF_INET6, raw[8:24]), port,
                        int.from_bytes(raw[4:8], 'big'), int.from_bytes(raw[24:28], 'little'))
                output.append((item.family, socket.SOCK_STREAM, socket.IPPROTO_TCP, address))
            node = item.next
        if not output: raise auth_error('vertex_request_failed')
        return output

    def cancel(self):
        self.ws.GetAddrInfoExCancel(ctypes.byref(self.handle))

    def close(self):
        if self.result:
            self.ws.FreeAddrInfoExW(self.result)
            self.result = _AddressPointer()
        if self.event:
            self.kernel.CloseHandle(self.event)
            self.event = None


_gate = threading.Lock()
_retained = None


def resolve_addresses(host, port, guard):
    guard.check()
    try: numeric = ipaddress.ip_address(host)
    except ValueError: numeric = None
    if numeric is not None:
        family = socket.AF_INET if numeric.version == 4 else socket.AF_INET6
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP,
            (str(numeric), port) if numeric.version == 4 else (str(numeric), port, 0, 0))]
    # One outstanding native lookup maximum. Failed native cancellation cannot
    # free live OVERLAPPED buffers or accumulate abandoned lookups/threads.
    global _retained
    if not _gate.acquire(blocking=False): raise auth_error('vertex_request_failed')
    request = None
    try:
        if _retained is not None:
            if not _retained.poll(0): raise auth_error('vertex_request_failed')
            _retained.close(); _retained = None
        guard.check()
        request = _WindowsResolution(host, port, guard.deadline - guard.monotonic())
        while not request.poll(0):
            guard.check()
            request.poll(min(.025, max(0, guard.deadline - guard.monotonic())))
        guard.check()
        return request.addresses()
    finally:
        try:
            if request is not None:
                if not request.poll(0): request.cancel()
                if request.poll(0): request.close()
                else: _retained = request  # Reap on next lookup; never publish late results.
        except Exception:
            _retained = request  # Keep native buffers alive if cancellation fails.
        finally:
            _gate.release()
