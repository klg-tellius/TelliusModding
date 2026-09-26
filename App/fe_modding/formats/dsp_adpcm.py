"""Nintendo GameCube/Wii DSP-ADPCM: the audio codec behind every ``.stm``
music track (see stm.py) and, per public documentation, THP cutscene audio
too. This is a real, standard, publicly documented codec - not something
reverse-engineered for this project - ported from Alex Barney's DspTool
(MIT license, https://github.com/Thealexbarney/DspTool), a well-established
open-source reimplementation of Nintendo's original encoder/decoder used as
the reference by several other tools (e.g. VGAudio). Decode logic also
matches vgmstream's independent implementation, cross-checked while writing
this.

Encoding (correlate_coefs() in particular) is not a simple formula - it's an
iterative statistical fit (autocorrelation + refinement passes) ported
line-for-line from the reference C source rather than reimplemented from a
description, specifically because audio has no tolerance for "close enough"
math the way image formats do: a subtly wrong constant produces audible
noise, not just a slightly-off pixel.

A "frame" is 8 bytes: 1 header byte (high nibble = which of 8 coefficient
pairs to use, low nibble = a power-of-two scale exponent) + 7 bytes holding
14 4-bit sample deltas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SAMPLES_PER_FRAME = 14
BYTES_PER_FRAME = 8


def _clamp16(value: int) -> int:
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    return value


def _c_idiv(a: int, b: int) -> int:
    """C-style integer division: truncates toward zero, unlike Python's // (floors)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


@dataclass
class AdpcmInfo:
    coef: list[int] = field(default_factory=lambda: [0] * 16)  # 8 (a, b) predictor coefficient pairs
    gain: int = 0
    pred_scale: int = 0  # the header byte of the first encoded frame
    yn1: int = 0
    yn2: int = 0
    loop_pred_scale: int = 0
    loop_yn1: int = 0
    loop_yn2: int = 0


def bytes_for_adpcm_samples(samples: int) -> int:
    frames, extra = divmod(samples, SAMPLES_PER_FRAME)
    extra_bytes = (extra // 2 + extra % 2 + 1) if extra else 0
    return BYTES_PER_FRAME * frames + extra_bytes


def get_nibble_address(samples: int) -> int:
    """Nibble offset of a given sample index (2 header nibbles precede each 14-sample frame)."""
    frames, extra = divmod(samples, SAMPLES_PER_FRAME)
    return 16 * frames + extra + 2


def get_nibbles_for_n_samples(samples: int) -> int:
    frames, extra = divmod(samples, SAMPLES_PER_FRAME)
    extra_nibbles = 0 if extra == 0 else extra + 2
    return 16 * frames + extra_nibbles


def get_sample_for_adpcm_nibble(nibble: int) -> int:
    frames, extra = divmod(nibble, 16)
    return SAMPLES_PER_FRAME * frames + extra - 2


def decode(data: bytes, info: AdpcmInfo, num_samples: int) -> list[int]:
    hist1, hist2 = info.yn1, info.yn2
    coefs = info.coef
    out: list[int] = []

    pos = 0
    remaining = num_samples
    while remaining > 0:
        header = data[pos]
        pos += 1
        predictor = (header >> 4) & 0xF
        scale = 1 << (header & 0xF)
        coef1, coef2 = coefs[predictor * 2], coefs[predictor * 2 + 1]

        samples_to_read = min(SAMPLES_PER_FRAME, remaining)
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
            sample = _clamp16(sample)

            hist2 = hist1
            hist1 = sample
            out.append(sample)

        remaining -= samples_to_read

    return out


def get_loop_context(data: bytes, info: AdpcmInfo, num_samples: int) -> None:
    """Decode without keeping output, just to capture the ADPCM state (predictor/
    scale byte and history) at the loop start point - fills in info.loop_*."""
    hist1, hist2 = info.yn1, info.yn2
    coefs = info.coef
    ps = 0

    pos = 0
    remaining = num_samples
    while remaining > 0:
        ps = data[pos]
        header = data[pos]
        pos += 1
        predictor = (header >> 4) & 0xF
        scale = 1 << (header & 0xF)
        coef1, coef2 = coefs[predictor * 2], coefs[predictor * 2 + 1]

        samples_to_read = min(SAMPLES_PER_FRAME, remaining)
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
            sample = _clamp16(sample)
            hist2 = hist1
            hist1 = sample

        remaining -= samples_to_read

    info.loop_pred_scale = ps
    info.loop_yn1 = hist1
    info.loop_yn2 = hist2


def get_states_at(data: bytes, coef: list[int], num_samples: int, sample_offsets: list[int]) -> dict[int, tuple[int, int]]:
    """Decode once, capturing (hist1, hist2) at each requested sample offset
    (each must be frame-aligned, i.e. a multiple of SAMPLES_PER_FRAME).

    Same history state get_loop_context() computes for one loop point, but
    for many checkpoints in a single pass - needed by thp.py, which has to
    know the decoder history at *every* video frame boundary (audio chunks
    a whole track's ADPCM stream into per-video-frame pieces), and
    re-running get_loop_context() once per checkpoint would be O(n^2) over
    a whole video's audio.
    """
    wanted = set(sample_offsets)
    results: dict[int, tuple[int, int]] = {}
    hist1 = hist2 = 0

    if 0 in wanted:
        results[0] = (0, 0)

    pos = 0
    remaining = num_samples
    sample_index = 0
    while remaining > 0:
        header = data[pos]
        pos += 1
        predictor = (header >> 4) & 0xF
        scale = 1 << (header & 0xF)
        coef1, coef2 = coef[predictor * 2], coef[predictor * 2 + 1]

        samples_to_read = min(SAMPLES_PER_FRAME, remaining)
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
            hist2 = hist1
            hist1 = _clamp16(sample)

        remaining -= samples_to_read
        sample_index += samples_to_read
        if sample_index in wanted:
            results[sample_index] = (hist1, hist2)

    return results


def encode(pcm: list[int], info: AdpcmInfo) -> bytes:
    """Encode PCM samples to ADPCM, filling in info.coef/pred_scale/yn1/yn2."""
    info.coef = correlate_coefs(pcm)

    num_samples = len(pcm)
    num_frames = num_samples // SAMPLES_PER_FRAME + (1 if num_samples % SAMPLES_PER_FRAME else 0)

    out = bytearray()
    # pcm_frame[0:2] carry the previous frame's last two *encoded* samples
    # (the decoder's history), pcm_frame[2:16] are this frame's 14 raw inputs.
    pcm_frame = [0] * (SAMPLES_PER_FRAME + 2)

    for i in range(num_frames):
        start = i * SAMPLES_PER_FRAME
        count = min(num_samples - start, SAMPLES_PER_FRAME)
        pcm_frame[2:16] = [0] * 14
        pcm_frame[2 : 2 + count] = pcm[start : start + count]

        # Always encode the full (zero-padded) 14 samples, matching the reference's
        # encode(): sampleCount there is hardcoded to SAMPLES_PER_FRAME regardless of
        # how many are "real" - only the output byte count is truncated for a partial
        # last frame (below), via getBytesForAdpcmSamples()/bytes_for_adpcm_samples().
        header_byte, data_bytes, encoded_tail = _encode_frame(pcm_frame, SAMPLES_PER_FRAME, info.coef)
        pcm_frame[0], pcm_frame[1] = encoded_tail

        frame_bytes = bytes([header_byte]) + data_bytes
        out += frame_bytes[: bytes_for_adpcm_samples(count)]

    info.gain = 0
    info.pred_scale = out[0] if out else 0
    info.yn1 = 0
    info.yn2 = 0
    return bytes(out)


def _encode_frame(pcm_in: list[int], sample_count: int, coefs: list[int]) -> tuple[int, bytes, tuple[int, int]]:
    """Port of DSPEncodeFrame(): tries all 8 coefficient pairs, keeps the best.
    pcm_in has 2 history samples followed by up to 14 real samples (zero-padded)."""
    in_samples = [[0] * 16 for _ in range(8)]
    out_samples = [[0] * 14 for _ in range(8)]
    scale = [0] * 8
    dist_accum = [0.0] * 8

    for i in range(8):
        coef1, coef2 = coefs[i * 2], coefs[i * 2 + 1]
        in_samples[i][0] = pcm_in[0]
        in_samples[i][1] = pcm_in[1]

        distance = 0
        for s in range(sample_count):
            v1 = _c_idiv(pcm_in[s] * coef2 + pcm_in[s + 1] * coef1, 2048)
            in_samples[i][s + 2] = v1
            v2 = pcm_in[s + 2] - v1
            v3 = 32767 if v2 >= 32767 else -32768 if v2 <= -32768 else v2
            if abs(v3) > abs(distance):
                distance = v3

        sc = 0
        while sc <= 12 and (distance > 7 or distance < -8):
            sc += 1
            distance = _c_idiv(distance, 2)  # C truncates toward zero; distance can be negative
        scale[i] = -1 if sc <= 1 else sc - 2

        index = 0
        while True:
            scale[i] += 1
            dist_accum[i] = 0.0
            index = 0

            for s in range(sample_count):
                v1 = in_samples[i][s] * coef2 + in_samples[i][s + 1] * coef1
                v2 = (pcm_in[s + 2] << 11) - v1
                divisor = (1 << scale[i]) * 2048
                v3f = v2 / divisor
                v3 = int(v3f + 0.4999999) if v2 > 0 else int(v3f - 0.4999999)

                if v3 < -8:
                    over = -8 - v3
                    if index < over:
                        index = over
                    v3 = -8
                elif v3 > 7:
                    over = v3 - 7
                    if index < over:
                        index = over
                    v3 = 7

                out_samples[i][s] = v3

                v1 = (v1 + ((v3 * (1 << scale[i])) << 11) + 1024) >> 11
                v1 = 32767 if v1 >= 32767 else -32768 if v1 <= -32768 else v1
                in_samples[i][s + 2] = v1

                err = pcm_in[s + 2] - v1
                dist_accum[i] += err * float(err)

            x = index + 8
            while x > 256:
                scale[i] += 1  # C: ++scale[i] always increments first, then clamps
                if scale[i] >= 12:
                    scale[i] = 11
                x >>= 1

            if not (scale[i] < 12 and index > 1):
                break

    best_index = min(range(8), key=lambda i: dist_accum[i])

    encoded_tail = (in_samples[best_index][sample_count], in_samples[best_index][sample_count + 1])

    header_byte = ((best_index << 4) | (scale[best_index] & 0xF)) & 0xFF

    padded = out_samples[best_index][:sample_count] + [0] * (14 - sample_count)
    data = bytearray(7)
    for y in range(7):
        data[y] = ((padded[y * 2] << 4) | (padded[y * 2 + 1] & 0xF)) & 0xFF

    return header_byte, bytes(data), encoded_tail


# -- coefficient computation (correlateCoefs) --------------------------------


def correlate_coefs(source: list[int]) -> list[int]:
    num_frames = (len(source) + SAMPLES_PER_FRAME - 1) // SAMPLES_PER_FRAME

    records: list[list[float]] = []
    prev_tail = [0, 0]  # last 2 samples of the previous 14-sample chunk (0,0 before the first)

    for i in range(num_frames):
        start = i * SAMPLES_PER_FRAME
        chunk = source[start : start + SAMPLES_PER_FRAME]
        if len(chunk) < SAMPLES_PER_FRAME:
            chunk = chunk + [0] * (SAMPLES_PER_FRAME - len(chunk))
        extended = prev_tail + chunk  # extended[2+n] == chunk[n]; extended[0:2] == history

        vec1 = _inner_product_merge(extended)
        if abs(vec1[0]) > 10.0:
            mtx = _outer_product_merge(extended)
            vec_idxs = [0, 0, 0]
            if not _analyze_ranges(mtx, vec_idxs):
                vec1 = _bidirectional_filter(mtx, vec_idxs, vec1)
                if not _quadratic_merge(vec1):
                    records.append(_finish_record(vec1))

        prev_tail = chunk[-2:]

    vec1 = [1.0, 0.0, 0.0]
    if records:  # deliberate divergence from the reference: it divides by recordCount
        # unconditionally, which for a fully-silent input (recordCount==0) produces
        # NaN coefficients in C - not a crash there, but NaN would poison every
        # downstream calculation here. Skipping leaves the inert identity vector
        # instead, which is the same "no meaningful prediction" outcome (silence).
        for record in records:
            filtered = _matrix_filter(record)
            vec1[1] += filtered[1]
            vec1[2] += filtered[2]
        vec1[1] /= len(records)
        vec1[2] /= len(records)

    vec_best = [[0.0, 0.0, 0.0] for _ in range(8)]
    vec_best[0] = _merge_finish_record(vec1)

    exp = 1
    for w in range(3):
        vec2 = [0.0, -1.0, 0.0]
        for i in range(exp):
            vec_best[exp + i] = [0.01 * vec2[y] + vec_best[i][y] for y in range(3)]
        exp = 1 << (w + 1)
        _filter_records(vec_best, exp, records)

    coefs_out = [0] * 16
    for z in range(8):
        for y, out_idx in ((1, z * 2), (2, z * 2 + 1)):
            d = -vec_best[z][y] * 2048.0
            if d > 0.0:
                coefs_out[out_idx] = 32767 if d > 32767.0 else round(d)
            else:
                coefs_out[out_idx] = -32768 if d < -32768.0 else round(d)

    return coefs_out


def _inner_product_merge(extended: list[int]) -> list[float]:
    vec_out = [0.0, 0.0, 0.0]
    for i in range(3):
        total = 0.0
        for x in range(SAMPLES_PER_FRAME):
            total -= extended[2 + x - i] * extended[2 + x]
        vec_out[i] = total
    return vec_out


def _outer_product_merge(extended: list[int]) -> list[list[float]]:
    mtx = [[0.0, 0.0, 0.0] for _ in range(3)]
    for x in range(1, 3):
        for y in range(1, 3):
            total = 0.0
            for z in range(SAMPLES_PER_FRAME):
                total += extended[2 + z - x] * extended[2 + z - y]
            mtx[x][y] = total
    return mtx


_DBL_EPSILON = 2.2204460492503131e-16  # matches C's <float.h> DBL_EPSILON


def _analyze_ranges(mtx: list[list[float]], vec_idxs_out: list[int]) -> bool:
    recips = [0.0, 0.0, 0.0]
    for x in range(1, 3):
        val = max(abs(mtx[x][1]), abs(mtx[x][2]))
        if val < _DBL_EPSILON:
            return True
        recips[x] = 1.0 / val

    max_index = 0
    for i in range(1, 3):
        for x in range(1, i):
            tmp = mtx[x][i]
            for y in range(1, x):
                tmp -= mtx[x][y] * mtx[y][i]
            mtx[x][i] = tmp

        val = 0.0
        for x in range(i, 3):
            tmp = mtx[x][i]
            for y in range(1, i):
                tmp -= mtx[x][y] * mtx[y][i]
            mtx[x][i] = tmp
            tmp = abs(tmp) * recips[x]
            if tmp >= val:
                val = tmp
                max_index = x

        if max_index != i:
            for y in range(1, 3):
                mtx[max_index][y], mtx[i][y] = mtx[i][y], mtx[max_index][y]
            recips[max_index] = recips[i]

        vec_idxs_out[i] = max_index

        if mtx[i][i] == 0.0:
            return True

        if i != 2:
            tmp = 1.0 / mtx[i][i]
            for x in range(i + 1, 3):
                mtx[x][i] *= tmp

    lo = 1.0e10
    hi = 0.0
    for i in range(1, 3):
        tmp = abs(mtx[i][i])
        lo = min(lo, tmp)
        hi = max(hi, tmp)

    if hi == 0.0 or lo / hi < 1.0e-10:
        return True
    return False


def _bidirectional_filter(mtx: list[list[float]], vec_idxs: list[int], vec_in: list[float]) -> list[float]:
    vec_out = list(vec_in)
    x = 0
    for i in range(1, 3):
        index = vec_idxs[i]
        tmp = vec_out[index]
        vec_out[index] = vec_out[i]
        if x != 0:
            for y in range(x, i):
                tmp -= vec_out[y] * mtx[i][y]
        elif tmp != 0.0:
            x = i
        vec_out[i] = tmp

    for i in range(2, 0, -1):
        tmp = vec_out[i]
        for y in range(i + 1, 3):
            tmp -= vec_out[y] * mtx[i][y]
        vec_out[i] = tmp / mtx[i][i]

    vec_out[0] = 1.0
    return vec_out


def _quadratic_merge(vec: list[float]) -> bool:
    v2 = vec[2]
    tmp = 1.0 - (v2 * v2)
    if tmp == 0.0:
        return True

    v0 = (vec[0] - (v2 * v2)) / tmp
    v1 = (vec[1] - (vec[1] * v2)) / tmp
    vec[0] = v0
    vec[1] = v1
    return abs(v1) > 1.0


def _finish_record(vec_in: list[float]) -> list[float]:
    v = list(vec_in)
    for z in (1, 2):
        if v[z] >= 1.0:
            v[z] = 0.9999999999
        elif v[z] <= -1.0:
            v[z] = -0.9999999999
    return [1.0, v[2] * v[1] + v[1], v[2]]


def _matrix_filter(src: list[float]) -> list[float]:
    mtx = [[0.0, 0.0, 0.0] for _ in range(3)]
    mtx[2][0] = 1.0
    for i in (1, 2):
        mtx[2][i] = -src[i]

    for i in (2, 1):
        val = 1.0 - (mtx[i][i] * mtx[i][i])
        for y in range(1, i + 1):
            mtx[i - 1][y] = ((mtx[i][i] * mtx[i][y]) + mtx[i][y]) / val

    dst = [1.0, 0.0, 0.0]
    for i in (1, 2):
        total = 0.0
        for y in range(1, i + 1):
            total += mtx[i][y] * dst[i - y]
        dst[i] = total
    return dst


def _merge_finish_record(src: list[float]) -> list[float]:
    dst = [1.0, 0.0, 0.0]
    tmp = [0.0, 0.0, 0.0]
    val = src[0]

    for i in (1, 2):
        v2 = 0.0
        for y in range(1, i):
            v2 += dst[y] * src[i - y]

        dst[i] = -(v2 + src[i]) / val if val > 0.0 else 0.0
        tmp[i] = dst[i]

        for y in range(1, i):
            dst[y] += dst[i] * dst[i - y]

        val *= 1.0 - (dst[i] * dst[i])

    return _finish_record(tmp)


def _contrast_vectors(source1: list[float], source2: list[float]) -> float:
    denom = 1.0 - source2[2] * source2[2]
    val = (source2[2] * source2[1] - source2[1]) / denom if denom != 0.0 else 0.0
    val1 = source1[0] ** 2 + source1[1] ** 2 + source1[2] ** 2
    val2 = source1[0] * source1[1] + source1[1] * source1[2]
    val3 = source1[0] * source1[2]
    return val1 + (2.0 * val * val2) + (2.0 * (-source2[1] * val - source2[2]) * val3)


def _filter_records(vec_best: list[list[float]], exp: int, records: list[list[float]]) -> None:
    for _pass in range(2):
        buffer_list = [[0.0, 0.0, 0.0] for _ in range(exp)]
        counts = [0] * exp

        for record in records:
            best_i = 0
            best_val = 1.0e30
            for i in range(exp):
                val = _contrast_vectors(vec_best[i], record)
                if val < best_val:
                    best_val = val
                    best_i = i
            counts[best_i] += 1
            filtered = _matrix_filter(record)
            for k in range(3):
                buffer_list[best_i][k] += filtered[k]

        for i in range(exp):
            if counts[i] > 0:
                buffer_list[i] = [v / counts[i] for v in buffer_list[i]]

        for i in range(exp):
            vec_best[i] = _merge_finish_record(buffer_list[i])
