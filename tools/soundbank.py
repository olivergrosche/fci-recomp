"""The games' sound banks (.sb2 in DVDsound.dat): list them, export their sounds as WAV and put WAVs in
their place (re/notes/SOUNDS.md).

  python -B tools/soundbank.py banks --game <folder>
  python -B tools/soundbank.py list <bank> [--game <folder>]
  python -B tools/soundbank.py export <bank> <folder> [--game <folder>] [--language <language>]
  python -B tools/soundbank.py replace <bank> <out> [<sound>=<wav> | event:<event>=<wav> ...]
                                       [--from <folder>] [--game <folder>] [--keep-rate] [--match-level]

  <bank>    a bank file (.sb2), or a bank's name (weapons_mp5) in the game's DVDsound.dat (needs --game); a
            dialogue bank, which comes once per language, as <language>/<name> (english/voices_merc1)
  --game    the game's files (its game/ folder): DVDsound.dat, lua.dat and default.xbe for the bank names,
            sounds_xb/ for the streamed sounds
  --language  the folder in sounds_xb of the dialogue streams (.LS2): a dialogue bank's own language, else
            English
  <out>    the changed bank: a .sb2 file, or a mod folder, which gets it as DVDsound/sounds_dvd/<bank>.sb2
  <sound>   a sound's (resource's) id in hex, as list prints it and export names its WAV (190025, 0x190025)
  <event>   an event's id as the scripts give it (FireSoundEvent = '1638408') or in hex (0x190008): every
            sound the event can play takes the WAV. Events and sounds count apart: event 0xad0001 may play
            sound 0xad0000
  --from    a folder of <sound>.wav files, as export writes them; only the ones that differ from the bank's
            own sound are put in (a loop's start comes from the WAV's smpl chunk)
  --keep-rate    keep the WAV's sample rate (by default it is resampled to the rate of the sound it replaces)
  --match-level  scale the WAV to the peak level of the sound it replaces

A bank names its events and sounds by id (the bank's group << 16 | a number). A sound lies in the bank (Xbox
ADPCM, mono) or is streamed from a file in sounds_xb (GameCommon.SS2, ...), which mods cannot change:
replace puts every new sound into the bank, a streamed one included (then mono). The rest of the bank stays
byte for byte.
"""

import argparse
import math
from pathlib import Path
import re
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dat2  # noqa: E402

VERSIONS = (0x00150000, 0x00170000)  # Instincts, Evolution
# the dialogue banks come once per language: \sounds_dvd\<language>\<bank>.sb2 (english/voices_merc1)
LANGUAGES = ("english", "french", "german", "italian", "spanish")
HEADER, EVENT, RESOURCE = 0x1C, 0x48, 0x58
AUDIO, SWITCH, RANDOM, SILENCE = 1, 3, 4, 8
TYPE_NAMES = {AUDIO: "audio", SWITCH: "switch", RANDOM: "random", SILENCE: "silence"}
# audio resource flags (+0x20)
STREAMED, SOFTWARE, LOOP = 0x08, 0x10, 0x400
STREAM_ONLY = STREAMED | SOFTWARE | 0x80 | 0x200 | 0x800  # bits no sound in a bank has
NO_NAME = 0xFFFFFFFF
XBOX_ADPCM = 0  # stream type (+0x48); 3 is Ubisoft's IMA ADPCM (stream.ss2), not handled here
BLOCK, BLOCK_SAMPLES = 36, 64  # an Xbox ADPCM block per channel and the samples it holds
DVD_FOLDER = "sounds_dvd"


def bank_key(name):
    """a bank's name in DVDsound.dat: \\sounds_dvd\\<name>.sb2"""
    name = name.lower()
    return dat2.key(f"{DVD_FOLDER}/{name if name.endswith('.sb2') else name + '.sb2'}")


def bank_hash(name):
    return zlib.crc32(bank_key(name).encode("latin-1")) & 0xFFFFFFFF


# ---- the bank ----


class Audio:
    """the fields of an audio resource (type 1), read from and written back into its 0x58 bytes"""

    FIELDS = {  # name: offset
        "size": 0x08,
        "extra": 0x0C,
        "offset": 0x10,
        "volume": 0x14,  # dB, 16.16
        "flags": 0x20,
        "samples": 0x28,  # a loop's intro (often 0)
        "samples_bytes": 0x2C,
        "loop_samples": 0x30,
        "loop_bytes": 0x34,
        "bytes_per_second": 0x38,
        "rate": 0x3C,
        "bits": 0x40,
        "channels": 0x44,
        "stream_type": 0x48,
        "name": 0x4C,  # offset of the stream's file name in the extra section, or NO_NAME
    }

    def __init__(self, raw):
        self.raw = bytearray(raw)

    def __getattr__(self, field):
        if field in Audio.FIELDS:
            return struct.unpack_from("<I", self.raw, Audio.FIELDS[field])[0]
        raise AttributeError(field)

    def set(self, **fields):
        for field, value in fields.items():
            struct.pack_into("<I", self.raw, Audio.FIELDS[field], value & 0xFFFFFFFF)

    @property
    def streamed(self):
        return bool(self.flags & STREAMED)

    @property
    def loop(self):
        return bool(self.flags & LOOP)

    @property
    def subblock(self):
        """the part of the bank's data it lies in: 0 for the hardware's (Xbox ADPCM), 1 for software ones"""
        return 1 if self.flags & SOFTWARE else 0

    @property
    def frames(self):
        return self.samples + self.loop_samples if self.loop else self.samples

    @property
    def volume_db(self):
        return struct.unpack_from("<i", self.raw, 0x14)[0] / 65536


class Bank:
    """events (0x48 bytes each), resources (0x58), the extra section, the data's parts and its bytes"""

    def __init__(self, b):
        if len(b) < HEADER or struct.unpack_from("<I", b, 0)[0] not in VERSIONS:
            raise ValueError("not a sound bank of Far Cry Instincts or Evolution")
        self.version, n1, n2, n3, nx, self.flag1, self.flag2 = struct.unpack_from("<7I", b, 0)
        s2 = HEADER + EVENT * n1
        sx = s2 + RESOURCE * n2
        s3 = sx + nx
        data = s3 + 8 * n3
        if data > len(b):
            raise ValueError("a sound bank shorter than its tables")
        self.events = [b[HEADER + EVENT * i : HEADER + EVENT * (i + 1)] for i in range(n1)]
        self.resources = [bytearray(b[s2 + RESOURCE * i : s2 + RESOURCE * (i + 1)]) for i in range(n2)]
        self.extra = b[sx:s3]
        self.parts = [struct.unpack_from("<II", b, s3 + 8 * i) for i in range(n3)]  # (subblock id, size)
        if data + sum(size for _, size in self.parts) != len(b):
            raise ValueError("a sound bank whose data is not the size its table gives")
        self.data = b[data:]

    def build(self):
        head = struct.pack(
            "<7I",
            self.version,
            len(self.events),
            len(self.resources),
            len(self.parts),
            len(self.extra),
            self.flag1,
            self.flag2,
        )
        parts = b"".join(struct.pack("<II", *p) for p in self.parts)
        return (
            head + b"".join(self.events) + b"".join(bytes(r) for r in self.resources) + self.extra + parts + self.data
        )

    # ids and types

    def rid(self, i):
        return struct.unpack_from("<I", self.resources[i], 0)[0]

    def rtype(self, i):
        return struct.unpack_from("<I", self.resources[i], 4)[0]

    def eid(self, i):
        return struct.unpack_from("<I", self.events[i], 0)[0]

    def etype(self, i):
        return struct.unpack_from("<I", self.events[i], 4)[0]

    def audio(self, i):
        return Audio(self.resources[i]) if self.rtype(i) == AUDIO else None

    def resource_index(self, rid):
        return next((i for i in range(len(self.resources)) if self.rid(i) == rid), None)

    def event_index(self, eid):
        return next((i for i in range(len(self.events)) if self.eid(i) == eid), None)

    def group(self):
        ids = [self.eid(i) for i in range(len(self.events))] + [self.rid(i) for i in range(len(self.resources))]
        return ids[0] >> 16 if ids else None

    # the trees

    def children(self, i):
        """[(resource index, label)] a switch or random resource chooses from"""
        r = self.resources[i]
        t = self.rtype(i)
        off, count = struct.unpack_from("<I", r, 0x0C)[0], struct.unpack_from("<I", r, 0x1C)[0]
        out = []
        if t == SWITCH:
            for k in range(count):
                index, value = struct.unpack_from("<II", self.extra, off + 8 * k)
                out.append((index & 0x3FFFFFFF, f"case {value}"))
        elif t == RANDOM:
            for k in range(count):
                index, chance, _ = struct.unpack_from("<III", self.extra, off + 12 * k)
                out.append((index & 0x3FFFFFFF, f"{chance / 655.36:.0f}%"))
        return [(j, label) for j, label in out if j < len(self.resources)]

    def event_resource(self, e):
        """the resource a play event (type 1) plays, else None"""
        if self.etype(e) != 1:
            return None
        i = struct.unpack_from("<I", self.events[e], 8)[0]
        return i if i < len(self.resources) else None

    def leaves(self, i, seen=None):
        """the audio resources resource i can play"""
        seen = set() if seen is None else seen
        if i in seen:
            return []
        seen.add(i)
        if self.rtype(i) == AUDIO:
            return [i]
        return [k for j, _ in self.children(i) for k in self.leaves(j, seen)]

    def stream_name(self, a):
        if a.name == NO_NAME:
            return None
        return self.extra[a.name :].split(b"\0")[0].decode("latin-1")

    # the data

    def part_start(self, subblock):
        """where a part of the data starts, or None when the bank has none"""
        at = 0
        for sid, size in self.parts:
            if sid == subblock:
                return at
            at += size
        return None

    def internal_bytes(self, a):
        start = self.part_start(a.subblock)
        if start is None:
            raise ValueError("a sound in a part of the bank the bank does not have")
        return self.data[start + a.offset : start + a.offset + a.size]


# ---- Xbox ADPCM ----

INDEX = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)
STEP = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97,
    107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428,
    4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350,
    22385, 24623, 27086, 29794, 32767,
)  # fmt: skip


def nibble_step(pred, index, n):
    step = STEP[index]
    diff = step >> 3
    if n & 1:
        diff += step >> 2
    if n & 2:
        diff += step >> 1
    if n & 4:
        diff += step
    pred = max(-32768, min(32767, pred - diff if n & 8 else pred + diff))
    return pred, max(0, min(88, index + INDEX[n]))


def nibble_at(i, channels, c):
    """(byte, shift) of nibble i (0..63) of channel c in a block's data: 4-byte words per channel in turn"""
    return (i // 8 * channels + c) * 4 + (i % 8) // 2, (i & 1) * 4


def adpcm_decode(b, channels):
    """[samples of each channel]: 64 a block, the header's sample and 63 of its 64 nibbles (as the Xbox)"""
    out = [[] for _ in range(channels)]
    size = BLOCK * channels
    for at in range(0, len(b) - size + 1, size):
        block = b[at : at + size]
        data = block[4 * channels :]
        for c in range(channels):
            pred, index = struct.unpack_from("<h", block, 4 * c)[0], min(block[4 * c + 2], 88)
            o = out[c]
            o.append(pred)
            for i in range(BLOCK_SAMPLES - 1):
                byte, shift = nibble_at(i, channels, c)
                pred, index = nibble_step(pred, index, (data[byte] >> shift) & 15)
                o.append(pred)
    return out


def encode_nibble(pred, index, sample):
    step = STEP[index]
    diff = sample - pred
    n = 8 if diff < 0 else 0
    diff = abs(diff)
    if diff >= step:
        n |= 4
        diff -= step
    step >>= 1
    if diff >= step:
        n |= 2
        diff -= step
    step >>= 1
    if diff >= step:
        n |= 1
    return n


def adpcm_encode(channels_samples):
    """Xbox ADPCM of [samples of each channel] (equal lengths, a multiple of 64)"""
    channels = len(channels_samples)
    n = len(channels_samples[0])
    if n % BLOCK_SAMPLES:
        raise ValueError("Xbox ADPCM needs a multiple of 64 samples")
    out = bytearray()
    index = [first_index(s) for s in channels_samples]
    for at in range(0, n, BLOCK_SAMPLES):
        block = bytearray(BLOCK * channels)
        for c, s in enumerate(channels_samples):
            pred = s[at]
            struct.pack_into("<hBB", block, 4 * c, pred, index[c], 0)
            idx = index[c]
            for i in range(BLOCK_SAMPLES - 1):
                nib = encode_nibble(pred, idx, s[at + 1 + i])
                pred, idx = nibble_step(pred, idx, nib)
                byte, shift = nibble_at(i, channels, c)
                block[4 * channels + byte] |= nib << shift
            index[c] = idx
        out += block
    return bytes(out)


def first_index(s):
    """a step index for the first block: about the size of its first changes"""
    d = max((abs(s[i + 1] - s[i]) for i in range(min(len(s), BLOCK_SAMPLES) - 1)), default=0)
    return next((i for i, step in enumerate(STEP) if step * 2 >= d), 88)


# ---- WAV ----


def read_wav(path_or_bytes):
    """(rate, [samples of each channel] as floats in -1..1, loop start or None) of a PCM or float WAV"""
    b = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    at, fmt, data, loop = 12, None, None, None
    while at + 8 <= len(b):
        cid, size = b[at : at + 4], struct.unpack_from("<I", b, at + 4)[0]
        body = b[at + 8 : at + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack_from("<HHIIHH", body, 0)
            if fmt[0] == 0xFFFE and len(body) >= 26:  # WAVE_FORMAT_EXTENSIBLE: the sub format's tag
                fmt = (struct.unpack_from("<H", body, 24)[0],) + fmt[1:]
        elif cid == b"data":
            data = body
        elif cid == b"smpl" and len(body) >= 36 + 24 and struct.unpack_from("<I", body, 28)[0]:
            loop = struct.unpack_from("<I", body, 36 + 8)[0]
        at += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError("a WAV file without fmt or data")
    tag, channels, rate, _, align, bits = fmt
    if channels < 1 or align < 1:
        raise ValueError("a WAV file with no channels")
    frames = len(data) // align
    if tag == 1 and bits == 16:
        flat = [v / 32768 for v in struct.unpack_from(f"<{frames * channels}h", data)]
    elif tag == 1 and bits == 8:
        flat = [(v - 128) / 128 for v in data[: frames * channels]]
    elif tag == 1 and bits in (24, 32):
        w = bits // 8
        flat = [
            int.from_bytes(data[i : i + w], "little", signed=True) / (1 << (bits - 1))
            for i in range(0, frames * channels * w, w)
        ]
    elif tag == 3 and bits == 32:
        flat = list(struct.unpack_from(f"<{frames * channels}f", data))
    else:
        raise ValueError(f"a WAV format this tool does not read (tag {tag}, {bits} bits)")
    return rate, [flat[c::channels] for c in range(channels)], loop


def wav_bytes(rate, channels_samples, loop=None):
    """a 16-bit PCM WAV of [int16 samples of each channel]; loop = (start, end) adds a smpl chunk"""
    channels = len(channels_samples)
    n = len(channels_samples[0]) if channels else 0
    inter = [channels_samples[c][i] for i in range(n) for c in range(channels)]
    data = struct.pack(f"<{len(inter)}h", *inter)
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * 2 * channels, 2 * channels, 16)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    if loop:
        smpl = struct.pack("<9I", 0, 0, 1_000_000_000 // rate, 60, 0, 0, 0, 1, 0)
        smpl += struct.pack("<6I", 0, 0, loop[0], loop[1] - 1, 0, 0)
        chunks += b"smpl" + struct.pack("<I", len(smpl)) + smpl
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


# ---- conversion ----


def resample(s, src, dst, taps=16):
    """s (floats) from rate src to dst: windowed sinc, low-passed below the lower rate's half"""
    if src == dst or not s:
        return list(s)
    g = math.gcd(src, dst)
    up, down = dst // g, src // g
    phases = up if up <= 4096 else 4096
    cutoff = min(1.0, dst / src) * 0.95  # of the source's Nyquist frequency
    table = []
    for p in range(phases):
        frac = p / phases
        row = []
        for k in range(-taps + 1, taps + 1):
            x = k - frac
            w = 0.42 + 0.5 * math.cos(math.pi * x / taps) + 0.08 * math.cos(2 * math.pi * x / taps)
            row.append(cutoff * (math.sin(math.pi * cutoff * x) / (math.pi * cutoff * x) if x else 1.0) * w)
        table.append(row)
    n_out = (len(s) * up + down - 1) // down
    padded = [0.0] * taps + list(s) + [0.0] * (taps + 1)
    out = []
    for n in range(n_out):
        pos = n * down  # in units of 1/up source samples
        i, rem = divmod(pos, up)
        row = table[rem * phases // up]
        window = padded[i + 1 : i + 1 + 2 * taps]
        out.append(sum(a * b for a, b in zip(row, window)))
    return out


def to_int16(s, scale=1.0):
    return [max(-32768, min(32767, round(v * 32767 * scale))) for v in s]


def mix_down(channels_samples, channels):
    """the WAV's channels as `channels` channels: averaged to one, or one copied to two"""
    if len(channels_samples) == channels:
        return channels_samples
    mono = [sum(v) / len(channels_samples) for v in zip(*channels_samples)]
    return [mono] * channels


def peak(channels_samples):
    return max((abs(v) for s in channels_samples for v in s), default=0)


# ---- reading the sounds ----


def stream_file(game, name, language):
    """the file a streamed sound lies in: sounds_xb/<name>, or sounds_xb/<language>/<name> for an .LS2"""
    folder = Path(game, "sounds_xb")
    if name.lower().endswith(".ls2"):
        folder = folder / language
    return next((p for p in folder.glob("*") if p.name.lower() == name.lower()), folder / name)


def sound_bytes(bank, a, game=None, language="English"):
    """the encoded bytes of an audio resource: from the bank, or from its stream file (needs game)"""
    if not a.streamed:
        return bank.internal_bytes(a)
    name = bank.stream_name(a)
    if game is None:
        raise ValueError(f"a sound streamed from {name}: give --game")
    with open(stream_file(game, name, language), "rb") as f:
        f.seek(a.offset)
        return f.read(a.size)


def decode(bank, i, game=None, language="English"):
    """(rate, [int16 samples of each channel], loop (start, end) or None) of audio resource i"""
    a = bank.audio(i)
    if a.stream_type != XBOX_ADPCM:
        raise ValueError(f"stream type {a.stream_type} (Ubisoft IMA ADPCM) is not decoded by this tool")
    channels = max(1, a.channels)
    pcm = adpcm_decode(sound_bytes(bank, a, game, language), channels)
    pcm = [s[: a.frames] for s in pcm]
    loop = (a.samples, a.frames) if a.loop else None
    return a.rate, pcm, loop


# ---- replacing ----


def encode_for(a, rate, channels_samples, loop_start=None, keep_rate=False, level=None):
    """(encoded bytes, frames, intro frames, rate) of a WAV's samples in the place of audio resource a.
    Mono (a bank's own sounds are), at a's rate unless keep_rate; a loop's length is fitted to whole blocks."""
    mono = mix_down(channels_samples, 1)[0]
    target = rate if keep_rate else a.rate
    s = resample(mono, rate, target)
    if loop_start is not None:
        loop_start = round(loop_start * target / rate)
    if level is not None:
        p = peak([s])
        if p:
            s = [v * level / p for v in s]
    if a.loop:
        intro = 0 if loop_start is None else min(len(s), loop_start // BLOCK_SAMPLES * BLOCK_SAMPLES)
        body = s[intro:]
        blocks = max(1, round(len(body) / BLOCK_SAMPLES))
        if len(body) != blocks * BLOCK_SAMPLES:  # stretch the loop a little rather than leave a gap in it
            body = resample(body, len(body), blocks * BLOCK_SAMPLES)[: blocks * BLOCK_SAMPLES]
            body += [0.0] * (blocks * BLOCK_SAMPLES - len(body))
        s = s[:intro] + body
    else:
        intro = 0
        s = s + [0.0] * (-len(s) % BLOCK_SAMPLES)
    pcm = to_int16(s)
    return adpcm_encode([pcm]), len(pcm), intro, target


def in_hardware_part(bank):
    """(index, Audio) of the sounds in the bank's hardware part"""
    for i in range(len(bank.resources)):
        a = bank.audio(i)
        if a is not None and not a.streamed and a.subblock == 0:
            yield i, a


def replace(bank, sounds, keep_rate=False, match_level=False, game=None, language="English", cache=None, windows=None):
    """the bank with {resource index: (rate, [samples of each channel], loop start or None)} in place of
    those audio resources, each put into the bank's hardware part (a streamed one too, then mono).
    cache: a dict that keeps the encoded sounds, so that a WAV given for many sounds, or for the sounds of
    other banks given the same dict (a dialogue bank's languages), is encoded once.
    windows: {resource index: (rate, mono samples, start, frames)}: the sound is `frames` samples of that tape
    from `start` (both whole Xbox ADPCM blocks, whose every block decodes on its own); a tape is encoded and
    stored once, so all sounds that are stretches of it share its data (not for loops)"""
    new = {}
    cache = {} if cache is None else cache
    for i, (rate, tape, start, frames) in (windows or {}).items():
        a = bank.audio(i)
        if a is None or a.loop:
            raise ValueError(f"resource {bank.rid(i):#x} is not a sound that plays once")
        n = -(-len(tape) // BLOCK_SAMPLES) * BLOCK_SAMPLES
        if start % BLOCK_SAMPLES or frames % BLOCK_SAMPLES or frames <= 0 or start < 0 or start + frames > n:
            raise ValueError(f"resource {bank.rid(i):#x}: a window of {frames} from {start} in a tape of {n}")
        key = ("tape", rate, tuple(tape))
        if key not in cache:
            cache[key] = adpcm_encode([to_int16(list(tape) + [0.0] * (n - len(tape)))])
        b = cache[key]
        new[i] = (b, frames, 0, rate, start // BLOCK_SAMPLES * BLOCK, frames // BLOCK_SAMPLES * BLOCK)
    for i, (rate, channels_samples, loop_start) in sounds.items():
        a = bank.audio(i)
        if a is None:
            raise ValueError(f"resource {bank.rid(i):#x} is not a sound")
        level = None
        if match_level:
            try:
                level = peak(decode(bank, i, game, language)[1]) / 32768
            except (ValueError, OSError):
                level = None
        # everything encode_for's result depends on
        key = (rate, tuple(map(tuple, channels_samples)), loop_start, keep_rate, level, a.rate, a.loop)
        if key not in cache:
            cache[key] = encode_for(a, rate, channels_samples, loop_start, keep_rate, level)
        b, frames, intro, target = cache[key]
        new[i] = (b, frames, intro, target, 0, len(b))
    if not new:
        return bank.build()
    out = Bank(bank.build())
    # the hardware part anew: the pieces still used in their order, then the new ones (each once)
    start = bank.part_start(0)
    old = bank.data[start : start + dict(bank.parts)[0]] if start is not None else b""
    kept = sorted({(a.offset, a.size) for i, a in in_hardware_part(bank) if i not in new})
    part, at = bytearray(), {}
    for off, size in kept:
        at[(off, size)] = len(part)
        part += old[off : off + size]
    placed = {}
    for i, (b, frames, intro, rate, off, size) in new.items():
        if b not in placed:
            placed[b] = len(part)
            part += b
        a = Audio(out.resources[i])
        bps = rate * BLOCK // BLOCK_SAMPLES  # mono
        flags = a.flags & ~STREAM_ONLY
        fields = dict(size=size, offset=placed[b] + off, flags=flags, rate=rate, bits=16, channels=1)
        fields.update(stream_type=XBOX_ADPCM, name=NO_NAME, bytes_per_second=bps)
        if a.loop:
            ib = intro // BLOCK_SAMPLES * BLOCK
            fields.update(samples=intro, samples_bytes=ib, loop_samples=frames - intro, loop_bytes=len(b) - ib)
        else:
            fields.update(samples=frames, samples_bytes=size, loop_samples=0, loop_bytes=0)
        a.set(**fields)
        out.resources[i][:] = a.raw
    for i, a in in_hardware_part(bank):
        if i not in new:
            a.set(offset=at[(a.offset, a.size)])
            out.resources[i][:] = a.raw
    # the data: the parts in their order with the hardware part changed (or first, when the bank had none)
    data, parts, done = bytearray(), [], False
    pos = 0
    for sid, size in bank.parts:
        if sid == 0:
            data += part
            parts.append((0, len(part)))
            done = True
        else:
            data += bank.data[pos : pos + size]
            parts.append((sid, size))
        pos += size
    if not done:
        data = part + data
        parts.insert(0, (0, len(part)))
    out.parts, out.data = parts, bytes(data)
    return out.build()


# ---- the game's banks ----


def candidate_names(game):
    """strings of the scripts and the executable that may name banks"""
    names = set()
    try:
        import luadat

        for b in dat2.read(Path(game, "lua")).values():
            try:
                f = luadat.parse(b)
            except ValueError:
                continue
            for g in luadat.functions(f):
                names.update(k for k in g.k if isinstance(k, str) and 0 < len(k) < 64)
    except OSError:
        pass
    xbe = Path(game, "default.xbe")
    if xbe.is_file():
        names.update(m.decode("latin-1") for m in re.findall(rb"[A-Za-z0-9_\-]{3,63}", xbe.read_bytes()))
    return names


def bank_names(game):
    """{name hash: bank name} for the banks of the game's DVDsound named in its files, a dialogue bank as
    <language>/<name> (english/voices_merc1)"""
    names = [n.lower() for n in candidate_names(game) if "\\" not in n and "/" not in n]
    found = {bank_hash(f"{lang}/{n}"): f"{lang}/{n}" for n in names for lang in LANGUAGES}
    found.update({bank_hash(n): n for n in names})
    return found


def load(bank, game=None):
    """(Bank, its name or None) of a bank file or a bank's name in the game's DVDsound"""
    p = Path(bank)
    if p.is_file():
        return Bank(p.read_bytes()), p.stem.lower()
    if game is None:
        raise SystemExit(f"error: no file {bank}; give --game to find it in DVDsound.dat")
    files = dat2.read(Path(game, "DVDsound"))
    h = bank_hash(bank)
    if h not in files:
        raise SystemExit(f"error: DVDsound.dat has no bank {bank_key(bank)}")
    return Bank(files[h]), bank.lower().removesuffix(".sb2")


def language_of(name):
    """the sounds_xb folder of a bank's language streams: French for french/voices_merc1, else English"""
    first = name.replace("\\", "/").split("/")[0].lower()
    return first.capitalize() if "/" in name.replace("\\", "/") and first in LANGUAGES else "English"


def parse_id(text):
    """a sound's id: hex, with or without 0x"""
    try:
        return int(text, 16)
    except ValueError:
        raise SystemExit(f"error: {text} is not a sound id (hex)")


def parse_event(text):
    """an event's id: decimal as the scripts give it, or hex with 0x"""
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        raise SystemExit(f"error: {text} is not an event id (decimal, or hex with 0x)")


def targets(bank, spec):
    """the audio resources `<sound>` or `event:<event>` names: the sound, or every sound the event can play"""
    if spec.lower().startswith("event:"):
        ident = parse_event(spec[6:])
        e = bank.event_index(ident)
        if e is None:
            raise SystemExit(f"error: the bank has no event {ident:#x} ({ident})")
        i = bank.event_resource(e)
        return bank.leaves(i) if i is not None else []
    ident = parse_id(spec)
    i = bank.resource_index(ident)
    if i is None or bank.rtype(i) != AUDIO:
        raise SystemExit(f"error: the bank has no sound {ident:#x}")
    return [i]


# ---- output ----


def describe(bank, i):
    t = bank.rtype(i)
    if t != AUDIO:
        return TYPE_NAMES.get(t, f"type {t}")
    a = bank.audio(i)
    where = f"streamed {bank.stream_name(a)} @{a.offset:#x}" if a.streamed else "in the bank"
    codec = "Xbox ADPCM" if a.stream_type == XBOX_ADPCM else f"stream type {a.stream_type}"
    secs = a.frames / a.rate if a.rate else 0
    loop = f", loops from {a.samples}" if a.loop else ""
    vol = f", {a.volume_db:+.0f} dB" if a.volume_db else ""
    return f"{codec} {a.channels} ch {a.rate} Hz, {secs:.3f} s{loop}{vol}, {a.size} bytes {where}"


def tree(bank, i, depth, label, seen):
    pad = "    " * depth
    head = f"{pad}{label + ': ' if label else ''}{bank.rid(i):#x} {describe(bank, i)}"
    if i in seen:
        return [head + " (above)"]
    seen.add(i)
    lines = [head]
    for j, lab in bank.children(i):
        lines += tree(bank, j, depth + 1, lab, seen)
    return lines


def listing(bank):
    lines = []
    used = set()
    for e in range(len(bank.events)):
        i = bank.event_resource(e)
        if i is None:
            lines.append(f"event {bank.eid(e):#x} ({bank.eid(e)}): type {bank.etype(e)}")
            continue
        lines.append(f"event {bank.eid(e):#x} ({bank.eid(e)}) plays")
        seen = set()
        lines += tree(bank, i, 1, "", seen)
        used |= seen
    rest = [i for i in range(len(bank.resources)) if i not in used]
    if rest:
        lines.append("no event plays")
        lines += [f"    {bank.rid(i):#x} {describe(bank, i)}" for i in rest]
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("banks", "list", "export", "replace"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--game")
    ap.add_argument("--language")
    ap.add_argument("--from", dest="source")
    ap.add_argument("--keep-rate", action="store_true")
    ap.add_argument("--match-level", action="store_true")
    a = ap.parse_args()
    if a.command == "banks":
        if not a.game:
            raise SystemExit("error: banks needs --game")
        names = bank_names(a.game)
        for h, b in dat2.read(Path(a.game, "DVDsound")).items():
            try:
                bank = Bank(b)
            except ValueError:
                print(f"{h:08x} {len(b):9d}  {names.get(h, '?')} (not a bank)")
                continue
            sounds = [bank.audio(i) for i in range(len(bank.resources)) if bank.rtype(i) == AUDIO]
            inside = sum(not s.streamed for s in sounds)
            print(
                f"{h:08x} {len(b):9d}  {names.get(h, '?'):32s} group {bank.group()}, {len(bank.events)} events, "
                f"{len(sounds)} sounds ({inside} in the bank)"
            )
        return
    if not a.args:
        raise SystemExit(f"error: {a.command} needs a bank")
    bank, name = load(a.args[0], a.game)
    # the .LS2 streams of a dialogue bank lie in its language's folder (sounds_xb/French/...)
    a.language = a.language or language_of(name)
    if a.command == "list":
        print(f"{name}: version {bank.version:#x}, group {bank.group()}, {len(bank.data)} bytes of sound data")
        print("\n".join(listing(bank)))
    elif a.command == "export":
        if len(a.args) < 2:
            raise SystemExit("error: export needs a folder")
        out = Path(a.args[1])
        out.mkdir(parents=True, exist_ok=True)
        for i in range(len(bank.resources)):
            if bank.rtype(i) != AUDIO:
                continue
            try:
                rate, pcm, loop = decode(bank, i, a.game, a.language)
            except (ValueError, OSError) as e:
                print(f"  {bank.rid(i):#x}: not exported ({e})")
                continue
            (out / f"{bank.rid(i):x}.wav").write_bytes(wav_bytes(rate, pcm, loop))
            print(f"  {bank.rid(i):x}.wav  {describe(bank, i)}")
    else:
        if len(a.args) < 2:
            raise SystemExit("error: replace needs where to write the bank")
        sounds = {}
        if a.source:
            for f in sorted(Path(a.source).glob("*.wav")):
                try:
                    i = bank.resource_index(int(f.stem, 16))
                except ValueError:
                    continue
                if i is None or bank.rtype(i) != AUDIO:
                    continue
                try:
                    own = wav_bytes(*decode(bank, i, a.game, a.language))
                except (ValueError, OSError):
                    own = None
                if f.read_bytes() != own:
                    sounds[i] = read_wav(f)
        for pair in a.args[2:]:
            spec, sep, wav = pair.partition("=")
            if not sep:
                raise SystemExit(f"error: {pair}: give <sound>=<wav> or event:<event>=<wav>")
            for i in targets(bank, spec):
                sounds[i] = read_wav(wav)
        out = Path(a.args[1])
        if out.suffix.lower() != ".sb2":
            out = out / "DVDsound" / DVD_FOLDER / f"{name}.sb2"
        b = replace(bank, sounds, a.keep_rate, a.match_level, a.game, a.language)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b)
        for i in sorted(sounds):
            print(f"  {bank.rid(i):#x}: {describe(Bank(b), i)}")
        print(f"{out}: {len(b)} bytes ({len(sounds)} sounds replaced)")


if __name__ == "__main__":
    main()
