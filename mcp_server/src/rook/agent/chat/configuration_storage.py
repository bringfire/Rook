"""Windows DACL admission for the service-owned Prime configuration directory.

No credential reads, existing-object ACL changes, or persistence implementation.
The surrounding Windows profile is an OS-managed trust boundary, not subject
to ancestor ACL admission. This does not defend against a compromised account,
administrators, or hostile control of the surrounding filesystem.
"""
from __future__ import annotations

import ctypes
import os
from contextlib import ExitStack, contextmanager
from pathlib import Path


class ConfigurationStorageRefused(RuntimeError):
    code = "configuration_storage_refused"

    def __init__(self):
        super().__init__("Configuration storage protection could not be verified. Operation not started; existing storage preserved.")


_FULL = 0x1F01FF
_SYSTEM = "S-1-5-18"
_ADMINS = "S-1-5-32-544"


def _admit_aces(aces, trusted):
    for sid, mask, flags in aces:
        if flags & 8:
            continue
        if sid not in trusted and mask:
            raise ConfigurationStorageRefused()


class _Windows:
    def __init__(self):
        from ctypes import wintypes as w
        self.w = w
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.adv = ctypes.WinDLL("advapi32", use_last_error=True)
        ptr = w.LPVOID

        class Attributes(ctypes.Structure):
            _fields_ = [("length", w.DWORD), ("descriptor", ptr), ("inherit", w.BOOL)]

        class FileInfo(ctypes.Structure):
            _fields_ = [("attributes", w.DWORD), ("created", w.FILETIME), ("accessed", w.FILETIME),
                        ("written", w.FILETIME), ("volume", w.DWORD), ("sizeHigh", w.DWORD),
                        ("sizeLow", w.DWORD), ("links", w.DWORD), ("indexHigh", w.DWORD), ("indexLow", w.DWORD)]

        class AclInfo(ctypes.Structure):
            _fields_ = [("count", w.DWORD), ("used", w.DWORD), ("free", w.DWORD)]

        self.Attributes, self.FileInfo, self.AclInfo = Attributes, FileInfo, AclInfo
        signatures = [
            (self.kernel, "CreateFileW", [w.LPCWSTR, w.DWORD, w.DWORD, ptr, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
            (self.kernel, "CreateDirectoryW", [w.LPCWSTR, ctypes.POINTER(Attributes)], w.BOOL),
            (self.kernel, "GetFileInformationByHandle", [w.HANDLE, ctypes.POINTER(FileInfo)], w.BOOL),
            (self.kernel, "GetCurrentProcess", [], w.HANDLE),
            (self.kernel, "CloseHandle", [w.HANDLE], w.BOOL),
            (self.kernel, "LocalFree", [ptr], ptr),
            (self.adv, "OpenProcessToken", [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)], w.BOOL),
            (self.adv, "GetTokenInformation", [w.HANDLE, ctypes.c_int, ptr, w.DWORD, ctypes.POINTER(w.DWORD)], w.BOOL),
            (self.adv, "ConvertSidToStringSidW", [ptr, ctypes.POINTER(w.LPWSTR)], w.BOOL),
            (self.adv, "ConvertStringSecurityDescriptorToSecurityDescriptorW", [w.LPCWSTR, w.DWORD, ctypes.POINTER(ptr), ptr], w.BOOL),
            (self.adv, "GetSecurityInfo", [w.HANDLE, w.DWORD, w.DWORD, ctypes.POINTER(ptr), ptr, ctypes.POINTER(ptr), ptr, ctypes.POINTER(ptr)], w.DWORD),
            (self.adv, "GetSecurityDescriptorControl", [ptr, ctypes.POINTER(w.WORD), ctypes.POINTER(w.DWORD)], w.BOOL),
            (self.adv, "GetAclInformation", [ptr, ptr, w.DWORD, ctypes.c_int], w.BOOL),
            (self.adv, "GetAce", [ptr, w.DWORD, ctypes.POINTER(ptr)], w.BOOL),
        ]
        for dll, name, args, result in signatures:
            fn = getattr(dll, name)
            fn.argtypes, fn.restype = args, result
        token = w.HANDLE()
        self.check(self.adv.OpenProcessToken(self.kernel.GetCurrentProcess(), 8, ctypes.byref(token)))
        try:
            size = w.DWORD()
            self.adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            self.check(0 < size.value <= 65536)
            buffer = ctypes.create_string_buffer(size.value)
            self.check(self.adv.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)))
            self.user_sid = self.sid(ctypes.cast(buffer, ctypes.POINTER(w.LPVOID))[0])
        finally:
            self.kernel.CloseHandle(token)
        self.trusted = {self.user_sid, _SYSTEM, _ADMINS}

    @staticmethod
    def check(value):
        if not value:
            raise ConfigurationStorageRefused()

    def sid(self, pointer):
        text = self.w.LPWSTR()
        self.check(self.adv.ConvertSidToStringSidW(pointer, ctypes.byref(text)))
        try:
            return text.value
        finally:
            self.kernel.LocalFree(ctypes.cast(text, self.w.LPVOID))

    @contextmanager
    def open(self, path, *, optional=False):
        # Metadata only; omit FILE_SHARE_DELETE to pin each admitted storage object
        # until this admission is complete. OPEN_REPARSE_POINT inspects the link itself.
        handle = self.kernel.CreateFileW(str(path), 0x20080, 3, None, 3, 0x02200000, None)
        if handle == ctypes.c_void_p(-1).value:
            if optional and ctypes.get_last_error() == 2:
                yield None
                return
            raise ConfigurationStorageRefused()
        try:
            yield handle
        finally:
            self.kernel.CloseHandle(handle)

    def inspect(self, handle, *, directory):
        info = self.FileInfo()
        self.check(self.kernel.GetFileInformationByHandle(handle, ctypes.byref(info)))
        self.check(not info.attributes & 1024 and bool(info.attributes & 16) == directory)
        self.check(directory or info.links == 1)
        owner, acl, sd = self.w.LPVOID(), self.w.LPVOID(), self.w.LPVOID()
        self.check(self.adv.GetSecurityInfo(handle, 1, 5, ctypes.byref(owner), None, ctypes.byref(acl), None, ctypes.byref(sd)) == 0)
        try:
            owner_sid = self.sid(owner)
            self.check(owner_sid == self.user_sid)
            self.check(acl.value)  # Null DACL grants unrestricted access.
            control, revision = self.w.WORD(), self.w.DWORD()
            self.check(self.adv.GetSecurityDescriptorControl(sd, ctypes.byref(control), ctypes.byref(revision)))
            if directory:
                self.check(control.value & 0x1000)  # SE_DACL_PROTECTED
            details = self.AclInfo()
            self.check(self.adv.GetAclInformation(acl, ctypes.byref(details), ctypes.sizeof(details), 2))
            self.check(0 < details.count <= 256)
            aces = []
            for index in range(details.count):
                ace = self.w.LPVOID()
                self.check(self.adv.GetAce(acl, index, ctypes.byref(ace)))
                kind, flags = ctypes.string_at(ace, 2)
                self.check(kind == 0)  # Refuse deny/complex ACEs rather than guess semantics.
                mask = ctypes.c_uint32.from_address(ace.value + 4).value
                sid = self.sid(ace.value + 8)
                # OWNER RIGHTS refers to this object's already-admitted owner.
                aces.append((owner_sid if sid == "S-1-3-4" else sid, mask, flags))
            _admit_aces(aces, self.trusted)
            self.check(any(sid == self.user_sid and mask & _FULL == _FULL and not flags & 8
                           for sid, mask, flags in aces))
            if directory:
                # New credential/temp/lock objects must inherit the same protected access.
                for sid in self.trusted:
                    self.check(any(s == sid and m & _FULL == _FULL and f & 3 == 3 and not f & 12
                                   for s, m, f in aces))
                self.check(all(s in self.trusted for s, m, f in aces if m))
            return (info.volume, info.indexHigh, info.indexLow)
        finally:
            self.kernel.LocalFree(sd)

    def create(self, path):
        sd = self.w.LPVOID()
        sddl = f"O:{self.user_sid}D:P(A;OICI;FA;;;{self.user_sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
        self.check(self.adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None))
        try:
            attrs = self.Attributes(ctypes.sizeof(self.Attributes), sd, False)
            if not self.kernel.CreateDirectoryW(str(path), ctypes.byref(attrs)):
                self.check(ctypes.get_last_error() == 183)  # Concurrent creator must still pass admission.
        finally:
            self.kernel.LocalFree(sd)


def admit_configuration_storage(path: Path) -> None:
    """Admit before child acquisition; never repair or read an existing store."""
    if not path.is_absolute() or ".." in path.parts:
        raise ConfigurationStorageRefused()
    if os.name != "nt":
        return  # This correction does not alter non-Windows storage policy.
    try:
        windows = _Windows()
        with ExitStack() as handles:
            handle = handles.enter_context(windows.open(path, optional=True))
            if handle is None:
                windows.create(path)
                handle = handles.enter_context(windows.open(path))
            windows.inspect(handle, directory=True)
            for name in ("auth.json", "settings.json", "models.json"):
                file = handles.enter_context(windows.open(path / name, optional=True))
                if file is not None:
                    windows.inspect(file, directory=False)
    except ConfigurationStorageRefused:
        raise
    except Exception:
        raise ConfigurationStorageRefused() from None
