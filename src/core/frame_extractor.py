import cv2
import os
from typing import List, Optional
import numpy as np
from src.config import Config


class FrameExtractor:
    def __init__(self):
        self.supported_formats = Config.SUPPORTED_FORMATS

    def extract_frames(self, video_path: str, num_frames: int = None) -> List[np.ndarray]:
        """
        Извлекает указанное количество кадров из видео, равномерно распределенных по времени

        Args:
            video_path: путь к видеофайлу
            num_frames: количество кадров для извлечения

        Returns:
            Список кадров в формате numpy arrays
        """
        if num_frames is None:
            num_frames = Config.DEFAULT_FRAMES_TO_COMPARE
        frames = []

        try:
            # Открываем видеофайл
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                print(f"Не удалось открыть видеофайл: {video_path}")
                return frames

            # Получаем общее количество кадров и FPS
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0

            # Если видео слишком короткое, берем все доступные кадры
            if total_frames <= num_frames:
                for i in range(total_frames):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                    ret, frame = cap.read()
                    if ret:
                        frames.append(frame)
            else:
                # Вычисляем позиции для извлечения кадров
                frame_positions = np.linspace(0, total_frames - 1, num_frames, dtype=int)

                for pos in frame_positions:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                    ret, frame = cap.read()
                    if ret:
                        frames.append(frame)

            cap.release()

        except Exception as e:
            print(f"Ошибка при извлечении кадров из {video_path}: {e}")

        return frames

    def extract_and_save_frames(self, video_path: str, output_dir: str, num_frames: int = None) -> List[str]:
        """
        Извлекает кадры и сохраняет их в файлы (для отладки)
        """
        if num_frames is None:
            num_frames = Config.DEFAULT_FRAMES_TO_COMPARE

        frames = self.extract_frames(video_path, num_frames)
        saved_paths = []

        for i, frame in enumerate(frames):
            filename = f"frame_{i}_{os.path.basename(video_path)}.jpg"
            output_path = os.path.join(output_dir, filename)
            try:
                cv2.imwrite(output_path, frame)
                saved_paths.append(output_path)
            except Exception as e:
                print(f"Ошибка при сохранении кадра {i}: {e}")

        return saved_paths

    def get_video_info(self, video_path: str) -> dict:
        """
        Получает информацию о видеофайле
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return {}

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0

            cap.release()

            return {
                'width': width,
                'height': height,
                'fps': fps,
                'total_frames': total_frames,
                'duration': duration
            }
        except Exception as e:
            print(f"Ошибка при получении информации о видео {video_path}: {e}")
            return {}