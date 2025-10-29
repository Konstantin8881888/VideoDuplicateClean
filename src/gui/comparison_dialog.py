import os
from src.algorithms.comparison_manager import ComparisonManager
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QTabWidget, QWidget, QScrollArea, QGridLayout,
    QGroupBox, QProgressBar, QMessageBox, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
import cv2
import numpy as np


class FrameExtractionThread(QThread):
    """Поток для извлечения кадров из видео"""
    progress_signal = pyqtSignal(int, str)
    frames_extracted = pyqtSignal(dict)

    def __init__(self, video_paths, num_frames=5):
        super().__init__()
        self.video_paths = video_paths
        self.num_frames = num_frames

    def run(self):
        from src.core.frame_extractor import FrameExtractor
        extractor = FrameExtractor()

        results = {}
        total_videos = len(self.video_paths)

        for i, video_path in enumerate(self.video_paths):
            self.progress_signal.emit(int((i / total_videos) * 100),
                                      f"Извлекаем кадры из {os.path.basename(video_path)}")

            frames = extractor.extract_frames(video_path, self.num_frames)
            results[video_path] = frames

        self.frames_extracted.emit(results)


class ComparisonDialog(QDialog):
    """Диалог для side-by-side сравнения видеофайлов"""

    def __init__(self, video_paths, parent=None):
        super().__init__(parent)
        self.video_paths = video_paths
        self.frames_data = {}
        self.frame_similarities = []  # Будем хранить схожести для каждого кадра
        self.current_frame_index = 0
        self.comparison_manager = ComparisonManager()  # Менеджер для сравнения кадров

        self.setWindowTitle("Side-by-Side Сравнение Видео")
        self.setGeometry(100, 50, 1200, 800)
        self.setup_ui()

        # Запускаем извлечение кадров
        self.extract_frames()

    def setup_ui(self):
        """Создает интерфейс диалога"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Заголовок
        title_label = QLabel("🎬 Side-by-Side Сравнение Видео")
        title_label.setStyleSheet("font-size: 16pt; font-weight: bold; margin: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Создаем splitter для резиновой разметки
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Левая панель - первое видео
        self.left_panel = self.create_video_panel(0)
        splitter.addWidget(self.left_panel)

        # Правая панель - второе видео
        self.right_panel = self.create_video_panel(1)
        splitter.addWidget(self.right_panel)

        # Устанавливаем равные размеры
        splitter.setSizes([600, 600])

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Статус
        self.status_label = QLabel("Подготавливаем данные для сравнения...")
        layout.addWidget(self.status_label)

        # Кнопки управления
        button_layout = QHBoxLayout()

        self.prev_btn = QPushButton("⏮ Предыдущий кадр")
        self.prev_btn.clicked.connect(self.previous_frame)
        self.prev_btn.setEnabled(False)
        button_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Следующий кадр ⏭")
        self.next_btn.clicked.connect(self.next_frame)
        self.next_btn.setEnabled(False)
        button_layout.addWidget(self.next_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def create_video_panel(self, video_index):
        """Создает панель для отображения видео и информации"""
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)

        # Заголовок с именем файла
        title = QLabel(f"Видео {video_index + 1}")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; margin: 5px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Метка для отображения схожести текущего кадра
        similarity_label = QLabel("Схожесть кадра: не вычислено")
        similarity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        similarity_label.setStyleSheet("font-weight: bold; color: blue; margin: 5px;")

        # Сохраняем ссылки на метки схожести
        if not hasattr(self, 'similarity_labels'):
            self.similarity_labels = [None, None]
        self.similarity_labels[video_index] = similarity_label
        layout.addWidget(similarity_label)

        # Область для отображения кадров
        frame_label = QLabel("Кадр не загружен")
        frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_label.setMinimumHeight(300)
        frame_label.setStyleSheet("border: 2px dashed gray; margin: 5px; padding: 10px;")
        frame_label.setWordWrap(True)

        # Сохраняем ссылки на метки кадров
        if not hasattr(self, 'frame_labels'):
            self.frame_labels = [None, None]
        self.frame_labels[video_index] = frame_label
        layout.addWidget(frame_label)

        # Информация о номере кадра
        frame_info_label = QLabel("Кадр: 0/0")
        frame_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Сохраняем ссылки на метки информации о кадрах
        if not hasattr(self, 'frame_info_labels'):
            self.frame_info_labels = [None, None]
        self.frame_info_labels[video_index] = frame_info_label
        layout.addWidget(frame_info_label)

        # Информация о файле
        info_group = QGroupBox("Информация о файле")
        info_layout = QVBoxLayout()
        info_group.setLayout(info_layout)

        file_info = QTextEdit()
        file_info.setMaximumHeight(150)
        file_info.setReadOnly(True)

        # Сохраняем ссылки на информацию о файлах
        if not hasattr(self, 'file_infos'):
            self.file_infos = [None, None]
        self.file_infos[video_index] = file_info
        info_layout.addWidget(file_info)

        layout.addWidget(info_group)

        return panel

    def extract_frames(self):
        """Запускает извлечение кадров из видео"""
        self.progress_bar.setVisible(True)
        self.status_label.setText("Извлекаем кадры из видео...")

        self.extraction_thread = FrameExtractionThread(self.video_paths, num_frames=10)  # Увеличили до 10 кадров
        self.extraction_thread.progress_signal.connect(self.update_extraction_progress)
        self.extraction_thread.frames_extracted.connect(self.on_frames_extracted)
        self.extraction_thread.start()

    def calculate_frame_similarities(self):
        """Вычисляет схожесть для каждой пары кадров"""
        self.frame_similarities = []

        if len(self.video_paths) < 2:
            return

        video1_frames = self.frames_data.get(self.video_paths[0], [])
        video2_frames = self.frames_data.get(self.video_paths[1], [])

        # Вычисляем схожесть для каждой пары кадров
        min_frames = min(len(video1_frames), len(video2_frames))

        for i in range(min_frames):
            frame1 = video1_frames[i]
            frame2 = video2_frames[i]

            # Вычисляем схожесть между кадрами
            similarity_result = self.comparison_manager.compare_images(frame1, frame2)
            similarity = similarity_result.get('overall', 0.0)

            self.frame_similarities.append(similarity)

    def update_extraction_progress(self, progress, message):
        """Обновляет прогресс извлечения кадров"""
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)

    def on_frames_extracted(self, frames_data):
        """Обрабатывает извлеченные кадры"""
        self.frames_data = frames_data
        self.progress_bar.setVisible(False)
        self.status_label.setText("Кадры успешно извлечены!")

        # Вычисляем схожести кадров
        self.calculate_frame_similarities()

        # Обновляем информацию о файлах
        self.update_file_info()

        # Показываем первый кадр
        self.show_frame(0)

        # Активируем кнопки управления
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)

    def update_file_info(self):
        """Обновляет информацию о файлах"""
        from src.core.frame_extractor import FrameExtractor
        extractor = FrameExtractor()

        for i, video_path in enumerate(self.video_paths):
            if video_path in self.frames_data and i < len(self.file_infos):
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

    def show_frame(self, frame_index):
        """Показывает кадр с указанным индексом и его схожесть"""
        self.current_frame_index = frame_index

        # Обновляем информацию о номере кадра
        max_frames = min([len(frames) for frames in self.frames_data.values() if frames])
        frame_info_text = f"Кадр: {frame_index + 1}/{max_frames}"

        for i in range(len(self.video_paths)):
            if i < len(self.frame_info_labels) and self.frame_info_labels[i]:
                self.frame_info_labels[i].setText(frame_info_text)

        # Отображаем кадры
        for i, video_path in enumerate(self.video_paths):
            if (video_path in self.frames_data and
                    frame_index < len(self.frames_data[video_path]) and
                    i < len(self.frame_labels)):
                frame = self.frames_data[video_path][frame_index]
                self.display_frame(frame, self.frame_labels[i])

        # Обновляем информацию о схожести
        self.update_similarity_display(frame_index)

    def update_similarity_display(self, frame_index):
        """Обновляет отображение схожести для текущего кадра"""
        if (frame_index < len(self.frame_similarities) and
                hasattr(self, 'similarity_labels')):

            similarity = self.frame_similarities[frame_index]
            similarity_text = f"Схожесть кадра: {similarity:.1%}"

            # Обновляем обе метки схожести
            for label in self.similarity_labels:
                if label is not None:
                    label.setText(similarity_text)

            # Также обновляем статус
            self.status_label.setText(f"Просмотр кадра {frame_index + 1}, схожесть: {similarity:.1%}")

    def display_frame(self, frame, label):
        """Отображает кадр в QLabel"""
        if frame is None or label is None:
            return

        try:
            # Конвертируем BGR в RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Получаем размеры кадра
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w

            # Создаем QImage из numpy массива
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

            # Масштабируем изображение для отображения
            pixmap = QPixmap.fromImage(q_img)
            scaled_pixmap = pixmap.scaled(400, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)

            label.setPixmap(scaled_pixmap)
            label.setText("")

        except Exception as e:
            label.setText(f"Ошибка отображения кадра: {str(e)}")

    def next_frame(self):
        """Переходит к следующему кадру"""
        max_frames = min([len(frames) for frames in self.frames_data.values() if frames])
        if self.current_frame_index < max_frames - 1:
            self.show_frame(self.current_frame_index + 1)

    def previous_frame(self):
        """Переходит к предыдущему кадру"""
        if self.current_frame_index > 0:
            self.show_frame(self.current_frame_index - 1)