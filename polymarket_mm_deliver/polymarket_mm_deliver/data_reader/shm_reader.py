import time
from multiprocessing import shared_memory
import numpy as np

# Frame layout must match the writer (64 bytes, little-endian):
# {
#   int64  date_time_ms   # stored as monotonic_ns in the producer
#   float64 yes_bid
#   float64 yes_ask
#   float64 no_bid
#   float64 no_ask
#   int64  bucket_ts      # 15m contract UTC bucket start (seconds)
#   16 bytes padding      # reserved
# }
FRAME_DTYPE = np.dtype([
    ('date_time_ms', '<i8'),
    ('yes_bid',      '<f8'),
    ('yes_ask',      '<f8'),
    ('no_bid',       '<f8'),
    ('no_ask',       '<f8'),
    ('bucket_ts',    '<i8'),
    ('_pad',         'V16'),
], align=True)

HDR_SIZE = 64


class ShmRingReader:
    """
    Simple reader for the shared-memory ring produced by the Polymarket
    market WS collector.

    This reader:
    - Attaches to an existing shared_memory block created by the producer.
    - Reads the ring header to discover capacity and set up a NumPy view.
    - Starts reading from the current write index so that restarting the
      reader does NOT replay old data.
    """

    def __init__(
        self,
        shm_name: str,
        wait: bool = True,
        retry_interval: float = 0.5,
    ):
        """
        Attach to an existing shared-memory ring.

        Args:
            shm_name:
                Name of the shared memory block (must match the producer).
            wait:
                If True, block and keep retrying until the producer creates
                the shared memory. If False, raise FileNotFoundError when
                the shared memory does not exist yet.
            retry_interval:
                Sleep time (seconds) between attach retries when wait=True.
        """
        self.shm_name = shm_name

        shm_obj = None
        while True:
            try:
                shm_obj = shared_memory.SharedMemory(name=shm_name, create=False)
                break
            except FileNotFoundError:
                if not wait:
                    raise
                time.sleep(retry_interval)

        # Detach from the resource_tracker so it does not auto-unlink the
        # shared memory when this process exits. The producer owns the lifetime.
        try:
            from multiprocessing import resource_tracker
            resource_tracker.unregister(shm_obj._name, 'shared_memory')
        except Exception:
            pass

        self.shm = shm_obj
        self._hdr = memoryview(self.shm.buf)[:HDR_SIZE]

        # Capacity is stored at offset [16:24] in the header
        cap = int.from_bytes(self._hdr[16:24], 'little', signed=False)
        self.capacity = cap
        self.mask = cap - 1

        # Ring body: NumPy view over the frames
        self._ring = np.ndarray(
            (cap,),
            dtype=FRAME_DTYPE,
            buffer=self.shm.buf[HDR_SIZE:]
        )

        # Start reading from the current write index so a restarted reader
        # does not replay historical frames.
        self._ridx = self._read_widx()

    def _read_widx(self) -> int:
        """Read the current write index from the ring header."""
        return int.from_bytes(self._hdr[:8], 'little', signed=False)

    def read_next_blocking(self, sleep_s: float = 0.001):
        """
        Blocking read of the next frame.

        Behavior:
        - If there is no new data (reader index == write index), sleep briefly
          and retry.
        - Once a new frame is available, return a copy of that frame so the
          caller is not affected by future overwrites in the ring.
        """
        while True:
            widx = self._read_widx()
            if self._ridx < widx:
                idx = self._ridx & self.mask
                frame = self._ring[idx].copy()
                self._ridx += 1
                return frame
            time.sleep(sleep_s)

    def close(self):
        """Close the local handle to the shared memory (does not unlink it)."""
        self.shm.close()