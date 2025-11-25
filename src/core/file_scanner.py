import os
from typing import List
from src.config import Config


class FileScanner:
    def __init__(self):
        self.supported_formats = Config.SUPPORTED_FORMATS

    def find_video_files(self, directory: str) -> List[str]:
        """
        Находит все видеофайлы в указанной папке и подпапках
        """
        video_files = []

        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_ext = os.path.splitext(file)[1].lower()
                    if file_ext in self.supported_formats:
                        full_path = os.path.join(root, file)
                        video_files.append(full_path)
        except Exception as e:
            print(f"Ошибка при сканировании папки: {e}")

        return video_files

    def get_file_info(self, file_path: str) -> dict:
        """
        Получает базовую информацию о файле
        """
        try:
            stat = os.stat(file_path)
            return {
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'path': file_path
            }
        except Exception as e:
            print(f"Ошибка при получении информации о файле {file_path}: {e}")
            return {}