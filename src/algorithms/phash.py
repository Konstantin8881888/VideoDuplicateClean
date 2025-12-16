import os
import gc
from collections import defaultdict

from PIL import Image
import imagehash
import numpy as np

from src.core.frame_extractor import FrameExtractor
from src.config import Config

# Настройки (можно переопределить через Config)
PHASH_HAMMING_THRESHOLD = getattr(Config, 'PHASH_HAMMING_THRESHOLD', 12)
PHASH_FRAMES = getattr(Config, 'PHASH_FRAMES', 30)  # сколько кадров брать по умолчанию

def _ensure_pil(img):
    """
    Приводим кадр к PIL.Image безопасно.
    Поддерживаем np.ndarray (BGR из OpenCV) и PIL.Image.
    Всегда возвращаем PIL.Image в режиме RGB или None при ошибке.
    """
    if img is None:
        return None

    # Если это уже PIL Image
    if isinstance(img, Image.Image):
        try:
            return img.convert("RGB")
        except Exception:
            return None

    # Пытаемся обработать numpy array
    try:
        if isinstance(img, np.ndarray):
            # Сделаем массив непрерывным и uint8, чтобы Pillow не падал
            arr = np.ascontiguousarray(img)
            if arr.dtype != np.uint8:
                try:
                    arr = arr.astype('uint8')
                except Exception:
                    # если не получилось привести тип — возвращаем None
                    return None

            # OpenCV обычно BGR -> приводим в RGB
            if arr.ndim == 3 and arr.shape[2] == 3:
                # Без глобального cv2 import: простая перестановка каналов
                try:
                    rgb = arr[:, :, ::-1]  # BGR -> RGB
                except Exception:
                    rgb = arr
            else:
                rgb = arr

            try:
                return Image.fromarray(rgb)
            except Exception:
                return None
    except Exception:
        return None

    # fallback — не удалось привести
    return None

def _compute_phashes_from_frames(frames):
    """
    frames: list of images (PIL.Image or numpy arrays)
    return: list of imagehash.ImageHash objects
    """
    hashes = []
    for f in frames:
        try:
            pil = _ensure_pil(f)
            if pil is None:
                continue
            h = imagehash.phash(pil)
            hashes.append(h)
        except Exception:
            # защищаемся от возможных ошибок на уровне Pillow/imagehash
            continue
    return hashes

def _hamming_distance(h1, h2):
    """Возвращает расстояние Хэмминга между двумя imagehash.ImageHash объектами"""
    try:
        return int(h1 - h2)
    except Exception:
        try:
            a = int(str(h1), 16)
            b = int(str(h2), 16)
            return bin(a ^ b).count('1')
        except Exception:
            return None

class PHashAlgorithm:
    """
    Алгоритм на основе перцептуального хеша (pHash).
    Более устойчивая к падениям версия.
    """
    def __init__(self, frames_to_sample: int = None, ham_thresh: int = None):
        self.name = 'phash'
        self.implemented = True
        self.frame_extractor = FrameExtractor()
        self.frames_to_sample = frames_to_sample if frames_to_sample is not None else PHASH_FRAMES
        self.ham_thresh = ham_thresh if ham_thresh is not None else PHASH_HAMMING_THRESHOLD

    def _video_to_phashes(self, video_path, frames_count=None):
        n = frames_count if frames_count is not None else self.frames_to_sample
        frames = []
        try:
            # Используем встроенный экстрактор кадров (предпочтительно)
            frames = self.frame_extractor.extract_frames(video_path, n)
        except Exception:
            # fallback: аккуратно используем OpenCV, но в локальном try/except
            try:
                import cv2
                cap = cv2.VideoCapture(video_path)
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                if total <= 0:
                    # если не удалось узнать total — делаем простую попытку чтения
                    step = 1
                else:
                    step = max(1, total // max(1, n))
                i = 0
                grabbed = 0
                while grabbed < n:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if i % step == 0:
                        # конвертим в contiguous uint8 перед добавлением
                        try:
                            arr = np.ascontiguousarray(frame)
                            if arr.dtype != np.uint8:
                                arr = arr.astype('uint8', copy=False)
                            frames.append(arr)
                        except Exception:
                            # пропускаем проблемный кадр
                            pass
                        grabbed += 1
                    i += 1
                try:
                    cap.release()
                except Exception:
                    pass
            except Exception:
                frames = []

        # Теперь преобразуем в phashes безопасно
        phashes = _compute_phashes_from_frames(frames)

        # Освобождаем память
        try:
            del frames
        except Exception:
            pass
        gc.collect()
        return phashes

    def compare_videos(self, video1_path, video2_path, max_frames=10):
        try:
            n = int(max_frames or self.frames_to_sample)
        except Exception:
            n = self.frames_to_sample

        ph1 = self._video_to_phashes(video1_path, frames_count=n)
        ph2 = self._video_to_phashes(video2_path, frames_count=n)

        if not ph1 or not ph2:
            return {'similarity': 0.0, 'frame_comparisons': []}

        # Для каждого хэша из короткого списка ищем минимальную дистанцию в длинном
        short, long = (ph1, ph2) if len(ph1) <= len(ph2) else (ph2, ph1)
        frame_comparisons = []
        total = 0.0
        valid = 0
        for h in short:
            best_dist = None
            for h2 in long:
                d = _hamming_distance(h, h2)
                if d is None:
                    continue
                if best_dist is None or d < best_dist:
                    best_dist = d
            if best_dist is None:
                sim = 0.0
            else:
                # размеры битов: imagehash.ImageHash.hash (numpy array)
                try:
                    bits = getattr(h, 'hash', None)
                    if bits is not None:
                        max_bits = int(bits.size)
                    else:
                        max_bits = 64
                except Exception:
                    max_bits = 64
                sim = 1.0 - (best_dist / float(max_bits))
                sim = max(0.0, min(1.0, sim))
            frame_comparisons.append({'similarity': sim, 'hamming_distance': int(best_dist) if best_dist is not None else None})
            total += sim
            valid += 1

        overall_similarity = (total / valid) if valid > 0 else 0.0
        return {
            'similarity': overall_similarity,
            'frame_comparisons': frame_comparisons
        }

    def find_similar_videos_optimized(self, video_files, similarity_threshold=None):
        try:
            threshold = float(similarity_threshold) if similarity_threshold is not None else float(getattr(Config, 'SIMILARITY_THRESHOLD', 0.5))
        except Exception:
            threshold = getattr(Config, 'SIMILARITY_THRESHOLD', 0.5)

        # Вычисляем phashes для каждого видео
        video_phashes = {}
        for v in video_files:
            try:
                ph = self._video_to_phashes(v, frames_count=self.frames_to_sample)
                video_phashes[v] = ph
            except Exception:
                video_phashes[v] = []

        results = []
        vids = list(video_phashes.keys())
        for i in range(len(vids)):
            for j in range(i+1, len(vids)):
                a, b = vids[i], vids[j]
                ph_a, ph_b = video_phashes.get(a, []), video_phashes.get(b, [])
                if not ph_a or not ph_b:
                    continue
                short, long = (ph_a, ph_b) if len(ph_a) <= len(ph_b) else (ph_b, ph_a)
                matches = 0
                for ha in short:
                    found = False
                    for hb in long:
                        d = _hamming_distance(ha, hb)
                        if d is None:
                            continue
                        if d <= self.ham_thresh:
                            found = True
                            break
                    if found:
                        matches += 1
                match_ratio = matches / max(1, len(short))
                if match_ratio >= threshold:
                    results.append( (a, b, float(match_ratio), {}) )

        results.sort(key=lambda x: -x[2])
        # освобождение памяти
        try:
            del video_phashes
        except Exception:
            pass
        gc.collect()
        return results