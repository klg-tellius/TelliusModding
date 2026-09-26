"""Nintendo THP: the cutscene video format on ``Movie/*.thp``. A real,
publicly documented GameCube format (not reverse-engineered for this
project) - parsed and built per two official/canonical sources: the
long-standing community spec at amnoid.de/gc/thp.txt (thakis, 2005), and
Nintendo's own "Revolution THP Library Guide" (RVL-06-0017-001-D), which
independently confirmed the header layout amnoid.de's spec implies and
added detail neither this project's earlier reverse-engineering nor
amnoid.de's spec had: frames must be padded to a 32-byte boundary, and
audio sample counts per frame must be a multiple of 14 (except the last
frame) - both load-bearing for encode_thp() below.

Each frame is close to a normal JPEG ("quasi-jpeg"): literal 0xFF bytes in
the entropy-coded data are left un-escaped, unlike real JPEG (which requires
0xFF followed by 0x00 unless it's an actual marker) - see _dejpegify() /
_escape_for_thp() for converting between the two. Per the SDK guide, this is
exactly what Nintendo's own THPConv tool does too: take normal JPEG frames
(THPConv requires baseline/sequential/4:2:0, dimensions a multiple of 16,
max 672px wide) and repackage them "with no loss in picture quality from
the original JPEG data" - i.e. a repack, not a re-compression.

Audio, when present, uses the exact same DSP-ADPCM algorithm as stm.py
(see dsp_adpcm.py's decode()/encode()) - just repackaged per-frame with its
own 8-coefficient-pair table and history instead of stm.py's whole-stream
DSP header, since a THP's audio has to decode incrementally alongside the
video rather than as one block. encode_thp() encodes each channel's PCM to
ADPCM once as a whole stream (reusing dsp_adpcm.encode(), so the
coefficients are fixed for the whole video, matching the format - the SDK
guide confirms "table1"/"table2" are per-file, not per-frame), then slices
that stream into per-video-frame chunks aligned to 14-sample boundaries,
using dsp_adpcm.get_states_at() to get each chunk's starting decoder history
in one linear pass rather than an O(n^2) re-decode per chunk.

Encoding a whole video (encode_thp()) is real work, but doesn't need to be:
Nintendo's own encoder is a *repackager*, not a video codec - the hard part
(decoding an arbitrary input video into JPEG-compatible frames) belongs to
FFmpeg (see tools.py's decode_video_to_frames()/decode_video_to_wav()), not
this module.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

from . import dsp_adpcm

try:
    from PIL import Image
except ImportError as exc:
    raise ImportError("fe_modding.formats.thp requires Pillow: pip install Pillow") from exc

MAGIC = b"THP\x00"
VERSION_1_1 = 0x00011000
HEADER_SIZE = 48
AUDIO_HEADER_SIZE = 80  # ThpAudioFrameHeader: channelSize+numSamples+table1+table2+4 prevs
MAX_WIDTH = 672
COMPONENT_VIDEO = 0
COMPONENT_AUDIO = 1
COMPONENT_NONE = 0xFF


class ThpError(Exception):
    pass


@dataclass(frozen=True)
class ThpInfo:
    version: int
    width: int
    height: int
    fps: float
    num_frames: int
    has_audio: bool
    audio_channels: int
    audio_frequency: int
    first_frame_offset: int
    first_frame_size: int


def read_info(stream: BinaryIO) -> ThpInfo:
    header = stream.read(48)
    if header[0:4] != MAGIC:
        raise ThpError(f"Not a THP file (expected magic {MAGIC!r}, got {header[0:4]!r}).")

    version, _max_buffer, _max_audio_samples = struct.unpack(">III", header[4:16])
    (fps,) = struct.unpack(">f", header[16:20])
    num_frames, first_frame_size, _data_size = struct.unpack(">III", header[20:32])
    component_data_offset, _offsets_data_offset = struct.unpack(">II", header[32:40])
    first_frame_offset, _last_frame_offset = struct.unpack(">II", header[40:48])

    stream.seek(component_data_offset)
    (num_components,) = struct.unpack(">I", stream.read(4))
    component_types = stream.read(16)[:num_components]

    width = height = 0
    has_audio = False
    audio_channels = 0
    audio_frequency = 0

    for component_type in component_types:
        if component_type == COMPONENT_VIDEO:
            # THPVideoInfo: xSize, ySize, videoType (all u32) - per the official SDK
            # guide's Figure 3-1, a fixed 12 bytes regardless of version.
            w, h, _video_type = struct.unpack(">III", stream.read(12))
            width, height = w, h
        elif component_type == COMPONENT_AUDIO:
            # THPAudioInfo: sndChannels, sndFrequency, sndNumSamples, sndNumTracks (all u32).
            channels, freq, _num_samples, num_tracks = struct.unpack(">IIII", stream.read(16))
            if num_tracks > 1:
                raise ThpError(
                    f"This THP has {num_tracks} audio tracks (alternate-language dubs?) - "
                    "only single-track audio is supported."
                )
            has_audio = True
            audio_channels, audio_frequency = channels, freq
        elif component_type == COMPONENT_NONE:
            pass
        else:
            raise ThpError(f"Unrecognized THP component type {component_type}.")

    return ThpInfo(
        version=version,
        width=width,
        height=height,
        fps=fps,
        num_frames=num_frames,
        has_audio=has_audio,
        audio_channels=audio_channels,
        audio_frequency=audio_frequency,
        first_frame_offset=first_frame_offset,
        first_frame_size=first_frame_size,
    )


def read_info_path(path: Path | str) -> ThpInfo:
    with open(path, "rb") as stream:
        return read_info(stream)


def iter_frame_offsets(stream: BinaryIO, info: ThpInfo) -> list[int]:
    """Walk the frame chain to find every frame's start offset - cheap (reads
    just the small header of each frame, not frame content), so this is safe
    to call on a 100+MB file.

    Subtlety confirmed against a real file: a frame's own header does *not*
    describe its own size - frame_header.next_total_size in frame N's header
    is actually the size of frame N+1 (cross-checked the whole chain via
    each frame's prev_total_size, which does match the frame before it).
    Frame 0's size instead comes from the main THP header's first_frame_size.
    """
    offsets = []
    pos = info.first_frame_offset
    size = info.first_frame_size
    for i in range(info.num_frames):
        offsets.append(pos)
        if i == info.num_frames - 1:
            break
        stream.seek(pos)
        (next_size,) = struct.unpack(">I", stream.read(4))
        pos += size
        size = next_size
    return offsets


def read_frame(stream: BinaryIO, offset: int, info: ThpInfo) -> tuple[Optional["Image.Image"], list[list[int]]]:
    """Decode one frame: returns (video_image_or_None, audio_channel_pcm_lists)."""
    stream.seek(offset)
    header_size = 16 if info.has_audio else 12
    header = stream.read(header_size)
    _next_total, _prev_total, image_size = struct.unpack(">III", header[0:12])
    audio_size = struct.unpack(">I", header[12:16])[0] if info.has_audio else 0

    image = None
    if image_size:
        jpeg_bytes = _dejpegify(stream.read(image_size))
        image = Image.open(io.BytesIO(jpeg_bytes))
        image.load()
    else:
        stream.read(0)

    audio_channels: list[list[int]] = []
    if info.has_audio and audio_size:
        audio_channels = _decode_audio_frame(stream.read(audio_size * info.audio_channels), info.audio_channels)

    return image, audio_channels


def _decode_audio_frame(data: bytes, num_channels: int) -> list[list[int]]:
    channel_size, num_samples = struct.unpack(">II", data[0:8])
    table1 = list(struct.unpack(">16h", data[8:40]))
    table2 = list(struct.unpack(">16h", data[40:72]))  # stored even for mono, per spec
    prevs = struct.unpack(">4h", data[72:80])  # ch1_prev1, ch1_prev2, ch2_prev1, ch2_prev2

    channels = []
    body = data[80:]
    for ch in range(num_channels):
        coef = table1 if ch == 0 else table2
        chunk = body[ch * channel_size : (ch + 1) * channel_size]
        channels.append(_decode_thp_channel(chunk, coef, prevs[ch * 2], prevs[ch * 2 + 1], num_samples))

    return channels


def _decode_thp_channel(data: bytes, coef: list[int], hist1: int, hist2: int, num_samples: int) -> list[int]:
    """Same reconstruction math as dsp_adpcm.decode(), but with the 3-bit
    (not 4-bit) predictor index the THP spec calls for: "highest bit of
    byte is ignored". Kept separate from dsp_adpcm.decode() rather than
    parameterizing it, since getting this mask wrong silently reads past
    the 8-pair coefficient table (only ever an issue if that stray top bit
    is actually set in real data - not verified either way, so the safer
    of the two readings is used rather than assumed away)."""
    out: list[int] = []
    pos = 0
    remaining = num_samples
    while remaining > 0:
        header = data[pos]
        pos += 1
        predictor = (header >> 4) & 0x7
        scale = 1 << (header & 0xF)
        coef1, coef2 = coef[predictor * 2], coef[predictor * 2 + 1]

        samples_to_read = min(dsp_adpcm.SAMPLES_PER_FRAME, remaining)
        for s in range(samples_to_read):
            byte = data[pos]
            if s % 2 == 0:
                nibble = (byte >> 4) & 0xF
            else:
                nibble = byte & 0xF
                pos += 1
            if nibble >= 8:
                nibble -= 16

            sample = (((scale * nibble) << 11) + 1024 + (coef1 * hist1 + coef2 * hist2)) >> 11
            sample = dsp_adpcm._clamp16(sample)
            hist2 = hist1
            hist1 = sample
            out.append(sample)

        remaining -= samples_to_read

    return out


def _dejpegify(data: bytes) -> bytes:
    """THP stores frame data as JPEG bytes with literal 0xFF left un-escaped
    (real JPEG requires 0xFF 0x00 for a literal 0xFF in entropy-coded data).
    Re-escape it so a standard JPEG decoder accepts it, per the spec: find
    the Start-of-Scan marker, find the End-of-Image marker searching
    *backwards* from the end, and 0x00-stuff every 0xFF strictly between
    them (leaving the EOI marker itself untouched)."""
    sos = data.find(b"\xff\xda")
    if sos == -1:
        raise ThpError("No Start-of-Scan marker found in THP frame - not a valid quasi-JPEG frame.")
    eoi = data.rfind(b"\xff\xd9")
    if eoi == -1:
        raise ThpError("No End-of-Image marker found in THP frame.")

    # Entropy-coded data starts after the SOS marker's own 2 length bytes + header;
    # simplest correct boundary per the spec is "between SOS marker and EOI marker".
    scan_start = sos + 2
    prefix = data[:scan_start]
    scan_data = data[scan_start:eoi]
    suffix = data[eoi:]

    escaped = scan_data.replace(b"\xff", b"\xff\x00")
    return prefix + escaped + suffix


# -- encoding -----------------------------------------------------------------


def _as_image(item) -> tuple["Image.Image", bool]:
    """Returns (image, owned) - owned is True when item was a path we opened
    ourselves (and so must close ourselves); an already-open Image passed in
    is the caller's to manage."""
    if isinstance(item, Image.Image):
        return item, False
    return Image.open(item), True


def encode_thp(
    frames: list,
    pcm_channels: Optional[list[list[int]]],
    audio_sample_rate: int,
    fps: float,
    jpeg_quality: int = 90,
) -> bytes:
    """Build a THP file from decoded frame images and (optionally) PCM audio.

    frames: one entry per video frame, all the same size; each entry is
    either an already-open PIL Image or a path to one. A path is opened,
    encoded, and closed on its own turn rather than all at once - a
    multi-minute import video can decode to thousands of frames, more than
    either physical memory (each frame's full pixel buffer, not just its
    much smaller JPEG-encoded form, would otherwise stay resident for every
    frame at once) or the OS's open-file-handle limit (~thousands, hit
    before encoding even starts) can hold simultaneously. Width and height
    must each be a multiple of 16 (width additionally capped at 672) - these
    are THPConv's own documented restrictions, not a guess. Match an
    existing THP's own dimensions when replacing it (tools.decode_video_to_frames
    handles the scale+pad) rather than picking arbitrary ones.

    pcm_channels: one list of PCM16 samples per audio channel (1 or 2), all
    the same length, or None/[] for a silent video. If shorter than the
    video, trailing frames get silent (0-sample) audio chunks; if longer,
    the excess is dropped - same behavior THPConv's own WAV substitution
    documents.
    """
    if not frames:
        raise ThpError("Need at least one frame to encode a THP file.")

    num_frames = len(frames)
    has_audio = bool(pcm_channels)
    num_audio_channels = len(pcm_channels) if has_audio else 0
    if has_audio and num_audio_channels not in (1, 2):
        raise ThpError(f"Only mono or stereo audio is supported (got {num_audio_channels} channels).")
    if has_audio and any(len(ch) != len(pcm_channels[0]) for ch in pcm_channels):
        raise ThpError("All audio channels must have the same number of samples.")

    width = height = None
    jpeg_frames = []
    for item in frames:
        image, owned = _as_image(item)
        try:
            if width is None:
                width, height = image.size
                if width % 16 or height % 16:
                    raise ThpError(f"Width and height must each be a multiple of 16 (got {width}x{height}).")
                if width > MAX_WIDTH:
                    raise ThpError(f"Width must be at most {MAX_WIDTH} (got {width}).")
            elif image.size != (width, height):
                raise ThpError(f"All frames must be the same size (found {image.size} and {(width, height)}).")
            jpeg_frames.append(_encode_thp_jpeg(image, jpeg_quality))
        finally:
            if owned:
                image.close()

    audio_frame_bytes: list[bytes] = [b""] * num_frames
    total_audio_samples = 0
    max_audio_samples_per_frame = 0

    if has_audio:
        total_audio_samples = len(pcm_channels[0])
        channel_coefs = []
        channel_adpcm = []
        for pcm in pcm_channels:
            info = dsp_adpcm.AdpcmInfo()
            adpcm = dsp_adpcm.encode(pcm, info)
            channel_coefs.append(info.coef)
            channel_adpcm.append(adpcm)

        chunks = _compute_audio_chunks(num_frames, total_audio_samples, audio_sample_rate, fps)
        checkpoints = sorted({start for start, _ in chunks} | {total_audio_samples})
        channel_states = [
            dsp_adpcm.get_states_at(channel_adpcm[ch], channel_coefs[ch], total_audio_samples, checkpoints)
            for ch in range(num_audio_channels)
        ]

        for i, (start, count) in enumerate(chunks):
            byte_start = dsp_adpcm.bytes_for_adpcm_samples(start)
            byte_end = dsp_adpcm.bytes_for_adpcm_samples(start + count)
            per_channel_data = [channel_adpcm[ch][byte_start:byte_end] for ch in range(num_audio_channels)]
            prevs = [channel_states[ch][start] for ch in range(num_audio_channels)]
            audio_frame_bytes[i] = _build_audio_frame_bytes(per_channel_data, channel_coefs, prevs, count)
            max_audio_samples_per_frame = max(max_audio_samples_per_frame, count)

    num_components = 2 if has_audio else 1
    frame_header_size = 8 + 4 * num_components  # next+prev totals, then one size field per component

    frame_bodies = []
    component_sizes = []
    for i in range(num_frames):
        sizes = [len(jpeg_frames[i])]
        body = jpeg_frames[i]
        if has_audio:
            sizes.append(len(audio_frame_bytes[i]))
            body += audio_frame_bytes[i]
        component_sizes.append(sizes)
        frame_bodies.append(body)

    frame_totals = [
        _round_up(frame_header_size + len(frame_bodies[i]), 32) for i in range(num_frames)
    ]

    movie_data = bytearray()
    frame_offsets_in_movie = []
    for i in range(num_frames):
        frame_offsets_in_movie.append(len(movie_data))
        next_size = frame_totals[(i + 1) % num_frames]  # wraps: last frame's "next" is frame 0's size
        prev_size = frame_totals[(i - 1) % num_frames]  # frame 0's "prev" is the last frame's size
        frame_header = struct.pack(">II", next_size, prev_size) + struct.pack(
            f">{num_components}I", *component_sizes[i]
        )
        frame_bytes = frame_header + frame_bodies[i]
        frame_bytes += bytes(frame_totals[i] - len(frame_bytes))
        movie_data += frame_bytes

    frame_comp = bytearray([COMPONENT_NONE] * 16)
    frame_comp[0] = COMPONENT_VIDEO
    if has_audio:
        frame_comp[1] = COMPONENT_AUDIO
    comp_info = struct.pack(">I", num_components) + bytes(frame_comp)

    video_info = struct.pack(">III", width, height, 0)  # videoType 0 = non-interlaced

    audio_info = b""
    if has_audio:
        audio_info = struct.pack(">IIII", num_audio_channels, audio_sample_rate, total_audio_samples, 1)

    comp_info_offset = HEADER_SIZE
    movie_data_offset = comp_info_offset + len(comp_info) + len(video_info) + len(audio_info)
    last_frame_offset = movie_data_offset + frame_offsets_in_movie[-1]

    header = bytearray(HEADER_SIZE)
    struct.pack_into(">4s", header, 0, MAGIC)
    struct.pack_into(">I", header, 4, VERSION_1_1)
    struct.pack_into(">I", header, 8, max(frame_totals))  # bufSize
    struct.pack_into(">I", header, 12, max_audio_samples_per_frame)  # audioMaxSamples
    struct.pack_into(">f", header, 16, fps)
    struct.pack_into(">I", header, 20, num_frames)
    struct.pack_into(">I", header, 24, frame_totals[0])  # firstFrameSize
    struct.pack_into(">I", header, 28, len(movie_data))  # movieDataSize
    struct.pack_into(">I", header, 32, comp_info_offset)
    struct.pack_into(">I", header, 36, 0)  # offsetDataOffsets: no frame-offset table (matches real retail files)
    struct.pack_into(">I", header, 40, movie_data_offset)  # first frame offset
    struct.pack_into(">I", header, 44, last_frame_offset)

    return bytes(header) + comp_info + video_info + audio_info + bytes(movie_data)


def _round_up(value: int, align: int) -> int:
    return (value + align - 1) // align * align


def _compute_audio_chunks(num_frames: int, total_audio_samples: int, sample_rate: int, fps: float) -> list[tuple[int, int]]:
    """How many audio samples go with each video frame. Every chunk but the
    last must be a multiple of 14 samples (an ADPCM frame) per the SDK
    guide; tracks the ideal fractional audio/video ratio with an
    accumulator so rounding error doesn't drift the two out of sync over a
    long video, the same way real encoders handle a non-integer
    samples-per-frame ratio (32000/29.97 = ~1067.7)."""
    chunks = []
    consumed = 0
    target = 0.0
    for i in range(num_frames):
        target += sample_rate / fps
        if i < num_frames - 1:
            desired_total = min(int(target // dsp_adpcm.SAMPLES_PER_FRAME) * dsp_adpcm.SAMPLES_PER_FRAME, total_audio_samples)
            desired_total = max(desired_total, consumed)
        else:
            desired_total = total_audio_samples
        chunks.append((consumed, desired_total - consumed))
        consumed = desired_total
    return chunks


def _build_audio_frame_bytes(
    channel_data: list[bytes], channel_coefs: list[list[int]], channel_prevs: list[tuple[int, int]], num_samples: int
) -> bytes:
    channel_size = len(channel_data[0]) if channel_data else 0
    table1 = channel_coefs[0]
    table2 = channel_coefs[1] if len(channel_coefs) > 1 else channel_coefs[0]  # stored even for mono, per spec
    (ch1_prev1, ch1_prev2) = channel_prevs[0]
    (ch2_prev1, ch2_prev2) = channel_prevs[1] if len(channel_prevs) > 1 else (0, 0)

    header = struct.pack(">II", channel_size, num_samples)
    header += struct.pack(">16h", *table1)
    header += struct.pack(">16h", *table2)
    header += struct.pack(">hhhh", ch1_prev1, ch1_prev2, ch2_prev1, ch2_prev2)
    assert len(header) == AUDIO_HEADER_SIZE

    return header + b"".join(channel_data)


def _encode_thp_jpeg(image: "Image.Image", quality: int) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality, subsampling=2, progressive=False)
    return _escape_for_thp(buffer.getvalue())


def _escape_for_thp(jpeg_bytes: bytes) -> bytes:
    """Inverse of _dejpegify(): remove the 0x00 stuffing a normal JPEG
    encoder inserts after every literal 0xFF byte in the entropy-coded scan
    data, since THP wants those bytes literal/un-escaped. Same SOS/EOI
    boundary convention as _dejpegify(), so the two are exact inverses."""
    sos = jpeg_bytes.find(b"\xff\xda")
    if sos == -1:
        raise ThpError("Encoded frame has no Start-of-Scan marker - not a valid JPEG.")
    eoi = jpeg_bytes.rfind(b"\xff\xd9")
    if eoi == -1:
        raise ThpError("Encoded frame has no End-of-Image marker - not a valid JPEG.")

    scan_start = sos + 2
    prefix = jpeg_bytes[:scan_start]
    scan_data = jpeg_bytes[scan_start:eoi]
    suffix = jpeg_bytes[eoi:]

    unescaped = scan_data.replace(b"\xff\x00", b"\xff")
    return prefix + unescaped + suffix
