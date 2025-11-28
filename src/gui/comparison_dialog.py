import os
import gc
import cv2
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QWidget, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import QUrl


class SafeFrameExtractionThread(QThread):
    """Безопасный поток для извлечения кадров с контролем памяти и поддержкой прерывания"""

    progress_signal = pyqtSignal(int, str)
    frames_extracted = pyqtSignal(dict, list)
    error_signal = pyqtSignal(str)

    def __init__(self, video_paths, num_frames=10):
        super().__init__()
        self.video_paths = video_paths
        self.num_frames = int(num_frames or 10)
        self._is_running = True

    def stop(self):
        """Остановка потока"""
        self._is_running = False

    def safe_extract_frames(self, video_path, num_frames):
        """Безопасное извлечение кадров с обработкой ошибок (локальная нормализация путей)."""
        try:
            # Локальная нормализация пути (не требует методов диалога)
            path = video_path or ""
            try:
                from PyQt6.QtCore import QUrl
                if isinstance(path, str) and path.startswith("file://"):
                    local = QUrl(path).toLocalFile()
                    if local:
                        path = local
            except Exception:
                # если QUrl недоступен — просто продолжим
                pass

            if path.startswith("\\\\?\\"):
                path = path[4:]

            path = path.replace("/", os.sep)
            path = os.path.normpath(path)
            path = os.path.abspath(path)

            # Вызов extractor по нормализованному пути
            from src.core.frame_extractor import FrameExtractor
            extractor = FrameExtractor()
            return extractor.extract_frames(path, int(num_frames or 10))

        except Exception as e:
            print(f"Ошибка при извлечении кадров из {video_path}: {e}")
            return []

    def calculate_similarities(self, frames1, frames2):
        """Вычисляет схожести между кадрами с защитой от ошибок (возвращает подробные результаты)."""
        try:
            from src.algorithms.comparison_manager import ComparisonManager
            manager = ComparisonManager()

            max_frames = max(len(frames1), len(frames2))
            similarities = []

            for i in range(max_frames):
                f1 = frames1[i] if i < len(frames1) else None
                f2 = frames2[i] if i < len(frames2) else None

                if f1 is not None and f2 is not None:
                    res = manager.compare_images(f1, f2)  # ожидаем dict с 'overall' и детальными алгоритмами
                    # Сохраняем число (overall) для быстрого доступа
                    similarities.append(res.get('overall', 0.0))
                else:
                    similarities.append(0.0)

            return similarities
        except Exception as e:
            print(f"Ошибка при вычислении схожестей: {e}")
            # если ошибка — возвращаем пустой список или нули длины минимальной
            min_len = min(len(frames1), len(frames2))
            return [0.0] * (max(len(frames1), len(frames2))) if (frames1 or frames2) else []

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
    """Стабильный диалог для side-by-side сравнения с функцией удаления"""

    # Сигнал для запроса удаления файла у родителя (MainWindow)
    file_delete_requested = pyqtSignal(str)
    # Сигнал для уведомления основного окна об удалении файла (оставляем совместимый сигнал)
    file_deleted = pyqtSignal(str)

    def __init__(self, video_paths, parent=None):
        super().__init__(parent)
        self.video_paths = video_paths[:2]  # Всегда только 2 видео
        self.frames_data = {}
        self.frame_similarities = []
        self.current_frame_index = 0
        self.deleted_files = set()  # Множество удаленных файлов

        self.setWindowTitle("Side-by-Side Сравнение Видео")
        self.setGeometry(100, 50, 1200, 800)
        self.setup_ui()

        # Запускаем безопасное извлечение кадров
        self.extract_frames_new()

    # -----------------------
    # Вспомогательные методы
    # -----------------------
    def _normalize_local_path(self, raw_path: str) -> str:
        """Лёгкая локальная нормализация (file://, \\?\\) для безопасного использования внутри диалога"""
        try:
            path = raw_path or ""
            if path.startswith("file://"):
                q = QUrl(path)
                local = q.toLocalFile()
                if local:
                    path = local
            if path.startswith("\\\\?\\"):
                path = path[4:]
            # нормализуем слэши и путь
            path = path.replace("/", os.sep)
            path = os.path.normpath(path)
            return os.path.abspath(path)
        except Exception:
            return raw_path

    def _safe_remove_local(self, raw_path: str) -> (bool, str):
        """Попытка локального безопасного удаления (fallback, если родитель не обработал запрос)"""
        try:
            path = self._normalize_local_path(raw_path)
            candidates = [raw_path, path]
            # добавим вариант без префикса, если он есть
            if raw_path.startswith("\\\\?\\"):
                candidates.append(raw_path[4:])
            last_err = ""
            for c in candidates:
                try:
                    if os.path.exists(c):
                        os.remove(c)
                        return True, ""
                except Exception as e:
                    last_err = str(e)
            return False, last_err or "Файл не найден"
        except Exception as e:
            return False, str(e)

    # -----------------------
    # UI setup и логика
    # -----------------------
    def setup_ui(self):
        """Создает стабильный интерфейс с кнопками удаления"""
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
        """Создает панель для видео с кнопкой удаления"""
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)

        # Заголовок
        title = QLabel(f"Видео {video_index + 1}")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Кнопка удаления
        delete_btn = QPushButton("🗑️ Удалить файл")
        delete_btn.clicked.connect(lambda: self.delete_video(video_index))
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b6b;
                color: white;
                font-weight: bold;
                padding: 5px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #ff5252;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        layout.addWidget(delete_btn)

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

    def delete_video(self, video_index):
        """Запрашивает удаление у родителя; если родитель не подключён — пытаемся локально."""
        # Защита: если индекс вне диапазона
        if video_index >= len(self.video_paths):
            QMessageBox.warning(self, "Ошибка", "Некорректный индекс файла")
            return

        video_path = self.video_paths[video_index]
        # Подтверждение пользователем
        try:
            size_mb = (os.path.getsize(video_path) / (1024 * 1024)) if os.path.exists(self._normalize_local_path(video_path)) else 0.0
        except Exception:
            size_mb = 0.0

        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить файл?\n\n{os.path.basename(video_path)}\n\nРазмер: {size_mb:.1f} MB",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Если у диалога подключён обработчик file_delete_requested — используем его (рекомендуемый поток)
        if self.receivers(self.file_delete_requested) > 0:
            # Отправляем запрос родителю — родитель должен выполнить удаление и затем эмитнуть file_deleted
            self.status_label.setText("Запрос на удаление отправлен...")
            self.file_delete_requested.emit(video_path)
            # дальше родитель вызовет dialog.file_deleted.emit(path) после фактического удаления
            return

        # Иначе — fallback: пытаемся безопасно удалить локально (не рекомендуется в основной архитектуре)
        ok, err = self._safe_remove_local(video_path)
        if not ok:
            QMessageBox.critical(self, "Ошибка при удалении", f"Не удалось удалить файл: {err}")
            return

        # Если удаление прошло — аппдейтим UI и эмитим file_deleted чтобы основной код также отреагировал, если слушает
        self.deleted_files.add(video_path)
        self.update_after_deletion(video_index)
        self.file_deleted.emit(video_path)
        QMessageBox.information(self, "Успех", "Файл удалён (fallback)")
        return

    def update_after_deletion(self, video_index):
        """Обновляет интерфейс после удаления файла"""
        # Обновляем информацию о файле
        if video_index < len(self.file_infos) and self.file_infos[video_index]:
            self.file_infos[video_index].setPlainText(
                f"❌ ФАЙЛ УДАЛЕН\n\n"
                f"📁 Файл: {os.path.basename(self.video_paths[video_index])}\n"
                f"🗑️ Статус: Перемещен/удалён"
            )

        # Отключаем кнопку удаления (ищем QPushButton внутри панели)
        panel = self.left_panel if video_index == 0 else self.right_panel
        # ищем первую кнопку в panel — это наша delete
        for w in panel.findChildren(QPushButton):
            # предположительно, это кнопка удаления; отключаем и меняем текст
            w.setEnabled(False)
            w.setText("🗑️ Файл удален")

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

    def extract_frames_new(self):
        """Запускает безопасное извлечение кадров"""
        from src.config import Config
        num = getattr(Config, "DEFAULT_FRAMES_TO_COMPARE", 10)
        self.extraction_thread = SafeFrameExtractionThread(self.video_paths, num_frames=num)
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
        self.frames_data = frames_data or {}
        self.frame_similarities = frame_similarities or []

        # вычисляем доступное число кадров (максимум среди видео, либо 0)
        try:
            counts = [len(v) for v in self.frames_data.values()] if self.frames_data else []
            self.max_frames = max(counts) if counts else 0
        except Exception:
            self.max_frames = 0

        self.progress_bar.setVisible(False)
        self.status_label.setText("Кадры успешно извлечены!")

        # Обновляем информацию о файлах
        self.update_file_info()

        # Активируем кнопки (если есть хотя бы 1 кадр)
        enabled = self.max_frames > 0
        self.prev_btn.setEnabled(enabled)
        self.next_btn.setEnabled(enabled)

        # Показываем первый кадр, если есть
        if enabled:
            self.show_frame(0)
        else:
            # нет кадров — покажем информативное сообщение
            for label in self.frame_labels:
                if label:
                    label.setText("Кадры не найдены")
            for info in self.similarity_labels:
                if info:
                    info.setText("Схожесть: ---")

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
                    target = self._normalize_local_path(video_path)
                    video_info = extractor.get_video_info(target)
                    file_size = os.path.getsize(target) / (1024 * 1024)  # MB

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

            max_frames = getattr(self, 'max_frames', 0)
            frame_info = f"Кадр: {frame_index + 1}/{max_frames}" if max_frames > 0 else "Кадр: 0/0"

            for i in range(len(self.video_paths)):
                if i < len(self.frame_info_labels) and self.frame_info_labels[i]:
                    self.frame_info_labels[i].setText(frame_info)

            # Обновляем схожесть (если доступна)
            if (frame_index < len(self.frame_similarities) and hasattr(self, 'similarity_labels')):
                similarity = self.frame_similarities[frame_index]
                similarity_text = f"Схожесть: {similarity:.1%}"
            else:
                similarity_text = "Схожесть: ---"

            for label in self.similarity_labels:
                if label:
                    label.setText(similarity_text)

            # Отображаем кадры (защищённо)
            for i, video_path in enumerate(self.video_paths):
                frame = None
                if video_path in self.frames_data and frame_index < len(self.frames_data.get(video_path, [])):
                    frame = self.frames_data[video_path][frame_index]
                if i < len(self.frame_labels):
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
        max_frames = min([len(frames) for frames in self.frames_data.values()]) if self.frames_data else 0
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
                self.extraction_thread.requestInterruption()
                if not self.extraction_thread.wait(3000):
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
