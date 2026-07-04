from __future__ import annotations
import io

def _scale_wav_volume(wav_bytes: bytes, volume: float) -> bytes:
    v = max(0.0, min(1.0, float(volume)))
    if v >= 0.999:
        return wav_bytes
    try:
        import wave
        import audioop
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wr:
            params = wr.getparams()
            frames = wr.readframes(wr.getnframes())
        scaled = audioop.mul(frames, params.sampwidth, v)
        out = io.BytesIO()
        with wave.open(out, 'wb') as ww:
            ww.setparams(params)
            ww.writeframes(scaled)
        return out.getvalue()
    except Exception:
        return wav_bytes

def play_wav_async(wav_bytes: bytes, volume: float=1.0) -> None:
    if not wav_bytes:
        return
    data = _scale_wav_volume(wav_bytes, volume)
    try:
        from services import audio_player
        audio_player.get_client().play_effect(data)
    except Exception:
        pass

def play_wav_file(path: str, volume: float=1.0) -> None:
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return
    play_wav_async(data, volume)
__all__ = ['play_wav_async', 'play_wav_file']
