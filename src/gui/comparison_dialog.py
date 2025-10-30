import os
import gc
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QWidget, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage


class SafeFrameExtractionThread(QThread):
    """Безопасный поток для извлечения кадров с контролем памяти и поддержкой прерывания"""

    progress_signal = pyqtSignal(int, str)
    frames_extracted = pyqtSignal(dict, list)
    error_signal = pyqtSignal(str)

    def __init__(self, video_paths, num_frames=10):
        super().__init__()
        self.video_paths = video_paths
        self.num_frames = num_frames
        self._is_running = True

    def stop(self):
        """Остановка потока"""
        self._is_running = False

    def safe_extract_frames(self, video_path, num_frames):
        """Безопасное извлечение кадров с обработкой ошибок"""
        try:
            from src.core.frame_extractor import FrameExtractor
            extractor = FrameExtractor()
            return extractor.extract_frames(video_path, num_frames)
        except Exception as e:
            print(f"Ошибка при извлечении кадров из {video_path}: {e}")
            return []

    def calculate_similarities(self, frames1, frames2):
        """Вычисляет схожести между кадрами с защитой от ошибок"""
        try:
            from src.algorithms.comparison_manager import ComparisonManager
            manager = ComparisonManager()

            similarities = []
            min_frames = min(len(frames1), len(frames2))

            for i in range(min_frames):
                if frames1[i] is not None and frames2[i] is not None:
                    result = manager.compare_images(frames1[i], frames2[i])
                    similarities.append(result.get('overall', 0.0))
                else:
                    similarities.append(0.0)

            return similarities
        except Exception as e:
            print(f"Ошибка при вычислении схожестей: {e}")
            return [0.0] * min(len(frames1), len(frames2))

    def run(self):
        """Основной метод с защитой от падений и поддержкой прерывания"""
        try:
            results = {}
            similarities = []

            if not self._is_running:
                return

            self.progress_signal.emit(0, "Подготовка к извлечению кадров...")

            # Извлекаем кадры для каждого видео с проверкой прерывания
            for i, video_path in enumerate(self.video_paths):
                if not self._is_running:
                    break

                progress = int((i / len(self.video_paths)) * 50)
                self.progress_signal.emit(progress, f"Извлекаем кадры из {os.path.basename(video_path)}")

                frames = self.safe_extract_frames(video_path, self.num_frames)
                results[video_path] = frames

                # Принудительная очистка памяти после каждого видео
                gc.collect()

            if not self._is_running:
                return

            # Вычисляем схожести если есть два видео
            if len(self.video_paths) >= 2 and self._is_running:
                self.progress_signal.emit(75, "Вычисляем схожести кадров...")
                frames1 = results.get(self.video_paths[0], [])
                frames2 = results.get(self.video_paths[1], [])
                similarities = self.calculate_similarities(frames1, frames2)

                # Очищаем память после вычислений
                gc.collect()

            if self._is_running:
                self.progress_signal.emit(100, "Готово!")
                self.frames_extracted.emit(results, similarities)

        except Exception as e:
            error_msg = f"Критическая ошибка в потоке извлечения: {e}"
            print(error_msg)
            self.error_signal.emit(error_msg)
            self.frames_extracted.emit({}, [])


class ComparisonDialog(QDialog):
    """Стабильный диалог для side-by-side сравнения"""

    def __init__(self, video_paths, parent=None):
        super().__init__(parent)
        self.video_paths = video_paths[:2]  # Всегда только 2 видео
        self.frames_data = {}
        self.frame_similarities = []
        self.current_frame_index = 0

        self.setWindowTitle("Side-by-Side Сравнение Видео")
        self.setGeometry(100, 50, 1200, 800)
        self.setup_ui()

        # Запускаем безопасное извлечение кадров
        self.extract_frames()

    def setup_ui(self):
        """Создает стабильный интерфейс"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Заголовок
        title_label = QLabel("🎬 Side-by-Side Сравнение Видео")
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold; margin: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Основной контейнер
        main_layout = QHBoxLayout()
        layout.addLayout(main_layout)

        # Левая панель
        self.left_panel = self.create_video_panel(0)
        main_layout.addWidget(self.left_panel)

        # Правая панель
        self.right_panel = self.create_video_panel(1)
        main_layout.addWidget(self.right_panel)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(True)
        layout.addWidget(self.progress_bar)

        # Статус
        self.status_label = QLabel("Подготавливаем данные для сравнения...")
        layout.addWidget(self.status_label)

        # Кнопки управления
        self.create_control_buttons(layout)

    def create_video_panel(self, video_index):
        """Создает панель для видео"""
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)

        # Заголовок
        title = QLabel(f"Видео {video_index + 1}")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Метка схожести
        similarity_label = QLabel("Схожесть: ---")
        similarity_label.setStyleSheet("font-weight: bold; color: blue;")
        similarity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if not hasattr(self, 'similarity_labels'):
            self.similarity_labels = [None, None]
        self.similarity_labels[video_index] = similarity_label
        layout.addWidget(similarity_label)

        # Область для кадра
        frame_label = QLabel("Загрузка кадра...")
        frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_label.setMinimumSize(400, 300)
        frame_label.setStyleSheet("border: 2px solid gray; background: #f0f0f0;")

        if not hasattr(self, 'frame_labels'):
            self.frame_labels = [None, None]
        self.frame_labels[video_index] = frame_label
        layout.addWidget(frame_label)

        # Информация о кадре
        frame_info = QLabel("Кадр: 0/0")
        frame_info.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if not hasattr(self, 'frame_info_labels'):
            self.frame_info_labels = [None, None]
        self.frame_info_labels[video_index] = frame_info
        layout.addWidget(frame_info)

        # Информация о файле
        file_info = QTextEdit()
        file_info.setMaximumHeight(120)
        file_info.setReadOnly(True)

        if not hasattr(self, 'file_infos'):
            self.file_infos = [None, None]
        self.file_infos[video_index] = file_info
        layout.addWidget(file_info)

        return panel

    def create_control_buttons(self, layout):
        """Создает кнопки управления"""
        button_layout = QHBoxLayout()

        self.prev_btn = QPushButton("⏮ Предыдущий")
        self.prev_btn.clicked.connect(self.previous_frame)
        self.prev_btn.setEnabled(False)
        button_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Следующий ⏭")
        self.next_btn.clicked.connect(self.next_frame)
        self.next_btn.setEnabled(False)
        button_layout.addWidget(self.next_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.safe_close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def extract_frames(self):
        """Запускает безопасное извлечение кадров"""
        from src.config import Config
        self.extraction_thread = SafeFrameExtractionThread(self.video_paths, Config.DEFAULT_FRAMES_TO_COMPARE)
        self.extraction_thread.progress_signal.connect(self.update_progress)
        self.extraction_thread.frames_extracted.connect(self.on_frames_extracted)
        self.extraction_thread.error_signal.connect(self.on_extraction_error)
        self.extraction_thread.start()

    def update_progress(self, value: int, message: str):
        """Обновляет прогресс-бар и статус"""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def on_extraction_error(self, error_message):
        """Обработчик ошибок извлечения кадров"""
        self.status_label.setText(f"Ошибка: {error_message}")
        QMessageBox.critical(self, "Ошибка извлечения кадров", error_message)

    def on_frames_extracted(self, frames_data, frame_similarities):
        """Обрабатывает извлеченные кадры"""
        self.frames_data = frames_data
        self.frame_similarities = frame_similarities

        self.progress_bar.setVisible(False)
        self.status_label.setText("Кадры успешно извлечены!")

        # Обновляем информацию о файлах
        self.update_file_info()

        # Активируем кнопки
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)

        # Показываем первый кадр
        self.show_frame(0)

        # Принудительная очистка памяти
        gc.collect()

    def update_file_info(self):
        """Обновляет информацию о файлах"""
        from src.core.frame_extractor import FrameExtractor
        extractor = FrameExtractor()

        for i, video_path in enumerate(self.video_paths):
            if video_path in self.frames_data and i < len(self.file_infos):
                try:
                    # Получаем метаданные
                    video_info = extractor.get_video_info(video_path)
                    file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB

                    info_text = f"""📁 Файл: {os.path.basename(video_path)}
📏 Размер: {file_size:.2f} MB
🎞️ Разрешение: {video_info.get('width', 'N/A')}x{video_info.get('height', 'N/A')}
⏱️ Длительность: {video_info.get('duration', 0):.1f} сек
📊 FPS: {video_info.get('fps', 0):.1f}
🖼️ Всего кадров: {video_info.get('total_frames', 0)}
📂 Путь: {video_path}"""

                    if self.file_infos[i]:
                        self.file_infos[i].setPlainText(info_text)
                except Exception as e:
                    print(f"Ошибка при обновлении информации о файле: {e}")

    def show_frame(self, frame_index):
        """Показывает кадр с защитой от ошибок"""
        try:
            self.current_frame_index = frame_index

            # Обновляем информацию о кадре
            max_frames = min([len(frames) for frames in self.frames_data.values()])
            frame_info = f"Кадр: {frame_index + 1}/{max_frames}"

            for i in range(len(self.video_paths)):
                if i < len(self.frame_info_labels) and self.frame_info_labels[i]:
                    self.frame_info_labels[i].setText(frame_info)

            # Обновляем схожесть
            if (frame_index < len(self.frame_similarities) and
                    hasattr(self, 'similarity_labels')):

                similarity = self.frame_similarities[frame_index]
                similarity_text = f"Схожесть: {similarity:.1%}"

                for label in self.similarity_labels:
                    if label:
                        label.setText(similarity_text)

            # Отображаем кадры
            for i, video_path in enumerate(self.video_paths):
                if (video_path in self.frames_data and
                        frame_index < len(self.frames_data[video_path]) and
                        i < len(self.frame_labels)):
                    frame = self.frames_data[video_path][frame_index]
                    self.safe_display_frame(frame, self.frame_labels[i])

        except Exception as e:
            print(f"Ошибка при отображении кадра: {e}")

    def safe_display_frame(self, frame, label):
        """Безопасное отображение кадра с поддержкой разных форматов"""
        try:
            if frame is None:
                label.setText("Кадр не доступен")
                return

            # Проверяем и нормализуем формат кадра
            if len(frame.shape) == 2:  # Монохромный кадр (H, W)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
            elif frame.shape[2] == 4:  # RGBA кадр
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_RGBA2RGB)
            else:  # BGR кадр (стандартный для OpenCV)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Получаем размеры
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w

            # Проверяем корректность данных
            if frame_rgb.size == 0:
                label.setText("Пустой кадр")
                return

            # Создаем QImage
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

            if q_img.isNull():
                label.setText("Ошибка создания изображения")
                return

            # Масштабируем для отображения
            pixmap = QPixmap.fromImage(q_img)
            scaled_pixmap = pixmap.scaled(400, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)

            label.setPixmap(scaled_pixmap)

        except Exception as e:
            label.setText(f"Ошибка отображения: {str(e)[:50]}...")

    def next_frame(self):
        """Следующий кадр"""
        max_frames = min([len(frames) for frames in self.frames_data.values()])
        if self.current_frame_index < max_frames - 1:
            self.show_frame(self.current_frame_index + 1)

    def previous_frame(self):
        """Предыдущий кадр"""
        if self.current_frame_index > 0:
            self.show_frame(self.current_frame_index - 1)

    def safe_close(self):
        """Безопасное закрытие с корректной остановкой потоков"""
        try:
            # Останавливаем поток если работает
            if hasattr(self, 'extraction_thread') and self.extraction_thread.isRunning():
                self.extraction_thread.requestInterruption()  # Вежливая остановка
                if not self.extraction_thread.wait(3000):  # Ждем до 3 секунд
                    print("Поток не ответил, принудительная остановка")
                    self.extraction_thread.terminate()
                    self.extraction_thread.wait()

            # Очищаем данные
            self.frames_data.clear()
            self.frame_similarities.clear()

            # Принудительная очистка памяти
            gc.collect()

            self.close()

        except Exception as e:
            print(f"Ошибка при закрытии: {e}")
            self.close()

    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        self.safe_close()
        event.accept()