"""FPGAData: framing of the timestamp stream and matching packets to shots."""

import pytest

import lib.FPGAData as m
from lib.FPGAData import FPGAData


def pkt(shot, tick=24_999_450, seconds=1_735_689_600, d=0x7FFD):
    return (f"BAAB\r{seconds >> 16:04X}\r{seconds & 0xFFFF:04X}\r{tick >> 16:04X}\r"
            f"{tick & 0xFFFF:04X}\r{d:04X}\r{shot:04X}\rFEEF\r")


class Serial:
    """read_all() returns the next chunk, then nothing."""
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def read_all(self):
        return (self.chunks.pop(0) if self.chunks else "").encode("latin-1")


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


@pytest.fixture
def make_reader(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(m, "_now", clock.now)
    monkeypatch.setattr(m, "_sleep", clock.sleep)

    def make(chunks, tick_ns=10.0):
        r = object.__new__(FPGAData)            # bypass the singleton and the real port
        r._setup(tick_ns)
        r.serial = Serial(chunks)
        r.messages = []
        r.log = lambda level, msg: r.messages.append(msg)
        return r
    return make


def shots(r, numbers):
    out = []
    for n in numbers:
        p = r.read_shot(n)
        out.append(None if p is None else p.shot)
    return out


# --- the five cases that failed with the old reader -----------------------------------

def test_normal(make_reader):
    assert shots(make_reader([pkt(1), pkt(2), pkt(3)]), [1, 2, 3]) == [1, 2, 3]


def test_two_packets_in_one_read(make_reader):
    # old reader: [1, 3, 0] (shot 2 dropped)
    assert shots(make_reader([pkt(1) + pkt(2), pkt(3)]), [1, 2, 3]) == [1, 2, 3]


def test_tail_of_previous_packet_then_new(make_reader):
    # old reader: error (footer of the old packet found before the new header)
    r = make_reader([pkt(1)[25:] + pkt(2)])
    assert shots(r, [2]) == [2]
    assert any("discarded" in msg for msg in r.messages)


def test_packet_split_over_reads(make_reader):
    p = pkt(1)
    assert shots(make_reader([p[:3], p[3:12], p[12:39], p[39:]]), [1]) == [1]


def test_missing_shot_does_not_shift_the_next(make_reader):
    # old reader: shot 3 was logged as shot 2
    r = make_reader([pkt(1), "", "", pkt(3), pkt(4)])
    assert shots(r, [1, 2, 3, 4]) == [1, None, 3, 4]
    assert any("shot 2: missing" in msg for msg in r.messages)


# --- framing robustness ---------------------------------------------------------------

def test_corrupt_byte_discards_only_that_frame(make_reader):
    bad = pkt(2).replace("8580", "85\xff0")           # non-ASCII byte on the line
    r = make_reader([pkt(1) + bad + pkt(3)])
    assert shots(r, [1, 2, 3]) == [1, None, 3]


def test_data_word_equal_to_header(make_reader):
    p = pkt(1, tick=(0x017D << 16) | 0xBAAB)         # tick low word = BAAB
    cut = p.index("\rBAAB\r") + 3                      # split inside that word
    r = make_reader([p[:cut], p[cut:]])
    q = r.read_shot(1)
    assert q is not None and q.counter == ((0x017D << 16) | 0xBAAB) * 10.0


def test_garbage_between_packets(make_reader):
    r = make_reader([pkt(1) + "xx\x00zz" + pkt(2)])
    assert shots(r, [1, 2]) == [1, 2]


def test_stale_packets_flushed_before_sequence(make_reader):
    r = make_reader([pkt(7) + pkt(8)])                # left over from an aborted run
    r.flush()
    r.serial.chunks = [pkt(1)]
    assert shots(r, [1]) == [1]
    assert any("2 stale" in msg for msg in r.messages)


def test_duplicate_packet_of_same_shot(make_reader):
    # spurious second edge on QSwitch_IN: same shot number twice
    assert shots(make_reader([pkt(1) + pkt(1) + pkt(2)]), [1, 2]) == [1, 2]


def test_timeout_when_nothing_arrives(make_reader):
    r = make_reader([])
    assert r.read_shot(1, timeout_s=1.0) is None
    assert r.read_event(timeout_s=0.5) == (0, 0, 0, 0)


# --- values ---------------------------------------------------------------------------

@pytest.mark.parametrize("tick_ns", [10.0, 1e9 / 122.88e6])
def test_values(make_reader, tick_ns):
    p = make_reader([pkt(5, tick=24_999_450, d=0x7FFD)], tick_ns).read_shot(5)
    assert p.seconds == 1_735_689_600 and p.shot == 5
    assert p.counter == pytest.approx(24_999_450 * tick_ns)
    assert p.pps_delta == pytest.approx(-2 * tick_ns)


def test_fd_run_logs_each_shot_with_its_packet(make_reader, monkeypatch):
    import lib.Run as run_module
    from lib.Run import RunFD
    from fakes import FakeDC

    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)
    dc = FakeDC()
    dc.data = make_reader([pkt(9)])                    # stale packet from before the run
    started = []
    real_write = dc.fpga.write_dio

    def write_dio(name, value):
        if name == "laser_start":
            started.append(list(dc.data.serial.chunks))
            dc.data.serial.chunks = [pkt(1), "", "", pkt(3)]    # shot 2 missing
        real_write(name, value)
    dc.fpga.write_dio = write_dio

    run = RunFD(dc, {"identity": "clf", "clf": {}})
    run.nshots = 3
    lines = []
    run.log = lambda level, msg, **kw: lines.append(msg)
    run.run()

    shot_lines = [l for l in lines if l.startswith("power ")]
    assert [l.split("counter cycle: ")[1] for l in shot_lines] == ["1", "0", "3"]
    assert started == [[]]                             # stale packet flushed before laser_start


def test_read_event_keeps_order(make_reader):
    r = make_reader([pkt(1) + pkt(2)])
    assert r.read_event()[3] == 1 and r.read_event()[3] == 2
