
import ctypes
import ctypes.wintypes as wintypes
import struct
from dataclasses import dataclass, field
from typing import Optional

PROCESS_VM_READ           = 0x0010
PROCESS_VM_WRITE          = 0x0020
PROCESS_VM_OPERATION      = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS        = 0x00000002
MEM_COMMIT                = 0x1000
PAGE_NOACCESS             = 0x01
PAGE_GUARD                = 0x100


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress",       ctypes.c_void_p),
        ("AllocationBase",    ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize",        ctypes.c_size_t),
        ("State",             wintypes.DWORD),
        ("Protect",           wintypes.DWORD),
        ("Type",              wintypes.DWORD),
    ]

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",              wintypes.DWORD),
        ("cntUsage",            wintypes.DWORD),
        ("th32ProcessID",       wintypes.DWORD),
        ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID",        wintypes.DWORD),
        ("cntThreads",          wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase",      ctypes.c_long),
        ("dwFlags",             wintypes.DWORD),
        ("szExeFile",           ctypes.c_char * 260),
    ]

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",        wintypes.DWORD),
        ("th32ModuleID",  wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage",  wintypes.DWORD),
        ("ProccntUsage",  wintypes.DWORD),
        ("modBaseAddr",   ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize",   wintypes.DWORD),
        ("hModule",       wintypes.HMODULE),
        ("szModule",      ctypes.c_char * 256),
        ("szExePath",     ctypes.c_char * 260),
    ]


@dataclass
class ScanResult:
    address: int
    raw_bytes: bytes
    display_value: str


@dataclass
class WatchEntry:
    address: int
    label: str
    last_value: bytes = field(default_factory=bytes)
    current_value: bytes = field(default_factory=bytes)
    changed: bool = False

    @property
    def display_value(self) -> str:
        return _bytes_to_ascii(self.current_value)


def _bytes_to_ascii(data: bytes, max_len: int = 32) -> str:
    result = []
    for b in data[:max_len]:
        if 0x20 <= b <= 0x7E:
            result.append(chr(b))
        else:
            result.append('.')
    return ''.join(result)


class ArenaMemoryAnalyzer:

    TARGET_PROCESS = "DOSBOX.EXE"

    def __init__(self):
        self.pid: Optional[int] = None
        self.handle: Optional[int] = None
        self.base_address: int = 0
        self._can_write: bool = False
        self._watch_list: list[WatchEntry] = []

        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._setup_api()

    def _setup_api(self):
        k = self._kernel32
        k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
        k.Process32First.restype = wintypes.BOOL
        k.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
        k.Process32Next.restype = wintypes.BOOL
        k.Module32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32)]
        k.Module32First.restype = wintypes.BOOL
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.ReadProcessMemory.restype = wintypes.BOOL
        k.WriteProcessMemory.restype = wintypes.BOOL
        k.CloseHandle.restype = wintypes.BOOL
        k.VirtualQueryEx.restype = ctypes.c_size_t
        k.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)]
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL


    def find_pid(self) -> Optional[int]:
        snapshot = self._kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            return None

        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)

        try:
            found = self._kernel32.Process32First(snapshot, ctypes.byref(entry))
            while found:
                name = entry.szExeFile.decode("utf-8", errors="ignore").upper()
                if name == self.TARGET_PROCESS:
                    return entry.th32ProcessID
                found = self._kernel32.Process32Next(snapshot, ctypes.byref(entry))
        finally:
            self._kernel32.CloseHandle(snapshot)

        return None

    def get_image_path(self) -> Optional[str]:
        pid = self.find_pid()
        if not pid:
            return None
        h = self._kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buf))
            ok = self._kernel32.QueryFullProcessImageNameW(
                h, 0, buf, ctypes.byref(size))
            return buf.value if ok else None
        finally:
            self._kernel32.CloseHandle(h)

    def attach(self) -> bool:
        pid = self.find_pid()
        if pid is None:
            raise RuntimeError("DOSBox.exe が見つかりません。Arenaが起動中か確認してください。")

        rw_flags = (PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
                    | PROCESS_QUERY_INFORMATION)
        handle = self._kernel32.OpenProcess(rw_flags, False, pid)
        if handle:
            self._can_write = True
        else:
            handle = self._kernel32.OpenProcess(
                PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid
            )
            self._can_write = False
        if not handle:
            raise RuntimeError(f"プロセス(PID={pid})のオープンに失敗しました。管理者権限で実行してください。")

        self.pid = pid
        self.handle = handle
        self.base_address = self._get_base_address(pid)
        return True

    @property
    def can_write(self) -> bool:
        return self._can_write and self.handle is not None

    def detach(self):
        if self.handle:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None
            self.pid = None
            self.base_address = 0

    def is_attached(self) -> bool:
        return self.handle is not None

    def _get_base_address(self, pid: int) -> int:
        TH32CS_SNAPMODULE = 0x00000008
        snapshot = self._kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
        if snapshot == wintypes.HANDLE(-1).value:
            return 0

        entry = MODULEENTRY32()
        entry.dwSize = ctypes.sizeof(MODULEENTRY32)
        try:
            if self._kernel32.Module32First(snapshot, ctypes.byref(entry)):
                return ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value or 0
        finally:
            self._kernel32.CloseHandle(snapshot)
        return 0


    def read_bytes(self, address: int, size: int) -> bytes:
        if not self.is_attached():
            raise RuntimeError("プロセスにアタッチされていません。")

        buf = (ctypes.c_char * size)()
        bytes_read = ctypes.c_size_t(0)
        ok = self._kernel32.ReadProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            buf,
            size,
            ctypes.byref(bytes_read),
        )
        if not ok:
            error = ctypes.get_last_error()
            raise OSError(f"ReadProcessMemory 失敗: address=0x{address:08X}, error={error}")
        return bytes(buf[:bytes_read.value])

    def read_u8(self, address: int) -> int:
        return struct.unpack_from("B", self.read_bytes(address, 1))[0]

    def read_u16(self, address: int) -> int:
        return struct.unpack_from("<H", self.read_bytes(address, 2))[0]

    def read_u32(self, address: int) -> int:
        return struct.unpack_from("<I", self.read_bytes(address, 4))[0]

    def read_string(self, address: int, max_len: int = 256) -> str:
        data = self.read_bytes(address, max_len)
        end = data.find(b'\x00')
        if end >= 0:
            data = data[:end]
        return data.decode("ascii", errors="replace")

    def write_bytes(self, address: int, data: bytes) -> int:
        if not self.is_attached():
            raise RuntimeError("プロセスにアタッチされていません。")
        if not self._can_write:
            raise OSError("プロセスが書き込み権限なしで開かれています。")
        n = ctypes.c_size_t(0)
        buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
        ok = self._kernel32.WriteProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            buf,
            len(data),
            ctypes.byref(n),
        )
        if not ok:
            error = ctypes.get_last_error()
            raise OSError(f"WriteProcessMemory 失敗: address=0x{address:08X}, error={error}")
        return n.value



    def _enum_readable_regions(self, start: int, end: int) -> list[tuple[int, int]]:
        regions = []
        addr = start
        mbi = MEMORY_BASIC_INFORMATION()
        while addr < end:
            ret = self._kernel32.VirtualQueryEx(
                self.handle,
                ctypes.c_void_p(addr),
                ctypes.byref(mbi),
                ctypes.sizeof(mbi),
            )
            if not ret:
                break
            region_base = mbi.BaseAddress or 0
            region_size = mbi.RegionSize
            protect = mbi.Protect
            is_committed = mbi.State == MEM_COMMIT
            is_readable  = (protect & PAGE_NOACCESS == 0) and (protect & PAGE_GUARD == 0)
            if is_committed and is_readable:
                clamp_base = max(region_base, start)
                clamp_end  = min(region_base + region_size, end)
                if clamp_end > clamp_base:
                    regions.append((clamp_base, clamp_end - clamp_base))
            addr = region_base + region_size
        return regions

    def _scan_pattern(self, needle: bytes, start: int, end: int) -> list[tuple[int, bytes]]:
        results = []
        overlap = len(needle) - 1

        for region_base, region_size in self._enum_readable_regions(start, end):
            try:
                data = self.read_bytes(region_base, region_size)
            except OSError:
                continue
            offset = 0
            while True:
                idx = data.find(needle, offset)
                if idx == -1:
                    break
                abs_addr = region_base + idx
                raw = data[idx: idx + max(len(needle), 32)]
                results.append((abs_addr, raw))
                offset = idx + 1

        return results

    def scan_string(self, text: str, start: int, end: int) -> list[ScanResult]:
        if not self.is_attached():
            raise RuntimeError("プロセスにアタッチされていません。")
        needle = text.encode("ascii")
        return [
            ScanResult(address=addr, raw_bytes=raw, display_value=_bytes_to_ascii(raw))
            for addr, raw in self._scan_pattern(needle, start, end)
        ]

    def scan_bytes(self, pattern: bytes, start: int, end: int) -> list[ScanResult]:
        if not self.is_attached():
            raise RuntimeError("プロセスにアタッチされていません。")
        return [
            ScanResult(address=addr, raw_bytes=raw, display_value=raw.hex(" ").upper())
            for addr, raw in self._scan_pattern(pattern, start, end)
        ]


    def add_watch(self, address: int, label: str) -> WatchEntry:
        entry = WatchEntry(address=address, label=label)
        self._watch_list.append(entry)
        return entry

    def remove_watch(self, address: int):
        self._watch_list = [e for e in self._watch_list if e.address != address]

    def poll_watch_list(self, size: int = 32):
        for entry in self._watch_list:
            try:
                data = self.read_bytes(entry.address, size)
                entry.changed = data != entry.current_value
                entry.last_value = entry.current_value
                entry.current_value = data
            except OSError:
                entry.changed = False

    @property
    def watch_list(self) -> list[WatchEntry]:
        return self._watch_list


    @staticmethod
    def format_hexdump(data: bytes, base_address: int, width: int = 16) -> list[dict]:
        lines = []
        for i in range(0, len(data), width):
            chunk = data[i: i + width]
            addr = base_address + i
            hex_bytes = " ".join(f"{b:02X}" for b in chunk)
            ascii_str = "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in chunk)
            lines.append({
                "addr": addr,
                "hex_bytes": hex_bytes,
                "ascii_str": ascii_str,
                "raw": chunk,
            })
        return lines
