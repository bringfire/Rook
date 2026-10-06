"""Keep one named job query handle until its complete process tree settles.

Only private launch metadata is read/written. No credentials, cloud operations,
or process termination. Launched from this exact trusted package file with -I.
"""
from pathlib import Path
import sys
import time
from types import SimpleNamespace

if __package__ in (None, ''):
    # -I omits the script directory. Resolve our own installed/source package,
    # never an environment-provided PYTHONPATH or a caller-supplied module path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rook.chirp_process_job import _kernel, query_active
from rook.chirp_launch_tracking import LaunchRegistry
from rook.providers.vertex_auth import _WindowsNamedMutex


def keep(receipt, mutex_name):
    receipt = Path(receipt)
    registry = LaunchRegistry(SimpleNamespace(path=receipt.parent.parent/'vertex.json', _mutex_name=mutex_name))
    value = registry._read(receipt)
    kernel = _kernel()
    handle = kernel.OpenJobObjectW(0x0004, False, value['job_name'])
    if not handle:
        return 1
    ready = receipt.with_suffix('.ready')
    try:
        # Creator waits for this handle to exist before resuming or closing its
        # own handle. Namespace loss can never establish settlement.
        ready.write_text(value['job_name'], encoding='ascii')
        while query_active(kernel, handle):
            time.sleep(.1)
        with _WindowsNamedMutex(mutex_name, 5000):
            if receipt.exists():
                current = registry._read(receipt)
                if current['job_name'] != value['job_name'] or not current['contained']:
                    return 1
                current['settled'] = True
                registry._write(receipt, current)
        return 0
    finally:
        kernel.CloseHandle(handle)
        ready.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        raise SystemExit(keep(sys.argv[1], sys.argv[2]))
    except Exception:
        # Fail closed; no raw paths or process/account details in child output.
        raise SystemExit(1) from None
