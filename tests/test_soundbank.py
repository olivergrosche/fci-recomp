"""tools/soundbank.py on synthetic sound banks, WAVs and Xbox ADPCM (no game data)"""

import math
from pathlib import Path
import struct
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import dat2  # noqa: E402
import soundbank as sb  # noqa: E402

TOOL = Path(__file__).resolve().parents[1] / "tools" / "soundbank.py"
RATE = 32000
STREAM_AT = 0x800


def sine(n, freq=440.0, rate=RATE, amp=0.5, phase=0.0):
    return [amp * math.sin(2 * math.pi * freq * i / rate + phase) for i in range(n)]


def snr(want, got):
    sig = sum(v * v for v in want) or 1
    err = sum((a - b) ** 2 for a, b in zip(want, got)) or 1e-9
    return 10 * math.log10(sig / err)


def audio(rid, size, offset, frames, channels=1, rate=RATE, streamed=False, loop=False, name=sb.NO_NAME):
    r = bytearray(sb.RESOURCE)
    struct.pack_into("<IIIII", r, 0, rid, sb.AUDIO, size, 0, offset)
    struct.pack_into("<i", r, 0x14, -3 << 16)  # -3 dB
    flags = 0x107 | (sb.STREAMED | 0x200 if streamed else 0) | (sb.LOOP if loop else 0) | 0x5000_0000
    struct.pack_into("<I", r, 0x20, flags)
    struct.pack_into("<4I", r, 0x28, *((0, 0, frames, size) if loop else (frames, size, 0, 0)))
    struct.pack_into("<6I", r, 0x38, rate * 36 * channels // 64, rate, 16, channels, 0, name)
    return r


def chooser(rid, kind, extra, count):
    r = bytearray(sb.RESOURCE)
    struct.pack_into("<IIII", r, 0, rid, kind, 0x1234, extra)  # 0x08 left as garbage, as the games do
    struct.pack_into("<I", r, 0x1C, count)
    return r


def event(eid, kind, index, other=0):
    e = bytearray(sb.EVENT)
    struct.pack_into("<IIIII", e, 0, eid, kind, index, other, 0x10000)
    return bytes(e)


def bank_bytes(events, resources, extra, parts, data, version=0x00150000):
    head = struct.pack("<7I", version, len(events), len(resources), len(parts), len(extra), 0xFFFFFFFF, 0xFFFFFFFF)
    table = b"".join(struct.pack("<II", *p) for p in parts)
    return head + b"".join(events) + b"".join(bytes(r) for r in resources) + extra + table + data


@pytest.fixture
def sample(tmp_path):
    """a bank like a weapon's: event 0x7f0000 plays a switch between a sound in the bank and a stereo one
    streamed from GameCommon.SS2; event 0x7f0001 a random choice of two loops on the same data (event
    0x7f0001 is not sound 0x7f0001); a game folder with the stream file"""
    a = sb.adpcm_encode([sb.to_int16(sine(128))])
    loop = sb.adpcm_encode([sb.to_int16(sine(192, 880))])
    stereo = sb.adpcm_encode([sb.to_int16(sine(128, 300)), sb.to_int16(sine(128, 600, amp=0.25))])
    extra = struct.pack("<4I", 1, 0, 2, 1) + b"GameCommon.SS2\0 " + struct.pack("<6I", 4, 0x8000, 0, 5, 0x8000, 0)
    resources = [
        chooser(0x7F0010, sb.SWITCH, 0, 2),
        audio(0x7F0001, len(a), 0, 128),
        audio(0x7F0002, len(stereo), STREAM_AT, 128, channels=2, streamed=True, name=16),
        chooser(0x7F0011, sb.RANDOM, 32, 2),
        audio(0x7F0003, len(loop), len(a), 192, loop=True),
        audio(0x7F0004, len(loop), len(a), 192, loop=True),
        chooser(0x7F0012, sb.SILENCE, 0, 0),
    ]
    events = [event(0x7F0000, 1, 0), event(0x7F0001, 1, 3), event(0x7F0002, 4, 0, 1)]
    b = bank_bytes(events, resources, extra, [(0, len(a) + len(loop))], a + loop)
    game = tmp_path / "game"
    (game / "sounds_xb").mkdir(parents=True)
    (game / "sounds_xb" / "GameCommon.SS2").write_bytes(bytes(STREAM_AT) + stereo + bytes(64))
    return b, game


def wav_file(path, samples, rate=RATE, loop=None):
    path.write_bytes(sb.wav_bytes(rate, [sb.to_int16(s) for s in samples], loop))
    return path


# ---- Xbox ADPCM ----


def test_adpcm_decodes_a_block_as_the_xbox_does():
    # header 1000 at step index 0, then nibbles 7 (+11, index 8), 0 (+2 of step 16, index 7), 8 (-1 of 14)
    block = bytearray(36)
    struct.pack_into("<hBB", block, 0, 1000, 0, 0)
    block[4] = 0x07  # low nibble first: 7, then 0
    block[5] = 0x08
    out = sb.adpcm_decode(bytes(block), 1)[0]
    assert len(out) == 64  # the header's sample and 63 of the 64 nibbles
    assert out[:4] == [1000, 1011, 1013, 1012]


def test_adpcm_round_trips_and_keeps_stereo_channels_apart():
    left, right = sb.to_int16(sine(640, 500)), [0] * 640
    enc = sb.adpcm_encode([left, right])
    assert len(enc) == 640 // 64 * 72  # 36 bytes a block and channel
    got = sb.adpcm_decode(enc, 2)
    assert snr(left, got[0]) > 25
    assert max(abs(v) for v in got[1]) < 8  # silence stays silence
    with pytest.raises(ValueError):
        sb.adpcm_encode([[0] * 100])


def test_adpcm_block_headers_restart_the_predictor():
    s = sb.to_int16(sine(256, 3000, amp=0.9))
    enc = sb.adpcm_encode([s])
    for k in range(4):
        pred, index, reserved = struct.unpack_from("<hBB", enc, 36 * k)
        assert pred == s[64 * k] and index <= 88 and reserved == 0


# ---- WAV and resampling ----


def test_wav_round_trips_with_its_loop():
    s = sb.to_int16(sine(300))
    rate, chans, loop = sb.read_wav(sb.wav_bytes(22050, [s, s], loop=(100, 300)))
    assert rate == 22050 and len(chans) == 2 and loop == 100
    assert snr(s, sb.to_int16(chans[0])) > 80


def test_wav_reads_8_24_bit_and_float():
    def riff(tag, bits, data, channels=1):
        align = channels * bits // 8
        fmt = struct.pack("<HHIIHH", tag, channels, 8000, 8000 * align, align, bits)
        body = b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data
        return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body

    assert sb.read_wav(riff(1, 8, bytes([128, 255, 0])))[1][0] == [0.0, 127 / 128, -1.0]
    assert sb.read_wav(riff(1, 24, (1 << 22).to_bytes(3, "little")))[1][0] == [0.5]
    assert sb.read_wav(riff(3, 32, struct.pack("<2f", 0.25, -0.5)))[1][0] == [0.25, -0.5]
    with pytest.raises(ValueError):
        sb.read_wav(riff(2, 4, b"\0\0"))


def test_resample_keeps_a_sine_and_the_length():
    s = sine(11025, 440, rate=22050)
    out = sb.resample(s, 22050, 32000)
    assert len(out) == 16000
    want = sine(len(out), 440)
    assert max(abs(a - b) for a, b in zip(out[100:-100], want[100:-100])) < 1e-3
    assert sb.resample(s, 22050, 22050) == s
    down = sb.resample(sine(32000, 15000), 32000, 22050)  # above the new Nyquist frequency: filtered out
    assert max(abs(v) for v in down[200:-200]) < 0.01


# ---- banks ----


def test_bank_round_trips_byte_for_byte(sample):
    b, _ = sample
    bank = sb.Bank(b)
    assert bank.build() == b
    assert sb.replace(bank, {}) == b
    with pytest.raises(ValueError):
        sb.Bank(b[:-4])  # the data is shorter than its table says
    with pytest.raises(ValueError):
        sb.Bank(b"\x00\x00\x16\x00" + b[4:])


def test_listing_follows_switches_and_random_choices(sample):
    b, _ = sample
    bank = sb.Bank(b)
    assert bank.leaves(0) == [1, 2] and bank.leaves(3) == [4, 5]
    text = "\n".join(sb.listing(bank))
    assert "case 0: 0x7f0001 Xbox ADPCM 1 ch 32000 Hz" in text
    assert "case 1: 0x7f0002 Xbox ADPCM 2 ch 32000 Hz" in text and "streamed GameCommon.SS2 @0x800" in text
    assert "50%: 0x7f0003" in text and "loops from 0, -3 dB" in text
    assert "event 0x7f0002 (8323074): type 4" in text
    assert "0x7f0012 silence" in text  # played by no event


def test_targets_tell_events_from_sounds(sample):
    bank = sb.Bank(sample[0])
    assert sb.targets(bank, "7f0001") == [1]
    assert sb.targets(bank, "event:0x7f0001") == [4, 5]
    assert sb.targets(bank, f"event:{0x7F0000}") == [1, 2]
    with pytest.raises(SystemExit):
        sb.targets(bank, "7f0011")  # a random choice, not a sound


def test_decode_reads_the_bank_and_the_stream_file(sample):
    b, game = sample
    bank = sb.Bank(b)
    rate, pcm, loop = sb.decode(bank, 1)
    assert rate == RATE and len(pcm) == 1 and len(pcm[0]) == 128 and loop is None
    assert snr(sb.to_int16(sine(128)), pcm[0]) > 25
    rate, pcm, _ = sb.decode(bank, 2, game)
    assert len(pcm) == 2 and snr(sb.to_int16(sine(128, 600, amp=0.25)), pcm[1]) > 20
    assert sb.decode(bank, 4)[2] == (0, 192)
    with pytest.raises(ValueError):
        sb.decode(bank, 2)  # streamed: needs the game folder


def test_replace_puts_a_streamed_sound_into_the_bank(sample):
    b, game = sample
    bank = sb.Bank(b)
    new = sb.Bank(sb.replace(bank, {2: (RATE, [sine(200, 1000)], None)}))
    a = new.audio(2)
    assert not a.streamed and a.channels == 1 and a.name == sb.NO_NAME and a.stream_type == sb.XBOX_ADPCM
    assert a.flags & 0xFFFF == 0x107 and a.flags >> 16 == 0x5000  # streamed bits off, the rest kept
    assert a.frames == 256 and a.size == 4 * 36 and a.bytes_per_second == RATE * 36 // 64 and a.rate == RATE
    assert a.volume_db == -3
    assert snr(sb.to_int16(sine(200, 1000)), sb.decode(new, 2)[1][0][:200]) > 25
    # the rest stays: events, the extra section, the other sounds' bytes; only where they lie may move
    assert new.events == bank.events and new.extra == bank.extra
    for i in (1, 4, 5):
        assert new.internal_bytes(new.audio(i)) == bank.internal_bytes(bank.audio(i))
    assert new.parts == [(0, len(new.data))] and a.offset == len(bank.data)


def test_replace_resamples_unless_told_not_to(sample):
    b, _ = sample
    bank = sb.Bank(b)
    s = sine(2205, 440, rate=22050)
    a = sb.Bank(sb.replace(bank, {1: (22050, [s], None)})).audio(1)
    assert a.rate == RATE and a.frames == 3200
    a = sb.Bank(sb.replace(bank, {1: (22050, [s], None)}, keep_rate=True)).audio(1)
    assert a.rate == 22050 and a.frames == 2240 and a.bytes_per_second == 22050 * 36 // 64


def test_a_loop_keeps_whole_blocks_and_its_start(sample):
    b, _ = sample
    bank = sb.Bank(b)
    new = sb.Bank(sb.replace(bank, {4: (RATE, [sine(1000)], None)}))
    a = new.audio(4)
    assert a.loop and a.samples == 0 and a.loop_samples == 1024 and a.loop_bytes == 16 * 36  # stretched
    new = sb.Bank(sb.replace(bank, {4: (RATE, [sine(1280)], 200)}))
    a = new.audio(4)
    assert (a.samples, a.samples_bytes, a.loop_samples) == (192, 3 * 36, 1088)
    # sound 0x7f0004 shared the old data and keeps it
    assert new.internal_bytes(new.audio(5)) == bank.internal_bytes(bank.audio(5))


def test_the_same_sound_is_stored_once(sample):
    b, _ = sample
    bank = sb.Bank(b)
    s = (RATE, [sine(640)], None)
    new = sb.Bank(sb.replace(bank, {1: s, 2: s}))
    assert new.audio(1).offset == new.audio(2).offset and new.audio(1).size == 10 * 36
    assert len(new.data) == 3 * 36 + 10 * 36  # the loops' data kept, sound 0x7f0001's old data gone


def test_a_bank_without_data_gets_its_part(sample):
    _, game = sample
    stereo = (game / "sounds_xb" / "GameCommon.SS2").read_bytes()[STREAM_AT : STREAM_AT + 144]
    res = [audio(0x10001, len(stereo), STREAM_AT, 128, channels=2, streamed=True, name=0)]
    b = bank_bytes([event(0x10000, 1, 0)], res, b"GameCommon.SS2\0\0", [], b"")
    bank = sb.Bank(b)
    assert bank.data == b"" and sb.decode(bank, 0, game)[1][0]
    new = sb.Bank(sb.replace(bank, {0: (RATE, [sine(64)], None)}))
    assert new.parts == [(0, 36)] and not new.audio(0).streamed


def test_evolution_banks_read_the_same(sample):
    b, _ = sample
    evo = b"\x00\x00\x17\x00" + b[4:]
    assert sb.Bank(evo).build() == evo


def test_load_finds_a_bank_by_name_in_dvdsound(sample, tmp_path):
    b, game = sample
    dat, fat = dat2.build({sb.bank_hash("Weapons_Test"): b, 0x1234: b"other"})
    (game / "DVDsound.dat").write_bytes(dat)
    (game / "DVDsound.fat").write_bytes(fat)
    assert sb.bank_key("weapons_test") == "\\sounds_dvd\\weapons_test.sb2"
    bank, name = sb.load("Weapons_Test", game)
    assert bank.build() == b and name == "weapons_test"
    with pytest.raises(SystemExit):
        sb.load("weapons_none", game)


def run(*args):
    return subprocess.run([sys.executable, "-B", str(TOOL), *map(str, args)], capture_output=True, text=True)


def test_cli_export_and_replace(sample, tmp_path):
    b, game = sample
    bank = tmp_path / "weapons_test.sb2"
    bank.write_bytes(b)
    out = tmp_path / "wav"
    r = run("export", bank, out, "--game", game)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in out.glob("*.wav")) == ["7f0001.wav", "7f0002.wav", "7f0003.wav", "7f0004.wav"]
    assert sb.read_wav(out / "7f0003.wav")[2] == 0  # the loop's start is in the WAV
    # exported files put back unchanged change nothing
    r = run("replace", bank, tmp_path / "same.sb2", "--from", out, "--game", game)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "same.sb2").read_bytes() == b
    # an event's sounds, into a mod folder
    wav = wav_file(tmp_path / "new.wav", [sine(500)])
    r = run("replace", bank, tmp_path / "mod", f"event:{0x7F0000}={wav}", "--game", game)
    assert r.returncode == 0, r.stderr
    new = sb.Bank((tmp_path / "mod" / "DVDsound" / "sounds_dvd" / "weapons_test.sb2").read_bytes())
    assert not new.audio(2).streamed and new.audio(1).offset == new.audio(2).offset
    r = run("replace", bank, tmp_path / "x.sb2", f"7f0010={wav}")
    assert r.returncode != 0 and "no sound 0x7f0010" in r.stderr
