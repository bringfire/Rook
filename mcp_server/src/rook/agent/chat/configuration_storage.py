"""Windows DACL admission for the service-owned Prime configuration directory.

Admission never repairs existing objects. Explicit maintenance may correct only
their DACLs; neither path reads credentials or implements persistence.
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
_FILES = ("auth.json", "settings.json", "models.json")


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
            (self.adv, "SetSecurityInfo", [w.HANDLE, w.DWORD, w.DWORD, ptr, ptr, ptr, ptr], w.DWORD),
            (self.adv, "GetSecurityDescriptorDacl", [ptr, ctypes.POINTER(w.BOOL), ctypes.POINTER(ptr), ctypes.POINTER(w.BOOL)], w.BOOL),
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

    def require_unelevated(self):
        token = self.w.HANDLE()
        self.check(self.adv.OpenProcessToken(self.kernel.GetCurrentProcess(), 8, ctypes.byref(token)))
        try:
            elevated, size = self.w.DWORD(), self.w.DWORD()
            self.check(self.adv.GetTokenInformation(token, 20, ctypes.byref(elevated), ctypes.sizeof(elevated), ctypes.byref(size)))
            self.check(not elevated.value)
        finally:
            self.check(self.kernel.CloseHandle(token))

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
    def open(self, path, *, optional=False, repair=False, directory=False):
        # Admission requests metadata only. Omit FILE_SHARE_DELETE to pin storage
        # through the operation. OPEN_REPARSE_POINT inspects the link itself.
        # SetSecurityInfo on a MAXIMUM_ALLOWED directory handle does not propagate
        # ACEs into existing children. File handles request no credential data access.
        access = (0x02000000 if directory else 0x60080) if repair else 0x20080
        sharing = 0 if repair and not directory else 3
        handle = self.kernel.CreateFileW(str(path), access, sharing, None, 3, 0x02200000, None)
        if handle == ctypes.c_void_p(-1).value:
            if optional and ctypes.get_last_error() == 2:
                yield None
                return
            raise ConfigurationStorageRefused()
        try:
            yield handle
        finally:
            closed = self.kernel.CloseHandle(handle)
            if repair:
                self.check(closed)

    def inspect(self, handle, *, directory, permissions=True):
        info = self.FileInfo()
        self.check(self.kernel.GetFileInformationByHandle(handle, ctypes.byref(info)))
        self.check(not info.attributes & 1024 and bool(info.attributes & 16) == directory)
        self.check(directory or info.links == 1)
        owner, acl, sd = self.w.LPVOID(), self.w.LPVOID(), self.w.LPVOID()
        self.check(self.adv.GetSecurityInfo(handle, 1, 5, ctypes.byref(owner), None, ctypes.byref(acl), None, ctypes.byref(sd)) == 0)
        try:
            owner_sid = self.sid(owner)
            self.check(owner_sid == self.user_sid)
            identity = (info.volume, info.indexHigh, info.indexLow)
            if not permissions:
                return identity  # Repair precheck: unsafe DACL is the problem being corrected.
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
            return identity
        finally:
            self.kernel.LocalFree(sd)

    @contextmanager
    def private_descriptor(self, *, directory):
        sd = self.w.LPVOID()
        inherit = "OICI" if directory else ""
        sddl = f"O:{self.user_sid}D:P(A;{inherit};FA;;;{self.user_sid})(A;{inherit};FA;;;SY)(A;{inherit};FA;;;BA)"
        self.check(self.adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None))
        try:
            yield sd
        finally:
            self.kernel.LocalFree(sd)

    def create(self, path):
        with self.private_descriptor(directory=True) as sd:
            attrs = self.Attributes(ctypes.sizeof(self.Attributes), sd, False)
            if not self.kernel.CreateDirectoryW(str(path), ctypes.byref(attrs)):
                self.check(ctypes.get_last_error() == 183)  # Concurrent creator must still pass admission.

    def protect(self, handle, *, directory):
        with self.private_descriptor(directory=directory) as sd:
            present, defaulted, acl = self.w.BOOL(), self.w.BOOL(), self.w.LPVOID()
            self.check(self.adv.GetSecurityDescriptorDacl(sd, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)))
            self.check(present.value and acl.value)
            # DACL only. Never set owner/group, SACL, file content or attributes.
            self.check(self.adv.SetSecurityInfo(handle, 1, 0x80000004, None, None, acl, None) == 0)


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
            for name in _FILES:
                file = handles.enter_context(windows.open(path / name, optional=True))
                if file is not None:
                    windows.inspect(file, directory=False)
    except ConfigurationStorageRefused:
        raise
    except Exception:
        raise ConfigurationStorageRefused() from None


def _known_children(path):
    names = set()
    with os.scandir(path) as children:
        for child in children:
            if child.name not in _FILES or child.name in names:
                raise ConfigurationStorageRefused()
            names.add(child.name)
    return names


def repair_configuration_storage(path: Path) -> dict:
    """Explicit maintenance only, with all store users closed by the operator.

    Finite selection: existing root and at most three known files. No ancestor
    admission, recursive permission writes, content access, creation or rollback.
    """
    rows = [{"name": name, "present": None, "attempted": False,
             "write_completed": False, "verified": False} for name in ("prime-config", *_FILES)]
    result = {"outcome": "refused", "code": "repair_refused", "objects": rows,
              "admission": "not_run", "cleanup": "closed"}
    handles = ExitStack()
    try:
        if os.name != "nt" or not path.is_absolute() or ".." in path.parts or path.name != "prime-config":
            raise ConfigurationStorageRefused()
        windows = _Windows()
        windows.require_unelevated()
        selected = []
        for index, row in enumerate(rows):
            directory = index == 0
            target = path if directory else path / row["name"]
            handle = handles.enter_context(windows.open(target, optional=not directory, repair=True, directory=directory))
            row["present"] = handle is not None
            if handle is not None:
                identity = windows.inspect(handle, directory=directory, permissions=False)
                row["identity"] = list(identity)
                selected.append((row, handle, directory, identity))
        expected = {row["name"] for row in rows[1:] if row["present"]}
        windows.check(_known_children(path) == expected)
        # Finish every identity/owner/type precheck before the first DACL write.
        for row, handle, directory, identity in selected:
            windows.check(windows.inspect(handle, directory=directory, permissions=False) == identity)
            try:
                admitted_identity = windows.inspect(handle, directory=directory)
            except ConfigurationStorageRefused:
                pass  # The intended correction is precisely an inadmissible DACL.
            else:
                windows.check(admitted_identity == identity)
                row["verified"] = True
        for row, handle, directory, identity in selected:
            windows.check(_known_children(path) == expected)
            windows.check(windows.inspect(handle, directory=directory, permissions=False) == identity)
            if not row["verified"]:
                row["attempted"] = True
                windows.protect(handle, directory=directory)
                row["write_completed"] = True
            windows.check(windows.inspect(handle, directory=directory) == identity)
            row["verified"] = True
        windows.check(_known_children(path) == expected)
        result["admission"] = "failed"
        admit_configuration_storage(path)
        result["admission"] = "passed"
        result["outcome"] = "repaired" if any(row["write_completed"] for row in rows) else "unchanged"
        result["code"] = "ok"
    except (Exception, KeyboardInterrupt):
        if any(row["attempted"] for row in rows):
            result.update(outcome="partial", code="repair_incomplete")
    finally:
        try:
            handles.close()
        except (Exception, KeyboardInterrupt):
            result.update(outcome="failed", code="cleanup_failed", cleanup="unconfirmed")
    return result


def main(argv=None):
    import argparse
    import json
    from rook.runtime_paths import resolve_runtime_paths

    class RepairParser(argparse.ArgumentParser):
        def error(self, message):
            self.exit(2, "Invalid repair arguments. No permissions changed.\n")

    parser = RepairParser(description="Explicit Rook configuration-storage permissions repair.", allow_abbrev=False)
    parser.add_argument("--repair-permissions", action="store_true", required=True)
    parser.add_argument("--confirm-closed", action="store_true", required=True)
    parser.add_argument("--expected-directory", required=True)
    args = parser.parse_args(argv)
    result = {"outcome": "refused", "code": "binding_mismatch", "objects": [],
              "admission": "not_run", "cleanup": "closed"}
    try:
        paths = resolve_runtime_paths()
        path = paths.data_root / "prime-config"
        expected = Path(args.expected_directory)
    except (Exception, KeyboardInterrupt):
        result["code"] = "binding_unavailable"
    else:
        if paths.mode == "release" and expected.is_absolute() and ".." not in expected.parts and expected == path:
            result = repair_configuration_storage(path)
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["code"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
